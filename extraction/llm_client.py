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
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Optional, TypeVar

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIStatusError

# Încarcă variabilele de mediu din .env
load_dotenv()

logger = logging.getLogger("llm_client")

T = TypeVar("T")


class _SingleFlightCall:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.val: Any = None
        self.exc: Optional[Exception] = None


class SingleFlight:
    """Mecanism de coalescing / deduplicare pentru cereri simultane identice (in-flight request deduplication).

    Dacă mai multe thread-uri cer aceeași cheie în același timp, doar primul thread (liderul)
    execută apelul extern; celelalte așteaptă rezultatul liderului și îl refolosesc fără request suplimentar.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[str, _SingleFlightCall] = {}

    def execute(self, key: str, fn: Callable[[], T]) -> tuple[T, bool]:
        """Execută fn() pentru key sau așteaptă rezultatul apelului în curs.

        Returnează: (rezultat, este_lider).
        Dacă este_lider este False, cererea a fost deduplicată din zbor (coalesced).
        """
        with self._lock:
            if key in self._calls:
                call = self._calls[key]
                is_leader = False
            else:
                call = _SingleFlightCall()
                self._calls[key] = call
                is_leader = True

        if not is_leader:
            call.event.wait(timeout=60)
            if call.exc is not None:
                raise call.exc
            return call.val, False

        try:
            call.val = fn()
            return call.val, True
        except Exception as e:
            call.exc = e
            raise e
        finally:
            call.event.set()
            with self._lock:
                self._calls.pop(key, None)


# Client partajat global pentru connection pooling eficient și evitarea socket-urilor orfane
_shared_openai_client: Optional[OpenAI] = None
_shared_client_lock = threading.Lock()


def _get_shared_openai_client(base_url: str, api_key: str) -> OpenAI:
    global _shared_openai_client
    with _shared_client_lock:
        if _shared_openai_client is None:
            cheie = api_key if api_key else "no-key-provided"
            _shared_openai_client = OpenAI(base_url=base_url, api_key=cheie, timeout=25.0)
        return _shared_openai_client


class LLMClient:
    """Client configurabil pentru interacțiunea cu API-ul LLM compatibil OpenAI."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.featherless.ai/v1")
        # .env.example are ambele chei; LLM_BASE_URL implicit e Featherless.
        cheie_raw = os.getenv("LLM_API_KEY", "") or os.getenv("FEATHERLESS_API_KEY", "")
        self.api_key = cheie_raw.strip().strip('"').strip("'")
        self.model_text = os.getenv("LLM_MODEL_TEXT", "Qwen/Qwen3-32B")
        self.model_vision = os.getenv("LLM_MODEL_VISION", "google/gemma-3-27b-it")

        try:
            self.max_paralele = max(1, int(os.getenv("LLM_MAX_PARALELE", "1")))
        except ValueError:
            self.max_paralele = 1

        self.semaphore = threading.Semaphore(self.max_paralele)
        self._singleflight = SingleFlight()

        # Simulatorul offline (regex) e DOAR pentru teste și trebuie cerut explicit.
        # Nu citește și nu scrie niciodată în cache, ca să nu otrăvească răspunsurile reale.
        self.offline = os.getenv("LLM_OFFLINE", "").strip().lower() in ("1", "true", "da", "yes")

        # Cache director (L2 disc)
        if cache_dir is None:
            self.cache_dir = Path(__file__).resolve().parent / ".cache"
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache L1 în memorie (RAM) pentru acces instant (0ms) în același proces
        self._cache_l1: dict[str, dict[str, Any]] = {}
        self._lock_cache = threading.RLock()

        # Statistici și metrice detaliate
        self.apeluri_reale = 0
        self.apeluri_cache = 0
        self.apeluri_cache_l1 = 0
        self.apeluri_cache_l2 = 0
        self.apeluri_singleflight = 0
        self.apeluri_offline = 0
        self.apeluri_reale_detalii: list[dict[str, Any]] = []
        self.apeluri_per_motiv: dict[str, dict[str, Any]] = {}
        self.istoric_apeluri: list[dict[str, Any]] = []
        self._lock_stats = threading.RLock()

        # Client OpenAI instanțiat la cerere (refolosește clientul partajat)
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """Instanțiază sau returnează clientul OpenAI partajat."""
        if self._client is None:
            cheie = self.api_key if self.api_key else "no-key-provided"
            self._client = _get_shared_openai_client(self.base_url, cheie)
        return self._client

    def reseteaza_statistici(self) -> None:
        """Resetează contorizarea apelurilor și istoricul metricilor."""
        with self._lock_stats:
            self.apeluri_reale = 0
            self.apeluri_cache = 0
            self.apeluri_cache_l1 = 0
            self.apeluri_cache_l2 = 0
            self.apeluri_singleflight = 0
            self.apeluri_offline = 0
            self.apeluri_reale_detalii = []
            self.apeluri_per_motiv = {}
            self.istoric_apeluri = []

    def _inregistreaza_apel(
        self,
        motiv: str,
        model: str,
        sursa: str,
        durata_ms: float = 0.0,
        status: str = "ok",
        tokens: Optional[dict[str, int]] = None,
    ) -> None:
        """Înregistrează un apel în statisticile detaliate per operațiune."""
        with self._lock_stats:
            if motiv not in self.apeluri_per_motiv:
                self.apeluri_per_motiv[motiv] = {
                    "total": 0,
                    "real": 0,
                    "cache_l1": 0,
                    "cache_l2": 0,
                    "singleflight": 0,
                    "offline": 0,
                    "durata_ms_total": 0.0,
                    "erori": 0,
                }
            entry = self.apeluri_per_motiv[motiv]
            entry["total"] += 1
            if sursa in entry:
                entry[sursa] += 1
            entry["durata_ms_total"] += durata_ms
            if status != "ok":
                entry["erori"] += 1

            if len(self.istoric_apeluri) < 300:
                self.istoric_apeluri.append({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "motiv": motiv,
                    "model": model,
                    "sursa": sursa,
                    "durata_ms": round(durata_ms, 2),
                    "status": status,
                    "tokens": tokens,
                })

    def get_statistici(self) -> dict[str, int]:
        """Returnează statisticile esențiale de apeluri (100% compatibil cu testele existente)."""
        with self._lock_stats:
            return {
                "apeluri_reale": self.apeluri_reale,
                "apeluri_cache": self.apeluri_cache,
                "apeluri_offline": self.apeluri_offline,
                "total_apeluri": self.apeluri_reale + self.apeluri_cache + self.apeluri_offline,
            }

    def get_statistici_detaliate(self) -> dict[str, Any]:
        """Returnează metrice complete privind economiile, latența și motivele apelurilor."""
        with self._lock_stats:
            total_cereri = self.apeluri_reale + self.apeluri_cache + self.apeluri_offline
            economisite = self.apeluri_cache + self.apeluri_singleflight
            rata_economisire = round((economisite / total_cereri * 100), 1) if total_cereri else 100.0

            return {
                "sumar": {
                    "total_cereri": total_cereri,
                    "apeluri_reale": self.apeluri_reale,
                    "apeluri_cache_total": self.apeluri_cache,
                    "apeluri_cache_l1_memorie": self.apeluri_cache_l1,
                    "apeluri_cache_l2_disc": self.apeluri_cache_l2,
                    "apeluri_singleflight_coalesced": self.apeluri_singleflight,
                    "apeluri_offline_simulat": self.apeluri_offline,
                    "rata_economisire_pct": rata_economisire,
                },
                "pe_operatiuni": dict(self.apeluri_per_motiv),
                "economii_estimate": {
                    "apeluri_api_evitate": economisite,
                    "timp_economisit_est_secunde": round(economisite * 2.5, 1),
                    "cost_economisit_est_usd": round(economisite * 0.003, 4),
                },
                "apeluri_reale_detalii": list(self.apeluri_reale_detalii),
            }

    def raport_metrici(self) -> str:
        """Generează un raport lizibil sub formă de tabel text."""
        detalii = self.get_statistici_detaliate()
        sumar = detalii["sumar"]
        econ = detalii["economii_estimate"]
        linii = [
            "===========================================================",
            "                  RAPORT METRICI APELURI LLM                ",
            "===========================================================",
            f"Total cereri procesate:          {sumar['total_cereri']}",
            f"  - Apeluri REALE către API:     {sumar['apeluri_reale']}",
            f"  - Cache Hit L1 (Memorie RAM):  {sumar['apeluri_cache_l1_memorie']}",
            f"  - Cache Hit L2 (Disc SHA256):  {sumar['apeluri_cache_l2_disc']}",
            f"  - Deduplicare SingleFlight:    {sumar['apeluri_singleflight_coalesced']}",
            f"  - Mod Simulat Offline:         {sumar['apeluri_offline_simulat']}",
            f"Rata de economisire apeluri:     {sumar['rata_economisire_pct']}%",
            f"Timp economisit estimat:         ~{econ['timp_economisit_est_secunde']} secunde",
            f"Cost API economisit estimat:     ~${econ['cost_economisit_est_usd']} USD",
            "-----------------------------------------------------------",
            "Defalcare pe operațiuni:",
        ]
        for motiv, date in detalii["pe_operatiuni"].items():
            linii.append(
                f"  • {motiv:<26}: {date['total']} cereri "
                f"({date.get('real', 0)} reale, {date.get('cache_l1', 0) + date.get('cache_l2', 0)} cache, "
                f"{date.get('singleflight', 0)} dedup)"
            )
        linii.append("===========================================================")
        return "\n".join(linii)

    def _calculeaza_cheie_cache(
        self,
        model: str,
        mesaje: list[dict[str, Any]],
        temperature: float = 0.0,
        cere_json: bool = False,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> str:
        """Generează un hash unic SHA256 bazat pe toți parametrii semantici ai apelului."""
        payload: dict[str, Any] = {
            "model": model,
            "mesaje": mesaje,
            "temperature": temperature,
        }
        if cere_json:
            payload["cere_json"] = True
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        sir = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(sir.encode("utf-8")).hexdigest()

    def _citeste_din_cache_cu_sursa(self, cheie: str) -> tuple[Optional[str], Optional[str]]:
        """Citește răspunsul din cache L1 (RAM) sau L2 (disc persistent).

        Întoarce (raspuns, 'l1'|'l2') sau (None, None).
        """
        # 1. Verificare cache L1 (memorie RAM) - latență 0ms
        with self._lock_cache:
            if cheie in self._cache_l1:
                return self._cache_l1[cheie].get("raspuns"), "l1"

        # 2. Verificare cache L2 (disc persistent)
        fisier_cache = self.cache_dir / f"{cheie}.json"
        if fisier_cache.exists():
            try:
                with open(fisier_cache, "r", encoding="utf-8") as f:
                    date = json.load(f)
                    with self._lock_cache:
                        self._cache_l1[cheie] = date
                    return date.get("raspuns"), "l2"
            except Exception:
                return None, None
        return None, None

    def _citeste_din_cache(self, cheie: str) -> Optional[str]:
        """Citește răspunsul din cache dacă există (păstrează compatibilitatea directă)."""
        raspuns, _ = self._citeste_din_cache_cu_sursa(cheie)
        return raspuns

    def _salveaza_in_cache(
        self,
        cheie: str,
        raspuns: str,
        model: str,
        mesaje: list[dict[str, Any]],
        model_raspuns: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Salvează răspunsul în cache-ul L1 (memorie) și L2 (disc) în mod atomic și Windows-safe."""
        payload: dict[str, Any] = {
            "cheie": cheie,
            "model": model,
            "model_raspuns": model_raspuns,
            "mesaje": mesaje,
            "raspuns": raspuns,
        }
        if tools is not None:
            payload["tools"] = tools
        if metadata:
            payload.update(metadata)

        # 1. Salvare L1 în memorie (instantaneu pentru firele aceluiași proces)
        with self._lock_cache:
            self._cache_l1[cheie] = payload

        # 2. Salvare atomică pe disc L2 (fișier temporar unic per proces și thread)
        tmp_name = f".tmp_{os.getpid()}_{threading.get_ident()}_{cheie[:8]}.tmp"
        tmp_file = self.cache_dir / tmp_name
        fisier_cache = self.cache_dir / f"{cheie}.json"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            for _ in range(5):
                try:
                    os.replace(tmp_file, fisier_cache)
                    break
                except PermissionError:
                    time.sleep(0.04)
            else:
                try:
                    os.replace(tmp_file, fisier_cache)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
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
        motiv: str = "general",
    ) -> str:
        """Apelează modelul LLM cu verificare în cache L1/L2, deduplicare SingleFlight și salvare ulterioară."""
        nume_model = model or self.model_text

        if self.offline:
            with self._lock_stats:
                self.apeluri_offline += 1
            self._inregistreaza_apel(motiv, nume_model, "offline", 0.0)
            return self._genereaza_raspuns_offline(mesaje, nume_model)

        cheie = self._calculeaza_cheie_cache(nume_model, mesaje, temperature, cere_json=cere_json)

        # 1. Verificare cache tiered (L1 RAM -> L2 Disc)
        t_start = time.perf_counter()
        raspuns_cache, sursa_cache = self._citeste_din_cache_cu_sursa(cheie)
        if raspuns_cache is not None:
            durata_ms = (time.perf_counter() - t_start) * 1000
            with self._lock_stats:
                self.apeluri_cache += 1
                if sursa_cache == "l1":
                    self.apeluri_cache_l1 += 1
                else:
                    self.apeluri_cache_l2 += 1
            self._inregistreaza_apel(motiv, nume_model, f"cache_{sursa_cache}", durata_ms)
            logger.info("LLMClient [%s HIT] (%s) Model: %s", sursa_cache.upper() if sursa_cache else "CACHE", motiv, nume_model)
            return raspuns_cache

        # 2. Apel real via SingleFlight (coalescing: deduplicare apeluri simultane pe același context)
        def _executa() -> tuple[str, str, float]:
            t_exec = time.perf_counter()
            resp, model_resp = self._executa_apel_api(
                model=nume_model,
                mesaje=mesaje,
                temperature=temperature,
                cere_json=cere_json,
            )
            d_ms = (time.perf_counter() - t_exec) * 1000
            self._salveaza_in_cache(cheie, resp, nume_model, mesaje, model_resp)
            return resp, model_resp, d_ms

        (raspuns, model_raspuns, durata_ms), is_leader = self._singleflight.execute(cheie, _executa)

        with self._lock_stats:
            if is_leader:
                self.apeluri_reale += 1
                self.apeluri_reale_detalii.append({
                    "model_cerut": nume_model,
                    "model_raspuns": model_raspuns,
                    "json_mode": cere_json,
                    "cheie_cache": cheie,
                    "motiv": motiv,
                    "durata_ms": round(durata_ms, 2),
                })
                self._inregistreaza_apel(motiv, nume_model, "real", durata_ms)
                logger.info("LLMClient [REAL CALL] (%s) Model: %s -> %s (%.1f ms)", motiv, nume_model, model_raspuns, durata_ms)
            else:
                self.apeluri_singleflight += 1
                self.apeluri_cache += 1
                self._inregistreaza_apel(motiv, nume_model, "singleflight", durata_ms)
                logger.info("LLMClient [SINGLEFLIGHT DEDUP] (%s) Model: %s (economisit 1 apel real)", motiv, nume_model)

        return raspuns

    def apeleaza_cu_json(
        self,
        mesaje: list[dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        chei_asteptate: Optional[list[str]] = None,
        chei_permise: Optional[set[str]] = None,
        motiv: str = "json",
    ) -> tuple[Optional[Any], Optional[str]]:
        """Apelează LLM-ul și extrage un JSON valid cu retry controlat.

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
            motiv=motiv,
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
                motiv=f"{motiv}_retry_{incercare}",
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
        motiv: str = "vision_ocr",
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
            motiv=motiv,
        )

    def apeleaza_cu_tools(
        self,
        mesaje: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
        max_tokens: int = 400,
        motiv: str = "planificator",
    ) -> tuple[str, list[dict[str, Any]], str]:
        """Apelează modelul LLM cu unelte (tool calling) nativ.

        Include:
        - Caching persistent L1/L2 pe schemele de tools și mesaje
        - Deduplicare concurentă SingleFlight
        - Eliminare taguri <think>...</think>
        - Concurrency control și exponential backoff
        - Înregistrare automată metrici și latență

        Întoarce (text_curatat, lista_tool_calls, model_raportat).
        """
        nume_model = model or self.model_text
        cheie = self._calculeaza_cheie_cache(
            nume_model, mesaje, temperature, cere_json=False, tools=tools, tool_choice=tool_choice
        )

        t_start = time.perf_counter()
        raspuns_cache, sursa_cache = self._citeste_din_cache_cu_sursa(cheie)
        if raspuns_cache is not None:
            durata_ms = (time.perf_counter() - t_start) * 1000
            with self._lock_stats:
                self.apeluri_cache += 1
                if sursa_cache == "l1":
                    self.apeluri_cache_l1 += 1
                else:
                    self.apeluri_cache_l2 += 1
            self._inregistreaza_apel(motiv, nume_model, f"cache_{sursa_cache}", durata_ms)
            logger.info("LLMClient [%s HIT TOOLS] (%s) Model: %s", (sursa_cache or "CACHE").upper(), motiv, nume_model)
            try:
                date = json.loads(raspuns_cache)
                return date.get("content", ""), date.get("tool_calls", []), date.get("model_raspuns", nume_model)
            except Exception:
                return raspuns_cache, [], nume_model

        # Apel real via SingleFlight
        def _executa() -> tuple[str, list[dict[str, Any]], str, float]:
            t_exec = time.perf_counter()
            if not self.api_key or self.api_key == "no-key-provided":
                raise RuntimeError("LLM_API_KEY lipsește din .env și răspunsul nu e în cache.")

            timpi_asteptare = [2, 4, 8, 16]
            with self.semaphore:
                for incercare, pauza in enumerate(timpi_asteptare):
                    try:
                        kwargs: dict[str, Any] = {
                            "model": nume_model,
                            "messages": mesaje,
                            "tools": tools,
                            "tool_choice": tool_choice,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "timeout": 20,
                        }
                        response = self.client.chat.completions.create(**kwargs)
                        alegere = response.choices[0]
                        mesaj = alegere.message
                        text_curatat = self.curata_text_raspuns(mesaj.content or "")
                        tool_calls_list: list[dict[str, Any]] = []
                        if mesaj.tool_calls:
                            for tc in mesaj.tool_calls:
                                tool_calls_list.append({
                                    "id": tc.id,
                                    "type": tc.type,
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    }
                                })
                        model_resp = str(getattr(response, "model", "") or nume_model)
                        payload_cache = json.dumps({
                            "content": text_curatat,
                            "tool_calls": tool_calls_list,
                            "model_raspuns": model_resp,
                        }, ensure_ascii=False)
                        d_ms = (time.perf_counter() - t_exec) * 1000
                        self._salveaza_in_cache(cheie, payload_cache, nume_model, mesaje, model_resp, tools=tools)
                        return text_curatat, tool_calls_list, model_resp, d_ms
                    except (RateLimitError, APIStatusError) as e:
                        cod = getattr(e, "status_code", None)
                        if (cod == 429 or isinstance(e, RateLimitError)) and incercare < len(timpi_asteptare) - 1:
                            time.sleep(pauza)
                            continue
                        raise e
                    except Exception as e:
                        if incercare < len(timpi_asteptare) - 1 and ("connection" in str(e).lower() or "timeout" in str(e).lower()):
                            time.sleep(pauza)
                            continue
                        raise e
                raise RuntimeError("Numărul maxim de reîncercări la API-ul LLM cu unelte a fost depășit.")

        (text_curatat, tool_calls_list, model_resp, durata_ms), is_leader = self._singleflight.execute(cheie, _executa)

        with self._lock_stats:
            if is_leader:
                self.apeluri_reale += 1
                self.apeluri_reale_detalii.append({
                    "model_cerut": nume_model,
                    "model_raspuns": model_resp,
                    "tool_calling": True,
                    "cheie_cache": cheie,
                    "motiv": motiv,
                    "durata_ms": round(durata_ms, 2),
                })
                self._inregistreaza_apel(motiv, nume_model, "real", durata_ms)
                logger.info("LLMClient [REAL TOOLS CALL] (%s) Model: %s -> %s (%.1f ms)", motiv, nume_model, model_resp, durata_ms)
            else:
                self.apeluri_singleflight += 1
                self.apeluri_cache += 1
                self._inregistreaza_apel(motiv, nume_model, "singleflight", durata_ms)
                logger.info("LLMClient [SINGLEFLIGHT TOOLS DEDUP] (%s) Model: %s (economisit 1 apel real)", motiv, nume_model)

        return text_curatat, tool_calls_list, model_resp


# Instanță globală singleton pentru utilizare facilă în întregul modul
_client_global: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Returnează clientul LLM partajat."""
    global _client_global
    if _client_global is None:
        _client_global = LLMClient()
    return _client_global
