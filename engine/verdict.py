"""Calculul verdictului final pe baza stării dosarului și a regulilor evaluate."""

from __future__ import annotations

import logging
from typing import Optional

from contracts import RezultatRegula, StareDosar, Verdict, VerdictTip

logger = logging.getLogger(__name__)

# Reguli obligatorii (care, dacă pică cu NU, duc direct la NEELIGIBIL)
REGULI_OBLIGATORII = {"G-01", "G-02", "G-03", "G-04"}
CAI_ELIGIBILITATE = ["GB-01", "GB-02", "GB-03", "GB-04"]


def decide_verdict(stare: StareDosar) -> Verdict:
    """Calculează verdictul determinist pe baza rezultatelor regulilor din StareDosar.

    Precedența:
      1. Orice regulă obligatorie cu NU => NEELIGIBIL
      2. SEMNAL sau escaladat => EXCEPTIE_ESCALADARE_COMITET
      3. Cale eligibilă cu OK => ELIGIBIL
      4. Cale eligibilă cu OK_CONDITIONAT => ELIGIBIL_CU_MONITORIZARE
      5. Altfel => NEELIGIBIL
    """
    reguli_dict = stare.reguli
    lista_reguli = list(reguli_dict.values())

    verdict_tip: VerdictTip
    cale_aleasa: Optional[str] = None

    # 1. Verificare reguli obligatorii: orice NU => NEELIGIBIL
    reguli_obligatorii_picate = [
        r for r in lista_reguli if r.regula_id in REGULI_OBLIGATORII and r.rezultat == "NU"
    ]
    if reguli_obligatorii_picate:
        verdict_tip = "NEELIGIBIL"
        cale_aleasa = None

    # 2. SEMNAL sau escaladare => EXCEPTIE_ESCALADARE_COMITET
    elif stare.escaladat or any(r.rezultat == "SEMNAL" for r in lista_reguli):
        verdict_tip = "EXCEPTIE_ESCALADARE_COMITET"
        reg_gb01 = reguli_dict.get("GB-01")
        if reg_gb01 and reg_gb01.rezultat == "OK":
            cale_aleasa = "GB-01 ar fi indeplinita, dar exista un posibil motiv de excludere"
        else:
            cale_aleasa = None

    # 3 & 4. Căi alternative de eligibilitate
    else:
        cale_ok = next((r for r in [reguli_dict.get(c) for c in CAI_ELIGIBILITATE] if r and r.rezultat == "OK"), None)
        cale_conditionat = next((r for r in [reguli_dict.get(c) for c in CAI_ELIGIBILITATE] if r and r.rezultat == "OK_CONDITIONAT"), None)

        if cale_ok:
            verdict_tip = "ELIGIBIL"
            if cale_ok.regula_id == "GB-01":
                cale_aleasa = "GB-01 (certificare BREEAM Excellent, Final)"
            elif cale_ok.regula_id == "GB-03":
                cale_aleasa = "GB-03 (EPC clasa A), dupa ce GB-01 a picat"
            else:
                cale_aleasa = f"{cale_ok.regula_id} ({cale_ok.dovada})"
        elif cale_conditionat:
            verdict_tip = "ELIGIBIL_CU_MONITORIZARE"
            if cale_conditionat.regula_id == "GB-01":
                cale_aleasa = "GB-01 (BREEAM Excellent, stadiu Interim)"
            else:
                cale_aleasa = f"{cale_conditionat.regula_id} ({cale_conditionat.dovada})"
        else:
            verdict_tip = "NEELIGIBIL"
            cale_aleasa = None

    impact_tco2 = stare.impact.get("rezultat_tco2_an") if stare.impact else None

    return Verdict(
        dosar_id=stare.extras.dosar_id,
        verdict=verdict_tip,
        cale_eligibilitate=cale_aleasa,
        reguli=lista_reguli,
        impact_tco2_an=impact_tco2,
        impact_detalii=stare.impact,
        actiuni=list(stare.actiuni),
        trace=list(stare.trace),
    )
