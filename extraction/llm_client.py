"""Client pentru apelurile LLM către Featherless sau orice API compatibil OpenAI.

Include:
- Configurare completă din .env cu python-dotenv
- Cache persistent bazat pe SHA256 în extraction/.cache/
- Eliminare blocuri <think>...</think> (Qwen3)
- Parsare robustă JSON cu o singură reîncercare în caz de eroare sintactică
- Respectare LLM_MAX_PARALELE și backoff exponențial la HTTP 429
- Suport multimodal / vision pentru OCR
- Monitorizare apeluri reale vs. cache
"""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIStatusError

# Încarcă variabilele de mediu din .env
load_dotenv()


class LLMClient:
    """Client configurabil pentru interacțiunea cu API-ul LLM compatibil OpenAI."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.featherless.ai/v1")
        # .env.example are ambele chei; LLM_BASE_URL implicit e Featherless.
        self.api_key = os.getenv("LLM_API_KEY", "") or os.getenv("FEATHERLESS_API_KEY", "")
        self.model_text = os.getenv("LLM_MODEL_TEXT", "Qwen/Qwen3-32B")
        self.model_vision = os.getenv("LLM_MODEL_VISION", "google/gemma-3-27b-it")

        try:
            self.max_paralele = max(1, int(os.getenv("LLM_MAX_PARALELE", "1")))
        except ValueError:
            self.max_paralele = 1

        self.semaphore = threading.Semaphore(self.max_paralele)

        # Simulatorul offline (regex) e DOAR pentru teste și trebuie cerut explicit.
        # Nu citește și nu scrie niciodată în cache, ca să nu otrăvească răspunsurile reale.
        self.offline = os.getenv("LLM_OFFLINE", "").strip().lower() in ("1", "true", "da", "yes")

        # Cache director
        if cache_dir is None:
            self.cache_dir = Path(__file__).resolve().parent / ".cache"
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Statistici apeluri
        self.apeluri_reale = 0
        self.apeluri_cache = 0
        self.apeluri_offline = 0
        # Un rând per apel real: modelul cerut și cel raportat de API (pentru raport)
        self.apeluri_reale_detalii: list[dict[str, Any]] = []
        self._lock_stats = threading.Lock()

        # Client OpenAI instanțiat la cerere
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """Instanțiază sau returnează clientul OpenAI existent."""
        if self._client is None:
            # Folosește un dummy key dacă nu este setat, pentru a preveni eroare la init când se folosește doar cache
            cheie = self.api_key if self.api_key else "no-key-provided"
            self._client = OpenAI(base_url=self.base_url, api_key=cheie)
        return self._client

    def reseteaza_statistici(self) -> None:
        """Resetează contorizarea apelurilor."""
        with self._lock_stats:
            self.apeluri_reale = 0
            self.apeluri_cache = 0
            self.apeluri_offline = 0
            self.apeluri_reale_detalii = []

    def get_statistici(self) -> dict[str, int]:
        """Returnează statisticile de apeluri."""
        with self._lock_stats:
            return {
                "apeluri_reale": self.apeluri_reale,
                "apeluri_cache": self.apeluri_cache,
                "apeluri_offline": self.apeluri_offline,
                "total_apeluri": self.apeluri_reale + self.apeluri_cache + self.apeluri_offline,
            }

    def _calculeaza_cheie_cache(self, model: str, mesaje: list[dict[str, Any]], temperature: float) -> str:
        """Generează un hash unic SHA256 bazat pe model, mesaje și temperatură."""
        payload = {
            "model": model,
            "mesaje": mesaje,
            "temperature": temperature,
        }
        sir = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(sir.encode("utf-8")).hexdigest()

    def _citeste_din_cache(self, cheie: str) -> Optional[str]:
        """Citește răspunsul din cache dacă există."""
        fisier_cache = self.cache_dir / f"{cheie}.json"
        if fisier_cache.exists():
            try:
                with open(fisier_cache, "r", encoding="utf-8") as f:
                    date = json.load(f)
                    return date.get("raspuns")
            except Exception:
                return None
        return None

    def _salveaza_in_cache(
        self,
        cheie: str,
        raspuns: str,
        model: str,
        mesaje: list[dict[str, Any]],
        model_raspuns: Optional[str] = None,
    ) -> None:
        """Salvează răspunsul în cache (cu modelul cerut și cel raportat de API)."""
        fisier_cache = self.cache_dir / f"{cheie}.json"
        try:
            with open(fisier_cache, "w", encoding="utf-8") as f:
                json.dump({
                    "cheie": cheie,
                    "model": model,
                    "model_raspuns": model_raspuns,
                    "mesaje": mesaje,
                    "raspuns": raspuns,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def curata_text_raspuns(text: str) -> str:
        """Elimină blocurile <think>...</think> specifice modelelor Qwen3."""
        if not text:
            return ""
        # Elimină <think>...</think> complet sau neterminat
        curatat = re.sub(r"<think>.*?(?:</think>|$)", "", text, flags=re.DOTALL)
        return curatat.strip()

    @classmethod
    def extrage_json_din_text(cls, text: str) -> Optional[Any]:
        """Extrage primul obiect sau array JSON valid dintr-un text brut."""
        curatat = cls.curata_text_raspuns(text)
        if not curatat:
            return None

        # 1. Încearcă direct
        try:
            return json.loads(curatat)
        except Exception:
            pass

        # 2. Elimină blocuri markdown ```json ... ```
        m_code = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", curatat)
        if m_code:
            try:
                return json.loads(m_code.group(1).strip())
            except Exception:
                pass

        # 3. Găsește primul acoladă deschisă '{' și acolada corespunzătoare
        start_obj = curatat.find("{")
        if start_obj != -1:
            stack = 0
            in_str = False
            escape = False
            for i in range(start_obj, len(curatat)):
                ch = curatat[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if ch == "{":
                        stack += 1
                    elif ch == "}":
                        stack -= 1
                        if stack == 0:
                            sub_text = curatat[start_obj : i + 1]
                            try:
                                return json.loads(sub_text)
                            except Exception:
                                break

        # 4. Găsește primul array '[' ... ']'
        start_arr = curatat.find("[")
        if start_arr != -1:
            stack = 0
            in_str = False
            escape = False
            for i in range(start_arr, len(curatat)):
                ch = curatat[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if ch == "[":
                        stack += 1
                    elif ch == "]":
                        stack -= 1
                        if stack == 0:
                            sub_text = curatat[start_arr : i + 1]
                            try:
                                return json.loads(sub_text)
                            except Exception:
                                break

        return None

    @classmethod
    def despacheteaza_plic(cls, date: Any) -> Any:
        """Qwen3 în JSON mode ambalează uneori răspunsul într-un plic inventat:
        {"model": "gpt-4o-mini", "response": "<JSON-ul real, ca text>"}. Modelul real e cel din
        metadatele API-ului; textul din plic e generat. Dacă plicul conține JSON valid, îl întoarce.
        """
        if (isinstance(date, dict) and isinstance(date.get("response"), str)
                and set(date) <= {"model", "response"}):
            interior = cls.extrage_json_din_text(date["response"])
            if interior is not None:
                return interior
        return date

    def _genereaza_raspuns_offline(self, mesaje: list[dict[str, Any]], model: str) -> str:
        """Generează un răspuns simulat (doar cu LLM_OFFLINE=1, pentru teste)."""
        user_content = ""
        system_content = ""
        for m in mesaje:
            if m.get("role") == "user":
                user_content += "\n" + str(m.get("content", ""))
            elif m.get("role") == "system":
                system_content += "\n" + str(m.get("content", ""))

        # 1. Clasificare (analizăm conținutul documentului din mesajul user-ului)
        if "clasifici documentul primit" in system_content.lower() or "clasifică acest document" in user_content.lower():
            u_low = user_content.lower()
            if "01_cerere" in u_low or "cerere de finanțare" in u_low or "cerere de finantare" in u_low:
                tip = "cerere_finantare"
                motiv = "Documentul conține antetul și datele unei cereri de finanțare persoane juridice."
            elif "03_certificat" in u_low or "certificat de performanță energetică" in u_low or "certificat de performanta energetica" in u_low or "cpe-" in u_low:
                tip = "certificat_energetic"
                motiv = "Certificat de performanță energetică cu date despre clădire și performanța EPC."
            elif "04_contract" in u_low or "contracte de închiriere" in u_low or "contracte de inchiriere" in u_low or "situația chiriașilor" in u_low:
                tip = "contract_inchiriere"
                motiv = "Extras contracte de închiriere și situația chiriașilor în vigoare."
            elif "breeam" in u_low or "leed" in u_low or "sustenabilitate" in u_low:
                tip = "certificat_sustenabilitate"
                motiv = "Certificare de sustenabilitate a clădirii."
            else:
                tip = "alt_document"
                motiv = "Document general atașat dosarului."

            return json.dumps({
                "tip_document": tip,
                "incredere": 0.98,
                "motiv": motiv
            }, ensure_ascii=False)

        # 2. Extragere câmpuri: Căutăm DOAR în secțiunea cu textul paginilor documentului
        if "Conținutul paginilor selectate:" in user_content:
            doc_text = user_content.split("Conținutul paginilor selectate:", 1)[1]
        else:
            doc_text = user_content

        rezultat: dict[str, Any] = {}

        # CUI
        m = re.search(r"(?:CUI|Cod Unic de Înregistrare)[ \t]+([0-9]{2,10})", doc_text)
        if m:
            rezultat["cui"] = {
                "valoare_text": m.group(1),
                "citat": m.group(0),
                "pagina": 1,
                "incredere": 0.98
            }

        # Suma EUR
        m = re.search(r"(?:Suma solicitată de la bancă|Valoare credit|Valoarea creditului)[ \t]+([0-9.,]+[ \t]*EUR)", doc_text)
        if m:
            rezultat["suma_eur"] = {
                "valoare_text": m.group(1),
                "citat": m.group(0),
                "pagina": 1,
                "incredere": 0.95
            }

        # Cota bancă
        m = re.search(r"banca[ \t]+([0-9]+%)[ \t]*\([^)]+\)", doc_text, re.IGNORECASE)
        if m:
            rezultat["cota_banca"] = {
                "valoare_text": m.group(1),
                "citat": m.group(0),
                "pagina": 1,
                "incredere": 0.95
            }
        else:
            m2 = re.search(r"(?:cota bancă|cota de participare)[ \t]+([0-9.,%]+)", doc_text, re.IGNORECASE)
            if m2:
                rezultat["cota_banca"] = {
                    "valoare_text": m2.group(1),
                    "citat": m2.group(0),
                    "pagina": 1,
                    "incredere": 0.9
                }

        # Data aprobare: doar expresia precisă, niciodată un „Data:” generic
        m = re.search(r"Data aprobării creditului[^:\n]*:[ \t]*([0-9.\-/]+)", doc_text)
        if m:
            rezultat["data_aprobare"] = {
                "valoare_text": m.group(1),
                "citat": m.group(0),
                "pagina": 1,
                "incredere": 0.98
            }

        # Țara
        m = re.search(r"(?:Țara|Tara)[ \t]+([A-Za-zĂÎÂȘȚăîâșț]+)", doc_text)
        if m:
            rezultat["tara"] = {
                "valoare_text": m.group(1),
                "citat": m.group(0),
                "pagina": 1,
                "incredere": 0.99
            }

        # Adresă clădire
        m = re.search(r"(?:Adresă|Adresa clădirii)[ \t]+(București[^\n|]+|Str\.[^\n|]+|[^\n|]+nr\.[^\n|]+)", doc_text)
        if m:
            rezultat["adresa_cladire"] = {
                "valoare_text": m.group(1).strip(),
                "citat": m.group(0).strip(),
                "pagina": 1,
                "incredere": 0.95
            }

        # Suprafață m2 (cerere sau carte funciară)
        m = re.search(r"Suprafață utilă \(declarată\)[ \t]+([0-9.,]+[ \t]*m²)", doc_text)
        if m:
            rezultat["suprafata_m2"] = {
                "valoare_text": m.group(1),
                "citat": m.group(0),
                "pagina": 1,
                "incredere": 0.95
            }

        # Stadiu clădire
        m = re.search(r"Stadiu[ \t]+(Finalizată,[^\n|]+|În construcție[^\n|]+|[^\n|]+exploatare)", doc_text)
        if m:
            rezultat["stadiu_cladire"] = {
                "valoare_text": m.group(1).strip(),
                "citat": m.group(0).strip(),
                "pagina": 1,
                "incredere": 0.95
            }

        # Nr certificat declarat
        m = re.search(r"Număr certificat de sustenabilitate comunicat:\s*([A-Za-z0-9\-]+)", doc_text)
        if m:
            rezultat["nr_certificat_declarat"] = {
                "valoare_text": m.group(1),
                "citat": m.group(0),
                "pagina": 1,
                "incredere": 0.98
            }

        # EPC clasa
        m = re.search(r"Clasa energetică[ \t|]+([A-G]\+?)", doc_text)
        if m:
            rezultat["epc_clasa"] = {
                "valoare_text": m.group(1),
                "citat": f"Clasa energetică {m.group(1)}",
                "pagina": 1,
                "incredere": 0.98
            }

        # EPC energie finala
        m = re.search(r"Consum anual specific de energie finală[ \t|]+([0-9.,]+[ \t]*kWh/m²[·\.]an)", doc_text)
        if m:
            rezultat["epc_energie_finala"] = {
                "valoare_text": m.group(1),
                "citat": f"Consum anual specific de energie finală {m.group(1)}",
                "pagina": 1,
                "incredere": 0.98
            }

        # EPC suprafata m2
        m = re.search(r"Aria utilă \(Au\)[ \t|]+([0-9.,]+[ \t]*m²)", doc_text)
        if m:
            rezultat["epc_suprafata_m2"] = {
                "valoare_text": m.group(1),
                "citat": f"Aria utilă (Au) {m.group(1)}",
                "pagina": 1,
                "incredere": 0.98
            }

        # Afirmații client
        afirmatii = []
        linii = doc_text.splitlines()
        for idx, line in enumerate(linii):
            line_str = line.strip()
            if line_str.startswith("•"):
                text_declaratie = line_str.lstrip("•").strip()
                # Verifică dacă linia continuă pe rândul următor
                if idx + 1 < len(linii) and not linii[idx + 1].strip().startswith("•") and not linii[idx + 1].strip().startswith("5."):
                    continuitate = linii[idx + 1].strip()
                    if continuitate and not continuitate.startswith("---") and not continuitate.startswith("===") and not continuitate.startswith("|"):
                        text_declaratie += " " + continuitate
                afirmatii.append(text_declaratie)

        if afirmatii:
            rezultat["afirmatii_client"] = afirmatii

        # Adăugăm un bloc think specific Qwen3 pentru a testa parsarea
        raspuns_cu_think = f"<think>\nAnalizăm documentul și extragem câmpurile solicitate.\nToate valorile sunt verificate în text.\n</think>\n{json.dumps(rezultat, ensure_ascii=False, indent=2)}"
        return raspuns_cu_think

    def _executa_apel_api(
        self,
        model: str,
        mesaje: list[dict[str, Any]],
        temperature: float = 0.0,
        cere_json: bool = True,
    ) -> tuple[str, str]:
        """Execută apelul HTTP către API cu retry exponențial la HTTP 429.

        Întoarce (conținut, modelul raportat de API în răspuns).
        """
        if not self.api_key or self.api_key == "no-key-provided":
            raise RuntimeError(
                "LLM_API_KEY lipsește din .env și răspunsul nu e în cache. "
                "Setează cheia sau, doar pentru teste, LLM_OFFLINE=1."
            )

        timpi_asteptare = [2, 4, 8, 16]

        with self.semaphore:
            for incercare, pauza in enumerate(timpi_asteptare):
                try:
                    kwargs: dict[str, Any] = {
                        "model": model,
                        "messages": mesaje,
                        "temperature": temperature,
                    }
                    if cere_json:
                        kwargs["response_format"] = {"type": "json_object"}

                    try:
                        response = self.client.chat.completions.create(**kwargs)
                    except Exception as err_json:
                        # Dacă parametrul response_format nu este acceptat de model
                        if cere_json and ("response_format" in str(err_json).lower() or "400" in str(err_json)):
                            kwargs.pop("response_format", None)
                            response = self.client.chat.completions.create(**kwargs)
                        else:
                            raise err_json

                    continut = response.choices[0].message.content or ""
                    return continut, str(getattr(response, "model", "") or "")

                except (RateLimitError, APIStatusError) as e:
                    # HTTP 429 sau rate limit
                    cod = getattr(e, "status_code", None)
                    if cod == 429 or isinstance(e, RateLimitError):
                        if incercare < len(timpi_asteptare) - 1:
                            time.sleep(pauza)
                            continue
                    raise e
                except Exception as e:
                    # Dacă este o eroare tranzitorie de rețea, încearcă din nou
                    if incercare < len(timpi_asteptare) - 1 and ("connection" in str(e).lower() or "timeout" in str(e).lower()):
                        time.sleep(pauza)
                        continue
                    raise e

            raise RuntimeError("Numărul maxim de reîncercări la API-ul LLM a fost depășit.")

    def apeleaza(
        self,
        mesaje: list[dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        cere_json: bool = True,
    ) -> str:
        """Apelează modelul LLM cu verificare în cache și salvare ulterioară."""
        nume_model = model or self.model_text

        if self.offline:
            with self._lock_stats:
                self.apeluri_offline += 1
            return self._genereaza_raspuns_offline(mesaje, nume_model)

        cheie = self._calculeaza_cheie_cache(nume_model, mesaje, temperature)

        raspuns_cache = self._citeste_din_cache(cheie)
        if raspuns_cache is not None:
            with self._lock_stats:
                self.apeluri_cache += 1
            return raspuns_cache

        # Apel real
        raspuns, model_raspuns = self._executa_apel_api(
            model=nume_model,
            mesaje=mesaje,
            temperature=temperature,
            cere_json=cere_json,
        )

        with self._lock_stats:
            self.apeluri_reale += 1
            self.apeluri_reale_detalii.append({
                "model_cerut": nume_model,
                "model_raspuns": model_raspuns,
                "json_mode": cere_json,
                "cheie_cache": cheie,
            })

        self._salveaza_in_cache(cheie, raspuns, nume_model, mesaje, model_raspuns)
        return raspuns

    def apeleaza_cu_json(
        self,
        mesaje: list[dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        chei_asteptate: Optional[list[str]] = None,
        chei_permise: Optional[set[str]] = None,
    ) -> tuple[Optional[Any], Optional[str]]:
        """Apelează LLM-ul și extrage un JSON valid.

        În caz de eșec de parsare, face până la două reîncercări.
        Dacă se dau chei_permise, orice cheie din afara chei_asteptate ∪ chei_permise invalidează răspunsul.
        Dacă se dau chei_asteptate, un obiect care nu conține niciuna dintre ele
        (răspuns degenerat, ex. {"response": "{"}) e tratat tot ca eșec.
        Întoarce (obiect_json, eroare_str).
        """

        def este_valid(date: Any) -> bool:
            if date is None:
                return False
            if chei_asteptate and isinstance(date, dict):
                if not any(k in date for k in chei_asteptate):
                    return False
                # chei stâlcite (ex. "sumaa_eur") = răspuns degenerat, chiar dacă alte chei sunt corecte
                if chei_permise is not None and not set(date) <= (set(chei_asteptate) | chei_permise):
                    return False
            return True

        nume_model = model or self.model_text
        text_raspuns = self.apeleaza(
            mesaje=mesaje,
            model=nume_model,
            temperature=temperature,
            cere_json=True,
        )

        date_json = self.despacheteaza_plic(self.extrage_json_din_text(text_raspuns))
        if este_valid(date_json):
            return date_json, None

        # Reîncercări: mesajele originale + o cerință explicită. Răspunsul greșit NU intră în istoric
        # (modelul tinde să-l continue). A doua reîncercare e fără JSON mode, care la unii furnizori
        # produce răspunsuri degenerate. Mesajele sunt deterministe, deci și reîncercările se cache-uiesc.
        cerinta = (
            "Întoarce EXCLUSIV obiectul JSON valid cerut"
            + (f", cu cheile: {', '.join(chei_asteptate)}" if chei_asteptate else "")
            + ". Fără explicații, fără introducere, fără blocuri <think> și fără formatare markdown."
        )
        text_retry = text_raspuns
        for incercare, cere_json in ((1, True), (2, False)):
            mesaje_retry = list(mesaje) + [{"role": "user", "content": f"{cerinta} (reîncercarea {incercare})"}]
            text_retry = self.apeleaza(
                mesaje=mesaje_retry,
                model=nume_model,
                temperature=temperature,
                cere_json=cere_json,
            )
            date_json_retry = self.despacheteaza_plic(self.extrage_json_din_text(text_retry))
            if este_valid(date_json_retry):
                return date_json_retry, None

        return None, f"Eșec parsare JSON chiar și după reîncercări. Răspuns brut: {text_retry[:200]}"

    def apeleaza_vision(
        self,
        prompt: str,
        imagine_bytes: bytes,
        mime_type: str = "image/jpeg",
        temperature: float = 0.0,
    ) -> str:
        """Apelează modelul de Vision pentru OCR pe imagini."""
        b64_str = base64.b64encode(imagine_bytes).decode("utf-8")
        mesaje = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_str}"
                        },
                    },
                ],
            }
        ]

        return self.apeleaza(
            mesaje=mesaje,
            model=self.model_vision,
            temperature=temperature,
            cere_json=False,
        )


# Instanță globală singleton pentru utilizare facilă în întregul modul
_client_global: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Returnează clientul LLM partajat."""
    global _client_global
    if _client_global is None:
        _client_global = LLMClient()
    return _client_global
