"""Teste de integrare și non-regresie pentru reguli, categorii, unelte și evaluare."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from agent.orchestrator import proceseaza_dosar
from contracts import Camp, Chirias, DosarExtras, RezultatRegula, StareDosar, ToolResult
from engine.co2 import calculeaza_co2, CalculeazaCO2Input
from engine.reguli import (
    evalueaza_cale,
    evalueaza_conditii_generale,
    verifica_chiriasi,
    EvalueazaCaleInput,
    ConditiiGeneraleInput,
    VerificaChiriasiInput,
)
from engine.verdict import decide_verdict
from eval.run_eval import compara_verdict_cu_asteptat, ruleaza_evaluare
from extraction.categorie import stabileste_categoria
from tools.anaf import verifica_firma, VerificaFirmaInput
from tools.breeam import cauta_certificat, CautaCertificatInput


def _creeaza_extras_complet(**kwargs) -> DosarExtras:
    implicit = {
        "dosar_id": "test_dosar",
        "cui": Camp(valoare="9900000010"),
        "suma_eur": Camp(valoare=10000000),
        "cota_banca": Camp(valoare=0.6),
        "data_aprobare": Camp(valoare="2026-01-01"),
        "tara": Camp(valoare="România"),
        "adresa_cladire": Camp(valoare="Str. Test 1"),
        "suprafata_m2": Camp(valoare=10000),
        "stadiu_cladire": Camp(valoare="Finalizată, în exploatare"),
        "nr_certificat_declarat": Camp(valoare="BREEAM-TEST"),
    }
    implicit.update(kwargs)
    return DosarExtras(**implicit)


def test_stabileste_categoria_detectie():
    """Verifică detectarea categoriei pentru diverse tipuri de documente clasificate."""
    # Green buildings
    cat_bld = stabileste_categoria([
        {"tip_document": "certificat_sustenabilitate", "fisier": "BREEAM.pdf"},
        {"tip_document": "certificat_energetic", "fisier": "EPC.pdf"},
    ])
    assert cat_bld is not None
    assert any(c["categorie"] == "green_buildings" for c in cat_bld["candidati"])

    # Clean transportation
    cat_trans = stabileste_categoria([
        {"tip_document": "lista_vehicule", "fisier": "vehicule.pdf"},
        {"tip_document": "certificat_conformitate_coc", "fisier": "coc.pdf"},
    ])
    assert cat_trans is not None
    assert any(c["categorie"] == "clean_transportation" for c in cat_trans["candidati"])

    # Energy efficiency / Data center
    cat_dc = stabileste_categoria([
        {"tip_document": "raport_pue", "fisier": "raport_pue.pdf"},
    ])
    assert cat_dc is not None
    assert any(c["categorie"] == "energy_efficiency" for c in cat_dc["candidati"])


def test_reguli_precedenta_si_alternative():
    """Verifică ordinea de precedență și căile alternative în motorul de reguli."""
    # 1. G-01 pică -> NEELIGIBIL indiferent de alte căi
    extras_g01 = _creeaza_extras_complet(
        dosar_id="t1",
        tara=Camp(valoare="TaraNeeligibila999"),
    )
    stare_g01 = StareDosar(dosar_folder="dosare/dosar_01_complet_eligibil", extras=extras_g01)
    evalueaza_conditii_generale(ConditiiGeneraleInput(), stare_g01)
    assert stare_g01.reguli["G-01"].rezultat == "NU"
    v1 = decide_verdict(stare_g01)
    assert v1.verdict == "NEELIGIBIL"

    # 2. Cale alternativă: GB-01 pică (BREEAM Very Good), GB-02 NEEVALUABIL, GB-03 trece (EPC A).
    # Dosar complet (CAEN de la ANAF, aprobare prin procesul standard), ca verdictul strict să poată fi ELIGIBIL.
    extras_alt = _creeaza_extras_complet(
        dosar_id="t2",
        epc_clasa=Camp(valoare="A"),
        epc_energie_finala=Camp(valoare=80.0),
        indicatori={"aprobat_proces_standard": Camp(valoare=True)},
    )
    stare_alt = StareDosar(dosar_folder="dosare/dosar_03_breeam_insuficient_cale_epc", extras=extras_alt,
                           raport_extractie={"documente_lipsa": [], "campuri_lipsa": []})
    stare_alt.rezultate_tools["cauta_certificat"] = ToolResult(
        tool="cauta_certificat", gasit=True, date={"rating": "Very Good", "stage": "Final"}
    )
    stare_alt.rezultate_tools["verifica_firma"] = ToolResult(
        tool="verifica_firma", gasit=True, date={"date_generale": {"cod_CAEN": "6820"}}
    )
    evalueaza_conditii_generale(ConditiiGeneraleInput(), stare_alt)
    evalueaza_cale(EvalueazaCaleInput(cale_id="GB-01"), stare_alt)
    assert stare_alt.reguli["GB-01"].rezultat == "NU"

    evalueaza_cale(EvalueazaCaleInput(cale_id="GB-02"), stare_alt)
    assert stare_alt.reguli["GB-02"].rezultat == "NEEVALUABIL"

    evalueaza_cale(EvalueazaCaleInput(cale_id="GB-03"), stare_alt)
    assert stare_alt.reguli["GB-03"].rezultat == "OK"

    v2 = decide_verdict(stare_alt)
    assert v2.verdict == "ELIGIBIL"
    assert "GB-03" in (v2.cale_eligibilitate or "")


def test_impact_co2_cladire_finalizata_vs_constructie():
    """Verifică dacă impactul CO2 este calculat doar pentru clădiri finalizate."""
    # Finalizata: calcul complet
    extras_fin = _creeaza_extras_complet(
        dosar_id="t_fin",
        stadiu_cladire=Camp(valoare="Finalizată"),
        suprafata_m2=Camp(valoare=20000),
        cota_banca=Camp(valoare=0.6),
        epc_energie_finala=Camp(valoare=95.0),
    )
    stare_fin = StareDosar(dosar_folder="dosare/dosar_01_complet_eligibil", extras=extras_fin)
    res_fin = calculeaza_co2(CalculeazaCO2Input(), stare_fin)
    assert res_fin.gasit is True
    # (297 - 95) * 20000 * 0.6 * 0.25 / 1000 = 606.0
    assert res_fin.date["rezultat_tco2_an"] == 606.0

    # In constructie: nu se calculeaza
    extras_const = _creeaza_extras_complet(
        dosar_id="t_const",
        stadiu_cladire=Camp(valoare="În construcție (progres 35%)"),
        suprafata_m2=Camp(valoare=20000),
        cota_banca=Camp(valoare=0.6),
        epc_energie_finala=Camp(valoare=95.0),
    )
    stare_const = StareDosar(dosar_folder="dosare/dosar_04_constructie_certificat_interim", extras=extras_const)
    res_const = calculeaza_co2(CalculeazaCO2Input(), stare_const)
    assert res_const.gasit is False
    assert "construc" in res_const.eroare.lower()


def test_tools_anaf_si_breeam_fallback_direct_pdf(tmp_path: Path):
    """Verifică robustețea uneltelor când fișierul JSON lipsește dar există PDF-ul."""
    # Creează un folder temporar DOAR cu fișierele PDF din dosar2 (fără JSON)
    folder_test = tmp_path / "dosar_doar_pdf"
    folder_test.mkdir()
    shutil.copyfile("dosare/dosar2/BREEAM.pdf", folder_test / "BREEAM.pdf")
    shutil.copyfile("dosare/dosar2/RASPUNS_ANAF.pdf", folder_test / "RASPUNS_ANAF.pdf")

    # BREEAM.pdf fallback
    stare_breeam = StareDosar(
        dosar_folder=str(folder_test),
        extras=_creeaza_extras_complet(dosar_id="test_pdf", cui=Camp(valoare="9900000020")),
    )
    res_breeam = cauta_certificat(CautaCertificatInput(nr_certificat="BREEAM-EXEMPLU-0002"), stare_breeam)
    assert res_breeam.gasit is True
    assert res_breeam.date["rating"] == "Excellent"
    assert res_breeam.date["certificate_no"] == "BREEAM-EXEMPLU-0002"
    assert "extras direct din document" in res_breeam.sursa

    # RASPUNS_ANAF.pdf fallback
    stare_anaf = StareDosar(
        dosar_folder=str(folder_test),
        extras=_creeaza_extras_complet(dosar_id="test_pdf", cui=Camp(valoare="9900000020")),
    )
    res_anaf = verifica_firma(VerificaFirmaInput(cui="9900000020"), stare_anaf)
    assert res_anaf.gasit is True
    assert res_anaf.date["date_generale"]["cui"] == 9900000020
    assert res_anaf.date["stare_inactiv"]["statusInactivi"] is False
    assert "extras direct din document" in res_anaf.sursa


def test_evaluare_completa_toate_cele_8_dosare():
    """Verifică rularea completă a evaluatorului pe toate cele 8 dosare."""
    cod_iesire = ruleaza_evaluare("dosare")
    assert cod_iesire == 0

    # Verificare individuală pe fiecare dosar
    dosare_paths = sorted([p for p in Path("dosare").iterdir() if p.is_dir() and (p / "expected.json").exists()])
    assert len(dosare_paths) == 8

    for p in dosare_paths:
        verdict = proceseaza_dosar(str(p))
        with open(p / "expected.json", "r", encoding="utf-8") as f:
            asteptat = json.load(f)
        erori = compara_verdict_cu_asteptat(verdict, asteptat)
        assert not erori, f"Erori la dosarul {p.name}: {erori}"
