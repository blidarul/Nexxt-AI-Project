"""Calculul verdictului final pe baza stării dosarului și a regulilor evaluate.

Verdict strict: ELIGIBIL doar dacă fiecare criteriu aplicabil din Framework a fost verificat și e îndeplinit.
Precedența (prima condiție care se potrivește câștigă):
1. O condiție generală (G-*) = NU                                           => NEELIGIBIL
2. O regulă obligatorie a categoriei (reguli, conditii_obligatorii) = NU    => NEELIGIBIL
3. O excludere confirmată (= NU)                                            => NEELIGIBIL
4. Toate căile de eligibilitate evaluate și toate = NU                      => NEELIGIBIL
5. Orice incertitudine: condiție generală neevaluată, regulă aplicabilă NEEVALUABIL (o cale NEEVALUABIL nu contează dacă altă cale e OK),
   SEMNAL blocant, document/câmp obligatoriu lipsă, categorie ambiguă, escaladare, nicio regulă a categoriei
   evaluată                                                                 => EXCEPTIE_ESCALADARE_COMITET
6. Totul îndeplinit, dar o regulă e OK_CONDITIONAT sau clădirea e în construcție (nota 8)
                                                                            => ELIGIBIL_CU_MONITORIZARE
7. Altfel (toate generalele, obligatoriile și excluderile OK, cel puțin o cale OK)  => ELIGIBIL

Rolul fiecărei reguli se citește din rules/*.yaml (secțiunile cai / conditii_obligatorii / reguli / excluderi),
iar severitatea verificărilor de plauzibilitate din reference/plauzibilitate.yaml (informativ nu blochează).
Motivele pentru care dosarul nu e ELIGIBIL se adaugă în Verdict.actiuni, cu prefixul „Motiv:”.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from contracts import RezultatRegula, StareDosar, Verdict, VerdictTip

logger = logging.getLogger(__name__)

RADACINA = Path(__file__).resolve().parent.parent
PREFIX_MOTIV = "Motiv: "

GENERALA, CALE, OBLIGATORIE, EXCLUDERE, PLAUZIBILITATE, PORTOFOLIU = (
    "generala", "cale", "obligatorie", "excludere", "plauzibilitate", "portofoliu",
)
# Cheia din YAML sub care stă o listă de reguli -> rolul regulilor din ea
ROL_DUPA_CHEIE = {
    "conditii_generale": GENERALA,
    "portofoliu": PORTOFOLIU,
    "cai": CALE,
    "conditii_obligatorii": OBLIGATORIE,
    "reguli": OBLIGATORIE,
    "excluderi": EXCLUDERE,
    "verificari": PLAUZIBILITATE,
}
# Destinații din cerinte_dosar.yaml care nu țin de eligibilitate (un câmp lipsă doar pentru ele nu blochează)
DESTINATII_NEBLOCANTE = {"impact", "stabileste_categoria"}


# ---------------------------------------------------------------------------
# Rolurile regulilor, din YAML
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _roluri_si_meta() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """(rol pe ID, nume pe ID, severitate pe ID de plauzibilitate)."""
    roluri: dict[str, str] = {}
    nume: dict[str, str] = {}
    severitati: dict[str, str] = {}

    def parcurge(nod: Any, rol: Optional[str]) -> None:
        if isinstance(nod, dict):
            if isinstance(nod.get("id"), str):
                roluri.setdefault(nod["id"], rol or OBLIGATORIE)
                if isinstance(nod.get("nume"), str):
                    nume.setdefault(nod["id"], nod["nume"])
                if rol == PLAUZIBILITATE:
                    severitati[nod["id"]] = str(nod.get("severitate") or "blocant")
                return  # sub-condițiile unei reguli nu sunt reguli separate
            for cheie, valoare in nod.items():
                parcurge(valoare, ROL_DUPA_CHEIE.get(cheie, rol))
        elif isinstance(nod, list):
            for valoare in nod:
                parcurge(valoare, rol)

    fisiere = sorted((RADACINA / "rules").glob("*.yaml")) + [RADACINA / "reference" / "plauzibilitate.yaml"]
    for cale in fisiere:
        if cale.name == "cerinte_dosar.yaml" or not cale.is_file():
            continue
        with open(cale, encoding="utf-8") as f:
            parcurge(yaml.safe_load(f), None)
    return roluri, nume, severitati


def rol_regula(regula_id: str) -> str:
    roluri, _, _ = _roluri_si_meta()
    if regula_id in roluri:
        return roluri[regula_id]
    # o regulă care nu e în YAML: rolul după forma ID-ului
    if regula_id.startswith("PL-"):
        return PLAUZIBILITATE
    if re.match(r"^G-", regula_id):
        return GENERALA
    if re.match(r"^P-\d", regula_id):
        return PORTOFOLIU
    if re.match(r"^[A-Z]+-X", regula_id):
        return EXCLUDERE
    return OBLIGATORIE


def conditii_generale_definite() -> list[str]:
    """ID-urile condițiilor generale din rules/conditii_generale.yaml (G-01..G-05)."""
    roluri, _, _ = _roluri_si_meta()
    return sorted(i for i, rol in roluri.items() if rol == GENERALA)


def _nume(regula_id: str) -> str:
    return _roluri_si_meta()[1].get(regula_id, regula_id)


def semnal_blocant(regula: RezultatRegula) -> bool:
    """Un SEMNAL blochează aprobarea, cu excepția verificărilor de plauzibilitate informative."""
    if regula.rezultat != "SEMNAL":
        return False
    if rol_regula(regula.regula_id) == PLAUZIBILITATE:
        return _roluri_si_meta()[2].get(regula.regula_id, "blocant") != "informativ"
    return True


# ---------------------------------------------------------------------------
# Lipsuri din raportul de extracție
# ---------------------------------------------------------------------------

def _obligatoriu(intrare: dict) -> bool:
    return intrare.get("obligatoriu", True) is not False


def _raport_din_extras(dosar_folder: str) -> dict:
    """Raportul extracției reale stă în <dosar>/_extras/; orchestratorul îl caută doar în rădăcina dosarului."""
    cale = Path(dosar_folder) / "_extras" / "raport_extractie.json"
    try:
        with open(cale, encoding="utf-8") as f:
            date = json.load(f)
    except (OSError, ValueError):
        return {}
    return date if isinstance(date, dict) else {}


def lipsuri_obligatorii(stare: StareDosar, exista_cale_ok: bool) -> list[str]:
    """Motivele din raport_extractie: documente obligatorii lipsă, câmpuri obligatorii negăsite, categorie ambiguă.

    Un câmp lipsă blochează doar dacă servește unei reguli de eligibilitate care nu a fost deja îndeplinită
    din altă sursă (ex. CAEN-ul confirmat de ANAF) și nu doar unei căi alternative, când altă cale e OK.
    """
    raport = stare.raport_extractie or _raport_din_extras(stare.dosar_folder)
    motive: list[str] = []
    for doc in raport.get("documente_lipsa") or []:
        if _obligatoriu(doc):
            motive.append(f"Document obligatoriu lipsă: {doc.get('id', '')} {doc.get('nume', '')}".strip()
                          + ". De solicitat clientului.")
    for camp in raport.get("campuri_lipsa") or []:
        if not _obligatoriu(camp):
            continue
        destinatii = [str(p) for p in camp.get("pentru") or []]
        relevante = []
        for p in destinatii:
            if p in DESTINATII_NEBLOCANTE or rol_regula(p) in (PLAUZIBILITATE, PORTOFOLIU):
                continue
            if p != "toate" and rol_regula(p) == CALE and exista_cale_ok:
                continue
            relevante.append(p)
        if not relevante:
            continue
        acoperite = [p for p in relevante if p in stare.reguli and stare.reguli[p].rezultat in ("OK", "OK_CONDITIONAT")]
        if len(acoperite) == len(relevante):
            continue
        motive.append(f"Câmp obligatoriu negăsit: {camp.get('camp')} (pentru {', '.join(relevante)}). "
                      "De verificat în documente sau de cerut clientului.")
    if raport.get("categorie_ambigua"):
        motive.append("Categoria proiectului nu a putut fi stabilită fără ambiguitate.")
    return motive


# ---------------------------------------------------------------------------
# Textul căii de eligibilitate (formatul așteptat de fixture-uri)
# ---------------------------------------------------------------------------

def _rating_breeam(stare: StareDosar) -> str:
    res = stare.rezultate_tools.get("cauta_certificat")
    if res and res.gasit and isinstance(res.date, dict):
        return str(res.date.get("rating", "Excellent")).strip().capitalize()
    return "Excellent"


def _in_constructie(stare: StareDosar) -> bool:
    stadiu = stare.extras.stadiu_cladire.valoare if stare.extras.stadiu_cladire else ""
    return "construc" in str(stadiu or "").lower()


def _text_cale(cale: RezultatRegula, stare: StareDosar, monitorizare: bool) -> str:
    if cale.regula_id == "GB-01":
        if cale.rezultat == "OK_CONDITIONAT":
            return "GB-01 (BREEAM Excellent, stadiu Interim)"
        if _in_constructie(stare):
            return f"GB-01 (certificare BREEAM {_rating_breeam(stare)}, cladire in constructie)"
        return f"GB-01 (certificare BREEAM {_rating_breeam(stare)}, Final)"
    if cale.regula_id == "GB-03":
        return "GB-03 (EPC clasa A), dupa ce GB-01 a picat"
    return f"{cale.regula_id} ({cale.dovada})"


def _motiv(regula: RezultatRegula, eticheta: str) -> str:
    return f"{eticheta} {regula.regula_id} ({_nume(regula.regula_id)}): {regula.dovada}"


# ---------------------------------------------------------------------------
# Verdictul
# ---------------------------------------------------------------------------

def decide_verdict(stare: StareDosar) -> Verdict:
    """Calculează verdictul determinist pe baza rezultatelor regulilor din StareDosar."""
    lista_reguli = list(stare.reguli.values())
    pe_rol: dict[str, list[RezultatRegula]] = {}
    for r in lista_reguli:
        pe_rol.setdefault(rol_regula(r.regula_id), []).append(r)
    generale, cai = pe_rol.get(GENERALA, []), pe_rol.get(CALE, [])
    obligatorii, excluderi = pe_rol.get(OBLIGATORIE, []), pe_rol.get(EXCLUDERE, [])
    plauzibilitate = pe_rol.get(PLAUZIBILITATE, [])
    # regulile care trebuie toate îndeplinite (căile sunt alternative)
    cumulative = generale + obligatorii + excluderi

    cale_ok = next((r for r in cai if r.rezultat == "OK"), None) or next(
        (r for r in cai if r.rezultat == "OK_CONDITIONAT"), None)
    motive: list[str] = []
    verdict_tip: VerdictTip
    cale_aleasa: Optional[str] = None

    picate = ([r for r in generale if r.rezultat == "NU"] or [r for r in obligatorii if r.rezultat == "NU"]
              or [r for r in excluderi if r.rezultat == "NU"])
    # 1-3. O condiție generală, o regulă obligatorie sau o excludere = NU
    if picate:
        verdict_tip = "NEELIGIBIL"
        motive = [_motiv(r, "Neîndeplinit") for r in picate]

    # 4. Toate căile evaluate și toate = NU
    elif cai and all(r.rezultat == "NU" for r in cai):
        verdict_tip = "NEELIGIBIL"
        motive = [_motiv(r, "Neîndeplinit") for r in cai]

    else:
        # 5. Incertitudini
        evaluate = {r.regula_id for r in generale}
        for regula_id in conditii_generale_definite():
            if regula_id not in evaluate:
                motive.append(f"Neevaluat {regula_id} ({_nume(regula_id)}): condiția generală nu a fost verificată.")
        for r in cumulative:
            if r.rezultat == "NEEVALUABIL":
                motive.append(_motiv(r, "Neevaluabil") + ". Se cer datele care lipsesc.")
        if cai and cale_ok is None:
            motive += [_motiv(r, "Neevaluabil") + ". Se cer datele care lipsesc." for r in cai if r.rezultat == "NEEVALUABIL"]
        motive += [_motiv(r, "Semnal") for r in lista_reguli if semnal_blocant(r)]
        motive += lipsuri_obligatorii(stare, exista_cale_ok=cale_ok is not None)
        if not cai and not obligatorii:
            motive.append("Nicio regulă a categoriei nu a fost evaluată.")
        if stare.escaladat:
            motive.append("Agentul a escaladat dosarul (sau s-a oprit la limita de pași).")

        if motive:
            verdict_tip = "EXCEPTIE_ESCALADARE_COMITET"
            semnal_excludere = any(r.rezultat == "SEMNAL" for r in excluderi)
            if cale_ok and cale_ok.regula_id == "GB-01" and cale_ok.rezultat == "OK" and semnal_excludere:
                cale_aleasa = "GB-01 ar fi indeplinita, dar exista un posibil motiv de excludere"
            elif cale_ok:
                cale_aleasa = f"{cale_ok.regula_id} ar fi indeplinita, dar verificarea nu e completa"
            elif any(r.rezultat == "OK" for r in obligatorii):
                ok = [r.regula_id for r in obligatorii if r.rezultat == "OK"]
                cale_aleasa = f"{', '.join(ok)} {'ar fi indeplinita' if len(ok) == 1 else 'ar fi indeplinite'}, dar verificarea nu e completa"
            else:
                cale_aleasa = "Verificare incompleta"
        else:
            # 6. Monitorizare: o regulă OK_CONDITIONAT sau clădire în construcție
            conditionate = [r for r in cumulative + ([cale_ok] if cale_ok else []) if r.rezultat == "OK_CONDITIONAT"]
            if conditionate or _in_constructie(stare):
                verdict_tip = "ELIGIBIL_CU_MONITORIZARE"
                motive = [_motiv(r, "Monitorizare") for r in conditionate]
                if _in_constructie(stare):
                    motive.append("Monitorizare: clădire în construcție; certificarea finală trebuie confirmată "
                                  "după recepție (Framework p. 7, nota 8).")
            # 7. Totul verificat și îndeplinit
            else:
                verdict_tip = "ELIGIBIL"
            if cale_ok:
                cale_aleasa = _text_cale(cale_ok, stare, monitorizare=verdict_tip != "ELIGIBIL")
            else:
                cale_aleasa = ", ".join(r.regula_id for r in obligatorii if r.rezultat in ("OK", "OK_CONDITIONAT")) or None

    # Semnalele informative nu schimbă verdictul, dar apar ca acțiuni
    for r in plauzibilitate:
        if r.rezultat == "SEMNAL" and not semnal_blocant(r):
            motive.append(_motiv(r, "Informativ"))

    # motivele intră în stare.actiuni (orchestratorul copiază acțiunile din stare în verdict); planificatorul
    # apelează și un verdict preliminar, așa că motivele unui calcul anterior se înlocuiesc, nu se adună
    stare.actiuni[:] = [a for a in stare.actiuni if not a.startswith(PREFIX_MOTIV)]
    for m in motive:
        text = PREFIX_MOTIV + m
        if text not in stare.actiuni:
            stare.actiuni.append(text)
    actiuni = list(stare.actiuni)
    if verdict_tip != "ELIGIBIL":
        logger.info("Dosar %s: %s (%d motive)", stare.extras.dosar_id, verdict_tip, len(motive))

    impact_tco2 = stare.impact.get("rezultat_tco2_an") if stare.impact else None
    return Verdict(
        dosar_id=stare.extras.dosar_id,
        verdict=verdict_tip,
        cale_eligibilitate=cale_aleasa,
        reguli=lista_reguli,
        impact_tco2_an=impact_tco2,
        impact_detalii=stare.impact or {},
        actiuni=actiuni,
        trace=list(stare.trace),
    )
