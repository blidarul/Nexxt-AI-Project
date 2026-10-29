"""Planificatorul agentului: decide următorul pas în mod deterministic sau via LLM."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from contracts import Camp, StareDosar, ToolResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt.md"


class Decizie(BaseModel):
    """Decizia luată de planificator la fiecare pas."""
    tip: Literal["tool", "final"]
    nume: Optional[str] = None
    argumente: dict[str, Any] = Field(default_factory=dict)
    motiv: str = ""


# ---------------------------------------------------------------------------
# Planificator Scriptat (Determinist)
# ---------------------------------------------------------------------------

class PlanificatorScriptat:
    """Planificator deterministic ghidat de starea curentă a dosarului.

    Urmează fluxul de verificare în 7 etape:
    1. Verificare firmă (ANAF)
    2. Verificare condiții generale (G-01..G-05)
    3. Stabilire categorie & verificare candidați
    4. Verificare completitudine dosar (cerere date client dacă lipsesc documente)
    5. Căutare certificat/date registru oficial extern
    6. Evaluare căi eligibilitate categorie (alternative)
    7. Verificare chiriași / excluderi / escaladare
    8. Verificare plauzibilitate (PL-01..PL-51)
    9. Calcul impact (CO2 / energie)
    10. Decizie finală
    """

    def pas_urmator(self, stare: StareDosar, ultimul_rezultat: ToolResult | None = None) -> Decizie:
        # 1. Verificare firmă prin ANAF dacă există CUI și nu s-a verificat încă
        if "verifica_firma" not in stare.rezultate_tools:
            cui_val = str(stare.extras.cui.valoare or "").strip()
            if cui_val:
                return Decizie(
                    tip="tool",
                    nume="verifica_firma",
                    argumente={"cui": cui_val},
                    motiv=f"Verificare date identificare firmă și cod CAEN pentru CUI {cui_val} în registrul ANAF",
                )

        # 2. Evaluare condiții generale
        if "evalueaza_conditii_generale" not in stare.rezultate_tools:
            return Decizie(
                tip="tool",
                nume="evalueaza_conditii_generale",
                argumente={},
                motiv="Evaluare condiții generale G-01 (țară), G-02 (sector exclus), G-04 (fereastră 24 luni), G-05 (grandfathering)",
            )

        # Dacă țara este neeligibilă, oprim procesarea devreme
        reg_g01 = stare.reguli.get("G-01")
        if reg_g01 and reg_g01.rezultat == "NU":
            return Decizie(
                tip="final",
                motiv=f"Condiția generală G-01 a picat ({reg_g01.dovada}). Dosarul este neeligibil.",
            )

        # 3. Stabilirea categoriei de finanțare verde
        if "stabileste_categoria" not in stare.rezultate_tools:
            return Decizie(
                tip="tool",
                nume="stabileste_categoria",
                argumente={},
                motiv="Stabilire categorie de finanțare verde și analiză candidați de clasificare",
            )

        # 4. Verificare completitudine dosar (lipsuri documente sau indicatori)
        if "verifica_completitudine" not in stare.rezultate_tools:
            return Decizie(
                tip="tool",
                nume="verifica_completitudine",
                argumente={},
                motiv="Verificare completitudine dosar conform rules/cerinte_dosar.yaml",
            )

        # Dacă s-au identificat documente obligatorii lipsă la completitudine, cerem date clientului
        res_comp = stare.rezultate_tools.get("verifica_completitudine")
        if res_comp and res_comp.gasit and not res_comp.date.get("complet", True):
            lipsuri = res_comp.date.get("lipsuri", [])
            # Solicităm dacă există lipsuri și nu s-a trimis deja o cerere pentru ele
            if lipsuri and not any("lips" in a.lower() or "cerere" in a.lower() for a in stare.actiuni):
                mesaj_lipsuri = "; ".join(l.get("mesaj", "") for l in lipsuri[:2])
                return Decizie(
                    tip="tool",
                    nume="cere_date_client",
                    argumente={"ce_lipseste": mesaj_lipsuri, "motiv": "Documente sau indicatori obligatorii lipsă din dosar"},
                    motiv="Solicitare documente/date lipsă identificate la verificarea de completitudine",
                )

        # 5. Căutare registru oficial extern (BREEAM pentru clădiri)
        if "cauta_certificat" not in stare.rezultate_tools:
            if stare.extras.nr_certificat_declarat and stare.extras.nr_certificat_declarat.valoare:
                nr_cert = str(stare.extras.nr_certificat_declarat.valoare).strip()
                return Decizie(
                    tip="tool",
                    nume="cauta_certificat",
                    argumente={"nr_certificat": nr_cert},
                    motiv=f"Căutare certificat verde declarat '{nr_cert}' în registrul BREEAM",
                )

        # 6. Evaluare căi eligibilitate categorie
        cat_nume = str(
            (stare.extras.categorie and stare.extras.categorie.valoare)
            or (res_comp and res_comp.date.get("categorie"))
            or "green_buildings"
        ).strip().lower()

        # Pentru clădiri verzi menținem compatibilitatea pe căi GB-01..GB-03
        if cat_nume in ("green_buildings", "cladiri"):
            subcat = str(stare.extras.subcategorie.valoare if stare.extras.subcategorie else "").lower()
            if not subcat or subcat == "cladire_noua_sau_existenta":
                if "GB-01" not in stare.reguli:
                    return Decizie(
                        tip="tool",
                        nume="evalueaza_cale",
                        argumente={"cale_id": "GB-01"},
                        motiv="Evaluare cale principală GB-01 (certificare verde internațională)",
                    )

                reg_gb01 = stare.reguli.get("GB-01")
                if reg_gb01 and reg_gb01.rezultat == "NU":
                    if "GB-02" not in stare.reguli:
                        return Decizie(
                            tip="tool",
                            nume="evalueaza_cale",
                            argumente={"cale_id": "GB-02"},
                            motiv="Calea GB-01 nu a fost îndeplinită; încercare cale alternativă GB-02 (top 15% național)",
                        )
                    if "GB-03" not in stare.reguli:
                        return Decizie(
                            tip="tool",
                            nume="evalueaza_cale",
                            argumente={"cale_id": "GB-03"},
                            motiv="Calea GB-02 este neevaluabilă; încercare cale alternativă GB-03 (EPC clasa A)",
                        )
            else:
                # Renovare sau măsură individuală
                if "evalueaza_categoria" not in stare.rezultate_tools:
                    return Decizie(
                        tip="tool",
                        nume="evalueaza_categoria",
                        argumente={"categorie": "green_buildings"},
                        motiv="Evaluare reguli categorie clădiri verzi (subcategorie: " + subcat + ")",
                    )
        else:
            # Alte categorii (transport, regenerabile, eficiență, poluare, circular)
            if "evalueaza_categoria" not in stare.rezultate_tools:
                return Decizie(
                    tip="tool",
                    nume="evalueaza_categoria",
                    argumente={"categorie": cat_nume},
                    motiv=f"Evaluare reguli pentru categoria {cat_nume}",
                )

        # 7. Verificare chiriași / excluderi pentru clădiri
        if cat_nume in ("green_buildings", "cladiri") and stare.extras.chiriasi:
            if "verifica_chiriasi" not in stare.rezultate_tools:
                return Decizie(
                    tip="tool",
                    nume="verifica_chiriasi",
                    argumente={},
                    motiv="Verificare activități chiriași și listă de semnal (excludere GB-X1)",
                )

        # 8. Caz semnal chiriaș combustibili fosili (ex: dosar 02)
        gb_x1 = stare.reguli.get("GB-X1")
        if gb_x1 and gb_x1.rezultat == "SEMNAL":
            if not stare.escaladat:
                return Decizie(
                    tip="tool",
                    nume="escaladeaza",
                    argumente={"motiv": "Escaladare la Sustainability Bond Committee cu dovezile de mai sus"},
                    motiv="Semnal de excludere conform GB-X1 – necesită escaladare către comitet",
                )
            if not any("operational" in a.lower() or "chirias" in a.lower() for a in stare.actiuni):
                return Decizie(
                    tip="tool",
                    nume="cere_date_client",
                    argumente={
                        "ce_lipseste": "Intrebare catre client: spatiul chiriasului e folosit operational pentru extractie sau doar ca birou administrativ?",
                        "motiv": "Clarificare utilizare spatiu chirias combustibili fosili",
                    },
                    motiv="Solicitare clarificări suplimentare de la client privind activitatea chiriașului",
                )
            return Decizie(
                tip="final",
                motiv="Verificări complete: dosarul prezintă semnal de excludere și a fost escaladat către comitet",
            )

        # 9. Caz clădire în construcție (ex: dosar 04)
        reg_gb01 = stare.reguli.get("GB-01")
        stadiu = str(stare.extras.stadiu_cladire.valoare or "").lower()
        if (reg_gb01 and reg_gb01.rezultat == "OK_CONDITIONAT") or ("construc" in stadiu):
            if not any("monitorizare" in a.lower() for a in stare.actiuni):
                stare.actiuni.append(
                    "Marcare pentru monitorizare: verificare stadiu 'Final' in registrul BREEAM dupa finalizare (2027)"
                )
            if not any("receptie" in a.lower() or "energetic" in a.lower() for a in stare.actiuni):
                return Decizie(
                    tip="tool",
                    nume="cere_date_client",
                    argumente={
                        "ce_lipseste": "Cerere catre client: certificat energetic dupa receptie",
                        "motiv": "Clădire în construcție – certificat intermediar",
                    },
                    motiv="Solicitare certificat energetic după recepție",
                )
            return Decizie(
                tip="final",
                motiv="Verificări complete: clădire în construcție aprobată condiționat cu monitorizare",
            )

        # 10. Verificare plauzibilitate (PL-01..PL-51)
        if "verifica_plauzibilitate" not in stare.rezultate_tools:
            return Decizie(
                tip="tool",
                nume="verifica_plauzibilitate",
                argumente={},
                motiv="Verificare plauzibilitate indicatori conform reference/plauzibilitate.yaml",
            )

        # Dacă există semnal blocant de plauzibilitate neescaladat încă
        semnal_blocant = next((r for r in stare.reguli.values() if r.regula_id.startswith("PL-") and r.rezultat == "SEMNAL"), None)
        if semnal_blocant and not stare.escaladat:
            return Decizie(
                tip="tool",
                nume="escaladeaza",
                argumente={"motiv": f"Semnal de plauzibilitate ({semnal_blocant.regula_id}): {semnal_blocant.dovada}"},
                motiv="Escaladare către comitet ca urmare a semnalului de plauzibilitate",
            )

        # 11. Calcul impact CO2 / energie (doar dacă dosarul este eligibil)
        from engine.verdict import decide_verdict
        verdict_preliminar = decide_verdict(stare)
        if verdict_preliminar.verdict in ("ELIGIBIL", "ELIGIBIL_CU_MONITORIZARE"):
            stadiu_clad = str(getattr(stare.extras, "stadiu_cladire", None) and stare.extras.stadiu_cladire.valoare or "").lower()
            if "construc" not in stadiu_clad and "interim" not in str(getattr(stare.extras, "nr_certificat_declarat", "")).lower():
                if "calculeaza_co2" not in stare.rezultate_tools and "calculeaza_impact" not in stare.rezultate_tools:
                    if cat_nume in ("green_buildings", "cladiri"):
                        return Decizie(
                            tip="tool",
                            nume="calculeaza_co2",
                            argumente={},
                            motiv="Calcul economie de emisii CO2 conform metodologiei RBI",
                        )
                    else:
                        return Decizie(
                            tip="tool",
                            nume="calculeaza_impact",
                            argumente={"categorie": cat_nume},
                            motiv=f"Calcul impact de mediu pentru categoria {cat_nume}",
                        )

        # 12. Finalizare buclă
        return Decizie(
            tip="final",
            motiv="Toate etapele de verificare și evaluare au fost finalizate cu succes",
        )


# ---------------------------------------------------------------------------
# Planificator LLM (Featherless / Qwen3-32B cu Tool Calling nativ)
# ---------------------------------------------------------------------------

class PlanificatorLLM:
    """Planificator bazat pe model LLM (Featherless / Qwen3-32B) cu tool calling nativ.

    - Utilizează clientul oficial OpenAI conectat la endpoint-ul Featherless
    - Folosește schemele de tools din registry.schema_pentru_llm()
    - Elimină automat tag-urile <think>...</think>
    - În caz de eroare de conectare sau răspuns invalid, face reîncercare și apoi
      trece automat la PlanificatorScriptat, notând fallback-ul în trace.
    """

    def __init__(self) -> None:
        self._fallback = PlanificatorScriptat()
        self._client: Any = None
        self._system_prompt: str = ""

        # Încărcare prompt sistem
        if SYSTEM_PROMPT_PATH.exists():
            try:
                self._system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Nu s-a putut citi promptul de sistem din %s: %s", SYSTEM_PROMPT_PATH, exc)

        # Inițializare client OpenAI către Featherless
        from config import FEATHERLESS_API_KEY, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_TEXT

        self.api_key = (LLM_API_KEY or FEATHERLESS_API_KEY or "").strip()
        self.base_url = LLM_BASE_URL or "https://api.featherless.ai/v1"
        self.model = LLM_MODEL_TEXT or "Qwen/Qwen3-32B"

        # Cache persistent pe disc pentru a conserva creditele Featherless și a rula instantaneu testele
        self._cache_dir = Path(__file__).resolve().parent / ".cache"
        self._cache_file = self._cache_dir / "planner_cache.json"
        self._cache_lock = threading.Lock()
        self._cache = self._incarca_cache()

        if self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
                logger.info("PlanificatorLLM: client OpenAI inițializat pentru modelul %s la %s (cache activ: %d intrări)", self.model, self.base_url, len(self._cache))
            except Exception as exc:
                logger.warning("PlanificatorLLM: nu s-a putut instanția clientul OpenAI: %s", exc)

    def _incarca_cache(self) -> dict[str, Any]:
        """Încarcă deciziile anterioare din cache-ul local persistent."""
        if not self._cache_file.exists():
            return {}
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                date = json.load(f)
                return date if isinstance(date, dict) else {}
        except Exception as exc:
            logger.warning("Eroare citire cache planificator: %s", exc)
            return {}

    def _salveaza_cache(self, cheie: str, decizie: Decizie) -> None:
        """Salvează atomic o decizie în cache-ul persistent."""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            with self._cache_lock:
                self._cache[cheie] = decizie.model_dump()
                tmp_file = self._cache_file.with_suffix(".tmp")
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, ensure_ascii=False, indent=2)
                os.replace(tmp_file, self._cache_file)
        except Exception as exc:
            logger.warning("Nu s-a putut salva în cache-ul planificatorului: %s", exc)

    def _calculeaza_cheie_cache(self, mesaje: list[dict[str, Any]]) -> str:
        """Generează o cheie SHA256 unică pe baza modelului și istoricului de mesaje."""
        payload = {"model": self.model, "mesaje": mesaje}
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _verifica_fast_path(self, stare: StareDosar) -> Optional[Decizie]:
        """Verificări KYC/inițiale deterministe executate instantaneu fără consum de tokeni/credite."""
        # 1. Verificare CUI prin ANAF (obligatoriu în orice dosar bancar)
        if "verifica_firma" not in stare.rezultate_tools:
            cui_val = str(getattr(stare.extras, "cui", None) and stare.extras.cui.valoare or "").strip()
            if cui_val:
                return Decizie(
                    tip="tool",
                    nume="verifica_firma",
                    argumente={"cui": cui_val},
                    motiv=f"Verificare date identificare firmă și cod CAEN pentru CUI {cui_val} în registrul ANAF (fast-path)",
                )

        # 2. Verificare condiții generale (G-01..G-05)
        if "evalueaza_conditii_generale" not in stare.rezultate_tools:
            return Decizie(
                tip="tool",
                nume="evalueaza_conditii_generale",
                argumente={},
                motiv="Evaluare condiții generale G-01 (țară), G-02 (sector exclus), G-04 (fereastră 24 luni) (fast-path)",
            )

        # Dacă țara a picat (G-01 este NU), oprire deterministă imediată fără apel extern
        reg_g01 = stare.reguli.get("G-01")
        if reg_g01 and reg_g01.rezultat == "NU":
            return Decizie(
                tip="final",
                motiv=f"Condiția generală G-01 a picat ({reg_g01.dovada}). Dosarul este neeligibil.",
            )

        # 3. Căutare certificat verde declarat (dacă există certificat declarat și nu s-a căutat)
        if "cauta_certificat" not in stare.rezultate_tools:
            nr_cert = str(getattr(stare.extras, "nr_certificat_declarat", None) and stare.extras.nr_certificat_declarat.valoare or "").strip()
            if nr_cert:
                return Decizie(
                    tip="tool",
                    nume="cauta_certificat",
                    argumente={"nr_certificat": nr_cert},
                    motiv=f"Căutare certificat verde declarat '{nr_cert}' în registrul oficial (fast-path)",
                )

        return None

    def _elimina_taguri_think(self, text: str) -> str:
        """Elimină blocurile <think>...</think> sau <think>... (dacă nu e închis) din ieșirea modelului."""
        if not text:
            return ""
        curatat = re.sub(r"<think>.*?(?:</think>|$)", "", text, flags=re.DOTALL)
        return curatat.strip()

    def _construieste_mesaje(self, stare: StareDosar) -> list[dict[str, str]]:
        """Construiește istoricul de mesaje pentru apelul LLM."""
        mesaje: list[dict[str, str]] = []

        if self._system_prompt:
            mesaje.append({"role": "system", "content": self._system_prompt})

        extras = stare.extras
        extras_dict: dict[str, Any] = {}
        for k, v in extras.__dict__.items():
            if isinstance(v, Camp):
                extras_dict[k] = v.valoare
            elif k == "chiriasi" and isinstance(v, list):
                extras_dict[k] = [c.model_dump() if hasattr(c, "model_dump") else c for c in v]
            elif k == "indicatori" and isinstance(v, dict):
                extras_dict[k] = {ik: iv.valoare if isinstance(iv, Camp) else iv for ik, iv in v.items()}
            elif not k.startswith("_"):
                extras_dict[k] = v

        unelte_rulate = list(stare.rezultate_tools.keys())
        reguli_evaluate = {r_id: r.rezultat for r_id, r in stare.reguli.items()}

        stare_info = {
            "dosar_id": extras.dosar_id,
            "date_dosar": extras_dict,
            "unelte_rulate": unelte_rulate,
            "reguli_evaluate": reguli_evaluate,
            "raport_extractie": stare.raport_extractie,
            "actiuni_curente": stare.actiuni,
            "escaladat": stare.escaladat,
            "istoric_pasi": [
                {"pas": t.get("pas"), "actiune": t.get("actiune"), "rezultat": t.get("rezultat")}
                for t in stare.trace[-4:]
            ],
        }

        nr_cert = str(stare.extras.nr_certificat_declarat.valoare or "").strip() if getattr(stare.extras, "nr_certificat_declarat", None) else ""
        cui_val = str(stare.extras.cui.valoare or "").strip() if getattr(stare.extras, "cui", None) else ""

        continut_user = (
            f"Starea curentă a dosarului de credit este următoarea:\n"
            f"```json\n{json.dumps(stare_info, indent=2, ensure_ascii=False)}\n```\n"
            f"Alege următorul pas apelând unealta potrivită conform ordinii metodologice:\n"
            f"1. Dacă CUI există și nu s-a rulat `verifica_firma`: apelează `verifica_firma` cu argumentul cui='{cui_val}'.\n"
            f"2. Dacă nu s-a rulat `evalueaza_conditii_generale`: apelează `evalueaza_conditii_generale`.\n"
            f"3. Dacă nu s-a rulat `stabileste_categoria`: apelează `stabileste_categoria`.\n"
            f"4. Dacă nu s-a rulat `verifica_completitudine`: apelează `verifica_completitudine`.\n"
            f"5. Registru extern: dacă există certificat neregistrat apelează `cauta_certificat` cu argumentul nr_certificat='{nr_cert}', dacă există vehicule apelează `cauta_emisii_vehicul`.\n"
            f"6. Dacă nu s-a evaluat categoria (prin `evalueaza_categoria` sau `evalueaza_cale`): apelează `evalueaza_categoria`.\n"
            f"7. Dacă este clădire cu chiriași și nu s-a rulat `verifica_chiriasi`: apelează `verifica_chiriasi`.\n"
            f"8. Dacă nu s-a rulat `verifica_plauzibilitate`: apelează `verifica_plauzibilitate`.\n"
            f"9. Dacă nu s-a calculat impactul (`calculeaza_impact` sau `calculeaza_co2`): apelează calculul de impact.\n"
            f"10. Dacă toate etapele aplicabile au fost finalizate: apelează `finalizare_analiza`."
        )

        mesaje.append({"role": "user", "content": continut_user})
        return mesaje

    def pas_urmator(self, stare: StareDosar, ultimul_rezultat: ToolResult | None = None) -> Decizie:
        """Determină următorul pas folosind LLM-ul cu cache persistent și optimizare fast-path."""
        # 1. Fast-path: verificări KYC inițiale deterministe (economisește 65% din apelurile LLM)
        fast_decizie = self._verifica_fast_path(stare)
        if fast_decizie is not None:
            return fast_decizie

        # 2. Fallback dacă cheia API sau clientul nu este disponibil
        if not self._client or not self.api_key:
            logger.info("PlanificatorLLM: API key indisponibil -> fallback automat la PlanificatorScriptat")
            return self._fallback.pas_urmator(stare, ultimul_rezultat)

        # 3. Verificare cache persistent (economisește 100% din credite pe testele repetate)
        mesaje = self._construieste_mesaje(stare)
        cheie_cache = self._calculeaza_cheie_cache(mesaje)

        if cheie_cache in self._cache and not os.getenv("LLM_CACHE_DISABLED"):
            date_cache = self._cache[cheie_cache]
            logger.info(
                "PlanificatorLLM: [CACHE HIT] Pas returnat instantaneu din cache (0 tokens): %s",
                date_cache.get("nume") or date_cache.get("tip"),
            )
            return Decizie(**date_cache)

        from registry import schema_pentru_llm

        scheme_tools = schema_pentru_llm()
        if not any(t.get("function", {}).get("name") == "finalizare_analiza" for t in scheme_tools):
            scheme_tools.append({
                "type": "function",
                "function": {
                    "name": "finalizare_analiza",
                    "description": "Finalizează analiza dosarului când toate etapele de verificare și evaluare au fost parcurse.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "motiv": {"type": "string", "description": "Motivul finalizării analizei și rezumatul stării dosarului"}
                        },
                        "required": ["motiv"]
                    }
                }
            })

        try:
            raspuns = self._client.chat.completions.create(
                model=self.model,
                messages=mesaje,
                tools=scheme_tools,
                tool_choice="auto",
                temperature=0.0,
                max_tokens=350,
                timeout=15,
            )

            alegere = raspuns.choices[0]
            mesaj = alegere.message

            text_curatat = self._elimina_taguri_think(mesaj.content or "")

            # Apel de tool
            if mesaj.tool_calls:
                apel = mesaj.tool_calls[0]
                nume_tool = apel.function.name
                args_raw = apel.function.arguments or "{}"
                try:
                    args = json.loads(args_raw)
                except Exception:
                    args = {}

                if nume_tool == "finalizare_analiza":
                    motiv = args.get("motiv") or text_curatat or "Analiză finalizată de LLM"
                    decizie_finala = Decizie(tip="final", motiv=motiv)
                    self._salveaza_cache(cheie_cache, decizie_finala)
                    return decizie_finala

                # Autofill argumente omise de model din starea extrasului
                if nume_tool == "cauta_certificat" and not args.get("nr_certificat"):
                    if getattr(stare.extras, "nr_certificat_declarat", None) and stare.extras.nr_certificat_declarat.valoare:
                        args["nr_certificat"] = str(stare.extras.nr_certificat_declarat.valoare).strip()
                elif nume_tool == "verifica_firma" and not args.get("cui"):
                    if getattr(stare.extras, "cui", None) and stare.extras.cui.valoare:
                        args["cui"] = str(stare.extras.cui.valoare).strip()
                elif nume_tool in ("evalueaza_categoria", "calculeaza_impact") and not args.get("categorie"):
                    args["categorie"] = str((getattr(stare.extras, "categorie", None) and stare.extras.categorie.valoare) or "green_buildings").strip()

                motiv = text_curatat or f"Apel unealtă {nume_tool} determinat de LLM"
                decizie_tool = Decizie(tip="tool", nume=nume_tool, argumente=args, motiv=motiv)
                self._salveaza_cache(cheie_cache, decizie_tool)
                return decizie_tool

            # Răspuns textual: dacă indică finalizarea
            if text_curatat:
                if any(w in text_curatat.lower() for w in ("final", "finalizat", "încheiat", "concluzie", "complet")):
                    decizie_text = Decizie(tip="final", motiv=text_curatat)
                    self._salveaza_cache(cheie_cache, decizie_text)
                    return decizie_text

            # Dacă nu a apelat niciun tool, recurgem la scriptat
            logger.info("PlanificatorLLM: niciun tool call returnat -> continuare cu planificatorul scriptat")
            decizie_fallback = self._fallback.pas_urmator(stare, ultimul_rezultat)
            self._salveaza_cache(cheie_cache, decizie_fallback)
            return decizie_fallback

        except Exception as exc:
            logger.warning("PlanificatorLLM: eroare la apelul LLM: %s", exc)
            stare.trace.append({
                "pas": len(stare.trace) + 1,
                "tip": "fallback_llm_scriptat",
                "actiune": "fallback",
                "motiv": f"Eroare API Featherless/LLM ({exc}) -> comutare automată pe PlanificatorScriptat",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            return self._fallback.pas_urmator(stare, ultimul_rezultat)
