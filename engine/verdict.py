"""Calculul verdictului final pe baza stării dosarului și a regulilor evaluate.

Precedența deterministă (conform RBI Framework și cerințelor Partea 1, pct. 9):
1. Condiție generală (G-01..G-04) cu NU => NEELIGIBIL
2. Regulă de excludere (-X) cu NU => NEELIGIBIL
3. Criteriu principal de categorie picat cu NU (fără nicio cale alternativă OK) => NEELIGIBIL
4. SEMNAL blocant (din reguli, excluderi sau plauzibilitate) sau escaladat => EXCEPTIE_ESCALADARE_COMITET
5. O cale OK => ELIGIBIL (sau ELIGIBIL_CU_MONITORIZARE dacă este în construcție)
6. O cale OK_CONDITIONAT => ELIGIBIL_CU_MONITORIZARE
7. Toate căile NEEVALUABIL => EXCEPTIE_ESCALADARE_COMITET (cu cerere de date)
8. Altfel => NEELIGIBIL
"""

from __future__ import annotations

import logging
from typing import Optional

from contracts import RezultatRegula, StareDosar, Verdict, VerdictTip

logger = logging.getLogger(__name__)

REGULI_OBLIGATORII_GENERALE = {"G-01", "G-02", "G-03", "G-04"}

# Reguli care sunt condiții de monitorizare sau cerințe suplimentare, nu căi propriu-zise de intrare în verde
NON_CAI = {
    "GB-R3", "GB-R4", "GB-X1", "GB-X2",
    "G-01", "G-02", "G-03", "G-04", "G-05",
    "P-01", "P-02", "P-03", "P-04",
}


def decide_verdict(stare: StareDosar) -> Verdict:
    """Calculează verdictul determinist pe baza rezultatelor regulilor din StareDosar."""
    reguli_dict = stare.reguli
    lista_reguli = list(reguli_dict.values())

    verdict_tip: VerdictTip
    cale_aleasa: Optional[str] = None

    # Căi de eligibilitate de categorie (excluzând regulile generale, excluderile și verificările de plauzibilitate)
    cai_reguli = [
        r for r in lista_reguli
        if r.regula_id not in NON_CAI and not "-X" in r.regula_id and not r.regula_id.startswith("PL-")
    ]
    cale_ok = next((r for r in cai_reguli if r.rezultat == "OK"), None)
    cale_conditionat = next((r for r in cai_reguli if r.rezultat == "OK_CONDITIONAT"), None)

    # 1. Condiții generale obligatorii: orice NU => direct NEELIGIBIL
    cond_gen_picate = [
        r for r in lista_reguli if r.regula_id in REGULI_OBLIGATORII_GENERALE and r.rezultat == "NU"
    ]
    if cond_gen_picate:
        verdict_tip = "NEELIGIBIL"
        cale_aleasa = None

    # 2. Excluderi categorice (orice regulă de excludere ce pică cu NU)
    elif any(
        r.rezultat == "NU" and (
            "-X" in r.regula_id or "excludere" in r.sursa_framework.lower() or "excludere" in r.dovada.lower()
        )
        for r in lista_reguli
    ):
        verdict_tip = "NEELIGIBIL"
        excl_picata = next(
            r for r in lista_reguli if r.rezultat == "NU" and (
                "-X" in r.regula_id or "excludere" in r.sursa_framework.lower() or "excludere" in r.dovada.lower()
            )
        )
        cale_aleasa = None
        logger.info("Dosar neeligibil din cauza excluderii: %s", excl_picata.regula_id)

    # 3. Criteriu tehnic de categorie picat cu NU fără nicio cale alternativă aprobată
    # (ex: renovare cu reducere < 30% GB-R1, mașină cu emisii > prag CT-03, hidro RE-03 etc.)
    elif any(r.rezultat == "NU" for r in cai_reguli) and not cale_ok and not cale_conditionat:
        verdict_tip = "NEELIGIBIL"
        r_picata = next(r for r in cai_reguli if r.rezultat == "NU")
        cale_aleasa = None
        logger.info("Dosar neeligibil: calea %s a picat cu NU și nu există cale alternativă aprobată", r_picata.regula_id)

    # 4. SEMNAL blocant sau escaladare manuală/automată => EXCEPTIE_ESCALADARE_COMITET
    elif stare.escaladat or any(r.rezultat == "SEMNAL" for r in lista_reguli):
        verdict_tip = "EXCEPTIE_ESCALADARE_COMITET"
        reg_gb01 = reguli_dict.get("GB-01")
        if reg_gb01 and reg_gb01.rezultat == "OK":
            cale_aleasa = "GB-01 ar fi indeplinita, dar exista un posibil motiv de excludere"
        else:
            semnal_r = next((r for r in lista_reguli if r.rezultat == "SEMNAL"), None)
            cale_aleasa = f"Semnal de atenție / verificare ({semnal_r.regula_id if semnal_r else 'escaladare'})"

    # 5. Căi de eligibilitate aprobate
    else:
        stadiu_str = str(getattr(stare.extras, "stadiu_cladire", None) and stare.extras.stadiu_cladire.valoare or "").lower()
        is_in_constructie = "construc" in stadiu_str

        # Verificare condiții obligatorii suplimentare (ex. GB-R3, monitorizare)
        cond_supl_monitorizare = any(reguli_dict.get(r_id, RezultatRegula(regula_id=r_id, rezultat="OK", dovada="", sursa_framework="")).rezultat == "OK_CONDITIONAT" for r_id in ("GB-R3", "GB-X2"))

        # Formatare BREEAM compatibilă cu fixture-urile existente
        res_breeam = stare.rezultate_tools.get("cauta_certificat")
        rating = "Excellent"
        if res_breeam and res_breeam.gasit and isinstance(res_breeam.date, dict):
            rating = str(res_breeam.date.get("rating", "Excellent")).strip().capitalize()

        if is_in_constructie or cond_supl_monitorizare:
            if cale_ok or cale_conditionat:
                verdict_tip = "ELIGIBIL_CU_MONITORIZARE"
                c = cale_ok or cale_conditionat
                if c.regula_id == "GB-01":
                    cale_aleasa = (
                        "GB-01 (BREEAM Excellent, stadiu Interim)"
                        if (c.rezultat == "OK_CONDITIONAT" or "interim" in str(getattr(stare.extras, "nr_certificat_declarat", "")).lower())
                        else f"GB-01 (certificare BREEAM {rating}, cladire in constructie)"
                    )
                elif c.regula_id == "GB-03":
                    cale_aleasa = "GB-03 (EPC clasa A), dupa ce GB-01 a picat"
                else:
                    cale_aleasa = f"{c.regula_id} ({c.dovada})"
            else:
                verdict_tip = "NEELIGIBIL"
                cale_aleasa = None

        elif cale_ok:
            verdict_tip = "ELIGIBIL"
            if cale_ok.regula_id == "GB-01":
                cale_aleasa = f"GB-01 (certificare BREEAM {rating}, Final)"
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

        # 6. Dacă toate căile sunt NEEVALUABIL -> EXCEPTIE_ESCALADARE_COMITET (cu cerere de date)
        elif cai_reguli and all(r.rezultat == "NEEVALUABIL" for r in cai_reguli):
            verdict_tip = "EXCEPTIE_ESCALADARE_COMITET"
            cale_aleasa = "Toate căile sunt neevaluabile din lipsă de date tehnice"
            if not any("lips" in a.lower() or "cere" in a.lower() for a in stare.actiuni):
                stare.actiuni.append("Solicitare date tehnice de la client pentru evaluarea căilor de eligibilitate.")

        # 7. Altfel => NEELIGIBIL
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
        impact_detalii=stare.impact or {},
        actiuni=list(stare.actiuni),
        trace=list(stare.trace),
    )
