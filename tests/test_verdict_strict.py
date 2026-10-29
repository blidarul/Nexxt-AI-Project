"""Verdict strict: ELIGIBIL doar dacă fiecare criteriu aplicabil a fost verificat și e îndeplinit.

Câte un test pentru fiecare rând din tabelul de precedență (engine/verdict.py), plus invariantul
rulat pe toate dosarele de evaluare: un dosar ELIGIBIL nu are nicio incertitudine.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import config
from agent.orchestrator import proceseaza_dosar
from contracts import Camp, DosarExtras, RezultatRegula, StareDosar, Verdict
from engine.evaluator_generic import evalueaza_regula_pe_lista
from engine.verdict import (
    CALE,
    PREFIX_MOTIV,
    conditii_generale_definite,
    decide_verdict,
    rol_regula,
    semnal_blocant,
)

GENERALE = ["G-01", "G-02", "G-03", "G-04", "G-05"]


def _stare(reguli: dict[str, str], stadiu: str = "Finalizata", raport: dict | None = None) -> StareDosar:
    extras = DosarExtras(
        dosar_id="test",
        cui=Camp(valoare="12345678"),
        suma_eur=Camp(valoare=1_000_000),
        cota_banca=Camp(valoare=0.5),
        data_aprobare=Camp(valoare="2026-01-01"),
        tara=Camp(valoare="Romania"),
        adresa_cladire=Camp(valoare="Str. Test 1"),
        suprafata_m2=Camp(valoare=5000),
        stadiu_cladire=Camp(valoare=stadiu),
        nr_certificat_declarat=Camp(valoare="CERT-1"),
    )
    stare = StareDosar(dosar_folder="dosare/test", extras=extras, raport_extractie=raport or {})
    for regula_id, rezultat in reguli.items():
        stare.reguli[regula_id] = RezultatRegula(regula_id=regula_id, rezultat=rezultat, dovada=f"dovada {regula_id}",
                                                 sursa_framework="p. 7")
    return stare


def _complet(**alte: str) -> dict[str, str]:
    """Un dosar de clădire complet: toate condițiile generale OK, GB-01 OK, excluderea GB-X1 OK."""
    return {**{g: "OK" for g in GENERALE}, "GB-01": "OK", "GB-X1": "OK", **alte}


def _motive(v: Verdict) -> list[str]:
    return [a for a in v.actiuni if a.startswith(PREFIX_MOTIV)]


# ------------------------------------------------------------------ rândurile tabelului

def test_1_conditie_generala_nu():
    v = decide_verdict(_stare(_complet(**{"G-01": "NU"})))
    assert v.verdict == "NEELIGIBIL"
    assert any("G-01" in m for m in _motive(v))


def test_2_regula_obligatorie_nu():
    reguli = {**{g: "OK" for g in GENERALE}, "CT-03": "NU", "CT-X1": "OK"}
    assert rol_regula("CT-03") != CALE
    assert decide_verdict(_stare(reguli)).verdict == "NEELIGIBIL"
    # și o condiție obligatorie a unei subcategorii cu căi (renovare)
    reguli = {**{g: "OK" for g in GENERALE}, "GB-R1": "OK", "GB-R4": "NU", "GB-X1": "OK"}
    assert decide_verdict(_stare(reguli)).verdict == "NEELIGIBIL"


def test_3_excludere_confirmata():
    v = decide_verdict(_stare(_complet(**{"GB-X1": "NU"})))
    assert v.verdict == "NEELIGIBIL"


def test_4_toate_caile_nu():
    v = decide_verdict(_stare(_complet(**{"GB-01": "NU", "GB-02": "NU", "GB-03": "NU"})))
    assert v.verdict == "NEELIGIBIL"


@pytest.mark.parametrize("reguli,raport,cuvant", [
    (_complet(**{"G-03": "NEEVALUABIL"}), None, "G-03"),
    (_complet(**{"GB-X1": "NEEVALUABIL"}), None, "GB-X1"),
    # nicio cale OK, una NEEVALUABIL -> se cer datele, nu NEELIGIBIL
    (_complet(**{"GB-01": "NU", "GB-02": "NEEVALUABIL"}), None, "GB-02"),
    (_complet(**{"GB-X1": "SEMNAL"}), None, "GB-X1"),
    (_complet(**{"PL-01": "SEMNAL"}), None, "PL-01"),
    (_complet(), {"documente_lipsa": [{"id": "D-02", "nume": "Decizia de aprobare", "obligatoriu": True}]}, "D-02"),
    # un câmp lipsă pentru o regulă care nu a fost îndeplinită din altă sursă
    (_complet(), {"campuri_lipsa": [{"camp": "epc_clasa", "pentru": ["GB-03"], "obligatoriu": True},
                                    {"camp": "pondere_suma_pentru_renovare", "pentru": ["GB-R4"], "obligatoriu": True}]},
     "pondere_suma_pentru_renovare"),
    (_complet(), {"campuri_lipsa": [{"camp": "categorie", "pentru": ["toate"], "obligatoriu": True}]}, "categorie"),
    (_complet(), {"categorie_ambigua": True}, "Categoria"),
    ({g: "OK" for g in GENERALE if g != "G-03"} | {"GB-01": "OK", "GB-X1": "OK"}, None, "G-03"),
])
def test_5_incertitudine_inseamna_exceptie(reguli, raport, cuvant):
    v = decide_verdict(_stare(reguli, raport=raport))
    assert v.verdict == "EXCEPTIE_ESCALADARE_COMITET"
    assert any(cuvant in m for m in _motive(v)), _motive(v)


def test_5_escaladat_si_fara_reguli_de_categorie():
    stare = _stare(_complet())
    stare.escaladat = True
    assert decide_verdict(stare).verdict == "EXCEPTIE_ESCALADARE_COMITET"
    v = decide_verdict(_stare({g: "OK" for g in GENERALE}))
    assert v.verdict == "EXCEPTIE_ESCALADARE_COMITET"
    assert any("Nicio regulă a categoriei" in m for m in _motive(v))


def test_5_nu_blocheaza_ce_nu_trebuie():
    # o cale NEEVALUABIL nu contează dacă altă cale e OK
    assert decide_verdict(_stare(_complet(**{"GB-02": "NEEVALUABIL"}))).verdict == "ELIGIBIL"
    # un câmp lipsă doar pentru o cale alternativă, sau acoperit de o regulă OK, nu blochează
    raport = {"campuri_lipsa": [
        {"camp": "epc_clasa", "pentru": ["GB-03"], "obligatoriu": True},
        {"camp": "cui", "pentru": ["G-02"], "obligatoriu": True},
        {"camp": "suma_eur", "pentru": ["impact"], "obligatoriu": True},
        {"camp": "data_marcare_verde", "pentru": ["G-05"], "obligatoriu": False},
    ]}
    assert decide_verdict(_stare(_complet(), raport=raport)).verdict == "ELIGIBIL"
    # un semnal de plauzibilitate informativ apare în acțiuni, dar nu blochează
    stare = _stare(_complet(**{"PL-03": "SEMNAL"}))
    assert not semnal_blocant(stare.reguli["PL-03"])
    v = decide_verdict(stare)
    assert v.verdict == "ELIGIBIL" and any(m.startswith(PREFIX_MOTIV + "Informativ PL-03") for m in v.actiuni)


def test_6_cale_conditionata_sau_constructie():
    assert decide_verdict(_stare(_complet(**{"GB-01": "OK_CONDITIONAT"}))).verdict == "ELIGIBIL_CU_MONITORIZARE"
    reguli = {**{g: "OK" for g in GENERALE}, "GB-R1": "OK", "GB-R3": "OK_CONDITIONAT", "GB-R4": "OK", "GB-X1": "OK"}
    assert decide_verdict(_stare(reguli)).verdict == "ELIGIBIL_CU_MONITORIZARE"
    v = decide_verdict(_stare(_complet(), stadiu="In constructie"))
    assert v.verdict == "ELIGIBIL_CU_MONITORIZARE" and any("construcție" in m for m in _motive(v))
    # incertitudinea are precedență față de monitorizare
    assert decide_verdict(_stare(_complet(**{"GB-01": "OK_CONDITIONAT", "G-03": "NEEVALUABIL"}))).verdict \
        == "EXCEPTIE_ESCALADARE_COMITET"


def test_7_complet_eligibil():
    v = decide_verdict(_stare(_complet()))
    assert v.verdict == "ELIGIBIL"
    assert v.cale_eligibilitate.startswith("GB-01")
    assert _motive(v) == []


def test_aplicabilitate_regula_de_camion_pe_autoturisme():
    """CT-04 (camioane) nu se aplică unei flote de autoturisme: nu pică, lipsește."""
    stare = _stare({})
    stare.extras.subcategorie = Camp(valoare="autoturism_sau_utilitara")
    regula = {"id": "CT-04", "tip": "prag", "camp": "emisii_wltp_gco2_km", "operator": "<=", "valoare": 25,
              "aplica_daca": {"tip": "camion"}}
    assert evalueaza_regula_pe_lista(regula, [{"model": "Hibrid", "emisii_wltp_gco2_km": 45}], stare) is None


# ------------------------------------------------------------------ invariantul pe toate dosarele

def _dosare_evaluare() -> list[tuple[Path, str]]:
    cazuri = []
    for folder in sorted(Path("dosare").iterdir()):
        if folder.is_dir() and (folder / "expected.json").exists():
            cazuri.append((folder, "mock"))
            if (folder / "_extras" / "dosar_extras.json").exists():
                cazuri.append((folder, "real"))
    for folder in sorted(Path("eval/dosare_reguli").iterdir()):
        if folder.is_dir() and (folder / "expected.json").exists():
            cazuri.append((folder, "mock"))
    return cazuri


def incertitudini(v: Verdict, raport: dict) -> list[str]:
    """Tot ce face un ELIGIBIL nejustificat, verificat independent de ordinea din decide_verdict."""
    rezultate = {r.regula_id: r.rezultat for r in v.reguli}
    cai = [i for i in rezultate if rol_regula(i) == CALE]
    cale_ok = any(rezultate[i] == "OK" for i in cai)
    probleme = [f"{g} neevaluat" for g in conditii_generale_definite() if g not in rezultate]
    for r in v.reguli:
        if rol_regula(r.regula_id) in ("plauzibilitate", "portofoliu"):
            if semnal_blocant(r):
                probleme.append(f"{r.regula_id}=SEMNAL")
            continue
        if r.regula_id in cai and cale_ok:
            continue
        if r.rezultat in ("NU", "NEEVALUABIL", "SEMNAL", "OK_CONDITIONAT"):
            probleme.append(f"{r.regula_id}={r.rezultat}")
    probleme += [f"document {d.get('id')}" for d in raport.get("documente_lipsa") or [] if d.get("obligatoriu", True) is not False]
    return probleme


@pytest.mark.parametrize("folder,mod", _dosare_evaluare(), ids=lambda x: str(x).replace("\\", "/"))
def test_invariant_eligibil_fara_incertitudini(folder, mod, monkeypatch):
    monkeypatch.setattr(config, "MOD_EXTRACTIE", mod)
    with redirect_stdout(io.StringIO()):
        v = proceseaza_dosar(str(folder))
    raport = {}
    if mod == "real":
        import json
        raport = json.loads((folder / "_extras" / "raport_extractie.json").read_text(encoding="utf-8"))
    if v.verdict == "ELIGIBIL":
        assert incertitudini(v, raport) == []
    else:
        # orice alt verdict își spune motivele
        assert any(a.startswith(PREFIX_MOTIV) for a in v.actiuni) or v.verdict == "NEELIGIBIL"
