"""Orchestratorul agentului: leagă extracția, planificatorul, registry-ul și verdictul.

Fluxul:
    1. extrage(folder) -> DosarExtras
    2. Construiește StareDosar (memoria de lucru)
    3. Bucla: planificator.pas_urmator(stare) -> Decizie
       - Decizie tip='tool'  -> registry.apeleaza(nume, argumente, stare) -> trace
       - Decizie tip='final' -> iese din buclă
    4. decide_verdict(stare) -> Verdict
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from contracts import DosarExtras, StareDosar, ToolResult, Verdict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de configurație
# ---------------------------------------------------------------------------

def _get_max_pasi() -> int:
    """Citește MAX_PASI_AGENT din config."""
    from config import MAX_PASI_AGENT
    return int(MAX_PASI_AGENT)


def _get_mod_extractie() -> str:
    """Citește MOD_EXTRACTIE din config."""
    from config import MOD_EXTRACTIE
    return str(MOD_EXTRACTIE)


def _get_mod_agent() -> str:
    """Citește MOD_AGENT din config."""
    from config import MOD_AGENT
    return str(MOD_AGENT)


# ---------------------------------------------------------------------------
# Etapa 1: Extracție
# ---------------------------------------------------------------------------

def _extrage(folder: str) -> DosarExtras:
    """Apelează modulul de extracție (A) și întoarce DosarExtras.

    În modul mock sau pentru dosare sintetice fără PDF-uri citește extras_mock.json;
    în modul real apelează extraction.extractor.extrage(folder).
    """
    cale = Path(folder)
    fisier_mock = cale / "extras_mock.json"

    mod = _get_mod_extractie()
    # Dacă este modul mock sau dacă dosarul este sintetic (fără fișiere PDF)
    if mod == "mock" or (fisier_mock.exists() and not any(cale.glob("*.pdf"))):
        if not fisier_mock.exists():
            raise FileNotFoundError(
                f"Fișierul extras_mock.json nu există în {cale}. "
                "Verificați calea dosarului sau schimbați MOD_EXTRACTIE=real."
            )
        import json
        with open(fisier_mock, "r", encoding="utf-8") as f:
            date = json.load(f)
        return DosarExtras(**date)

    # Modul real – delegat la modulul A
    from extraction.extractor import extrage  # type: ignore[import-untyped]
    return extrage(folder)


# ---------------------------------------------------------------------------
# Etapa 2: Construirea stării inițiale
# ---------------------------------------------------------------------------

def _creeaza_stare(folder: str, extras: DosarExtras) -> StareDosar:
    """Construiește StareDosar din DosarExtras și încarcă raport_extractie.json dacă există."""
    cale = Path(folder)
    raport_extractie: dict[str, Any] = {}
    fisier_raport = cale / "raport_extractie.json"
    if fisier_raport.exists():
        try:
            import json
            with open(fisier_raport, "r", encoding="utf-8") as f:
                raport_extractie = json.load(f) or {}
        except Exception as exc:
            logger.warning("Nu s-a putut citi raport_extractie.json din %s: %s", cale, exc)

    return StareDosar(
        dosar_folder=folder,
        extras=extras,
        raport_extractie=raport_extractie,
    )


# ---------------------------------------------------------------------------
# Etapa 3: Bucla agentului
# ---------------------------------------------------------------------------

def _obtine_planificator():
    """Instanțiază planificatorul potrivit (scriptat sau LLM) din config."""
    mod = _get_mod_agent()
    if mod == "llm":
        from agent.planner import PlanificatorLLM  # type: ignore[import-untyped]
        return PlanificatorLLM()
    else:
        from agent.planner import PlanificatorScriptat  # type: ignore[import-untyped]
        return PlanificatorScriptat()


def _executa_bucla(stare: StareDosar) -> None:
    """Execută bucla agentului: planificator decide → registry execută → trace.

    Se oprește când:
      - planificatorul decide tip='final'
      - se atinge limita de pași (escaladare automată)
    """
    from registry import apeleaza  # type: ignore[import-untyped]

    planificator = _obtine_planificator()
    max_pasi = _get_max_pasi()

    ultim_rezultat: ToolResult | None = None

    for nr_pas in range(1, max_pasi + 1):
        # 1. Planificatorul decide pasul următor
        decizie = planificator.pas_urmator(stare, ultim_rezultat)

        if decizie is None or not hasattr(decizie, "tip") or decizie.tip not in ("tool", "final"):
            raise ValueError(f"Decizie invalidă de la planificator la pasul {nr_pas}: {decizie!r}")

        if decizie.tip == "tool":
            if not getattr(decizie, "nume", None) or not str(decizie.nume).strip():
                raise ValueError(f"Decizia de tip 'tool' la pasul {nr_pas} nu are specificat un nume valid de tool: {decizie!r}")

        logger.info(
            "Pas %d: tip=%s, nume=%s, motiv=%s",
            nr_pas,
            decizie.tip,
            getattr(decizie, "nume", "-"),
            getattr(decizie, "motiv", ""),
        )

        # 2. Înregistrăm decizia în trace
        intrare_trace: dict[str, Any] = {
            "pas": nr_pas,
            "tip": decizie.tip,
            "actiune": getattr(decizie, "nume", None),
            "argumente": getattr(decizie, "argumente", {}),
            "motiv": getattr(decizie, "motiv", ""),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        # 3. Dacă planificatorul a decis „final", ieșim
        if decizie.tip == "final":
            intrare_trace["rezultat"] = "final"
            stare.trace.append(intrare_trace)
            break

        # 4. Executăm tool-ul prin registry
        rezultat = apeleaza(decizie.nume, decizie.argumente, stare)

        # 5. Salvăm rezultatul
        stare.rezultate_tools[decizie.nume] = rezultat
        ultim_rezultat = rezultat

        sumar_rezultat = ""
        if rezultat.eroare:
            sumar_rezultat = f"Eroare: {rezultat.eroare}"
        elif rezultat.date:
            if "rezultate" in rezultat.date:
                sumar_rezultat = str(rezultat.date["rezultate"])
            elif "rezultat_tco2_an" in rezultat.date:
                sumar_rezultat = f"Impact: {rezultat.date['rezultat_tco2_an']} tCO2/an"
            elif "cale_id" in rezultat.date:
                sumar_rezultat = f"{rezultat.date['cale_id']}: {rezultat.date.get('rezultat')}"
            elif "verificari" in rezultat.date:
                sumar_rezultat = f"Verificări plauzibilitate: {rezultat.date.get('nr_semnale', 0)} semnale"
            else:
                sumar_rezultat = ", ".join(f"{k}={v}" for k, v in list(rezultat.date.items())[:3])

        intrare_trace["rezultat"] = {
            "tool": rezultat.tool,
            "gasit": rezultat.gasit,
            "eroare": rezultat.eroare,
            "sumar": sumar_rezultat,
        }
        stare.trace.append(intrare_trace)

        logger.info(
            "  -> %s: gasit=%s, eroare=%s",
            rezultat.tool,
            rezultat.gasit,
            rezultat.eroare,
        )

    else:
        # Limita de pași a fost atinsă fără decizie „final"
        logger.warning(
            "Limita de %d pași atinsă pentru dosarul %s – escaladare automată.",
            max_pasi,
            stare.extras.dosar_id,
        )
        stare.escaladat = True
        stare.actiuni.append(
            f"Escaladare automată: limita de {max_pasi} pași a fost atinsă "
            f"fără verdict. Dosarul necesită analiză manuală."
        )
        stare.trace.append({
            "pas": max_pasi + 1,
            "tip": "escaladare_automata",
            "actiune": "escaladeaza",
            "motiv": f"Limita de {max_pasi} pași atinsă",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })


# ---------------------------------------------------------------------------
# Etapa 4: Verdictul
# ---------------------------------------------------------------------------

def _decide_verdict(stare: StareDosar) -> Verdict:
    """Apelează decide_verdict din motorul de reguli (C) și întoarce Verdict.

    Dacă starea e deja escaladată (limita de pași), verdictul devine
    EXCEPTIE_ESCALADARE_COMITET chiar dacă decide_verdict ar spune altceva.
    """
    from engine.verdict import decide_verdict  # type: ignore[import-untyped]

    verdict = decide_verdict(stare)

    # Suprascriem dacă escaladarea a fost forțată de buclă
    if stare.escaladat and verdict.verdict not in (
        "EXCEPTIE_ESCALADARE_COMITET",
    ):
        verdict.verdict = "EXCEPTIE_ESCALADARE_COMITET"  # type: ignore[assignment]

    return verdict


# ---------------------------------------------------------------------------
# Funcția publică: proceseaza_dosar
# ---------------------------------------------------------------------------

def proceseaza_dosar(folder: str) -> Verdict:
    """Procesează un dosar complet și întoarce Verdictul.

    Parametri:
        folder: calea către folderul dosarului (ex: 'dosare/dosar_01_complet_eligibil')

    Întoarce:
        Verdict – cu toate regulile, impactul, acțiunile și trace-ul.

    Fluxul:
        1. extrage(folder) → DosarExtras
        2. Construiește StareDosar
        3. Bucla agentului (planificator + registry)
        4. decide_verdict(stare) → Verdict
    """
    logger.info("=== Început procesare dosar: %s ===", folder)

    # 1. Extracție
    try:
        extras = _extrage(folder)
    except Exception as e:
        logger.error("Eroare la extracție pentru %s: %s", folder, e)
        raise

    logger.info(
        "Extracție completă: dosar_id=%s, CUI=%s",
        extras.dosar_id,
        extras.cui.valoare if extras.cui else "?",
    )

    # 2. Stare inițială
    stare = _creeaza_stare(folder, extras)

    # 3. Bucla agentului
    _executa_bucla(stare)

    # 4. Verdict
    verdict = _decide_verdict(stare)

    # Completăm verdictul cu informațiile din stare
    verdict.trace = stare.trace
    verdict.actiuni = stare.actiuni

    if stare.impact:
        verdict.impact_detalii = stare.impact
        verdict.impact_tco2_an = stare.impact.get("rezultat_tco2_an")

    logger.info(
        "=== Verdict dosar %s: %s (cale: %s) ===",
        verdict.dosar_id,
        verdict.verdict,
        verdict.cale_eligibilitate or "-",
    )

    return verdict
