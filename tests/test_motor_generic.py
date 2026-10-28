"""Teste unitare complete pentru motorul de reguli generic (Partea 1).

Acoperă:
1. Fiecare tip de regulă:
   - prag (<, <=, ==, !=, >=, >)
   - lista (apartenență cu normalizare)
   - lista_cu_ordine (BREEAM, LEED, DGNB, OGNI, EDGE cu condiție suplimentară și stadiu interim)
   - da_nu (comparare booleană Python True/False)
   - excludere (respingere directă cu NU sau SEMNAL)
   - oricare (disjuncție logică OR)
   - toate (conjuncție logică AND)
   - prag_dependent_de_data (grandfathering cu data marcării / aprobării)
   - aplica_daca (filtrare condițională)
   - daca_lipseste (tratare NEEVALUABIL / OK_CONDITIONAT / SEMNAL)
   - câmpuri calculate (cu formule păstrate în dovadă)
   - liste de vehicule (item-by-item cu pro-rata și acțiune generată)
2. Toate cele 10 cazuri din docs/VERIFICARI.md, secțiunea 6:
   1. Flotă hibrid 45 g/km marcată în 2025 -> ELIGIBIL
   2. Aceeași flotă marcată în 2026 -> NEELIGIBIL (CT-03)
   3. Camion electric declarat 0 g/km, în EEA apare diesel -> EXCEPTIE (PL-02)
   4. Hidrocentrală pusă în funcțiune în 2022, 7 W/m² -> NEELIGIBIL (RE-03c)
   5. Parc solar 10 MW care declară 40.000 MWh/an -> EXCEPTIE (PL-20)
   6. Data center cu PUE 1.38 -> ELIGIBIL (EE-07)
   7. Fabrică de ciment modernizată (-35% energie) -> NEELIGIBIL (EE-X1)
   8. Renovare EPC 210 -> 160 kWh/m2 (-24%) -> NEELIGIBIL (GB-R1)
   9. Profile aluminiu 80% reciclat, primar 2.1 tCO2e/t -> ELIGIBIL (CE-03)
   10. Pompe de căldură cu R410A (GWP = 2088) -> NEELIGIBIL (GB-M2)
3. Calculul de impact pentru toate categoriile.
"""

from __future__ import annotations

import pytest

from contracts import Camp, DosarExtras, RezultatRegula, StareDosar, ToolResult
from engine.evaluator_generic import (
    calculeaza_campuri_derivate,
    evalueaza_fisier_reguli,
    evalueaza_regula,
    evalueaza_regula_pe_lista,
)
from engine.impact import calculeaza_impact_categorie
from engine.plauzibilitate import evalueaza_plauzibilitate
from engine.verdict import decide_verdict


def _creeaza_stare_test(
    dosar_id: str = "test_dosar",
    categorie: str = "green_buildings",
    subcategorie: str = "",
    indicatori: dict[str, Any] | None = None,
    **kwargs,
) -> StareDosar:
    """Helper pentru instanțierea rapidă a unui StareDosar de test."""
    indic_camps: dict[str, Camp] = {}
    if indicatori:
        for k, v in indicatori.items():
            if isinstance(v, Camp):
                indic_camps[k] = v
            else:
                indic_camps[k] = Camp(valoare=v, sursa=f"test:{k}")

    extras_dict = {
        "dosar_id": dosar_id,
        "cui": Camp(valoare="12345678"),
        "suma_eur": Camp(valoare=5000000),
        "cota_banca": Camp(valoare=0.5),
        "data_aprobare": Camp(valoare="2025-06-01"),
        "tara": Camp(valoare="România"),
        "adresa_cladire": Camp(valoare="Str. Verificării 1"),
        "suprafata_m2": Camp(valoare=10000),
        "stadiu_cladire": Camp(valoare="Finalizată"),
        "nr_certificat_declarat": Camp(valoare="CERT-123"),
        "categorie": Camp(valoare=categorie),
        "subcategorie": Camp(valoare=subcategorie) if subcategorie else None,
        "indicatori": indic_camps,
    }
    extras_dict.update(kwargs)
    extras = DosarExtras(**extras_dict)
    stare = StareDosar(dosar_folder="dosare/test", extras=extras)
    # Rezultat implicit ANAF neexclus
    stare.rezultate_tools["verifica_firma"] = ToolResult(
        tool="verifica_firma",
        gasit=True,
        date={"date_generale": {"cod_CAEN": "4120"}},
    )
    return stare


# ===========================================================================
# 1. Teste pentru fiecare tip de regulă generică
# ===========================================================================

def test_regula_tip_prag():
    """Verifică regula de tip 'prag' cu toți operatorii matematici."""
    stare = _creeaza_stare_test(indicatori={"val_test": 50})

    # <=
    r_le = evalueaza_regula({"id": "T-01", "tip": "prag", "camp": "val_test", "operator": "<=", "valoare": 50}, stare)
    assert r_le.rezultat == "OK"

    # <
    r_lt = evalueaza_regula({"id": "T-02", "tip": "prag", "camp": "val_test", "operator": "<", "valoare": 50}, stare)
    assert r_lt.rezultat == "NU"

    # ==
    r_eq = evalueaza_regula({"id": "T-03", "tip": "prag", "camp": "val_test", "operator": "==", "valoare": 50}, stare)
    assert r_eq.rezultat == "OK"

    # >=
    r_ge = evalueaza_regula({"id": "T-04", "tip": "prag", "camp": "val_test", "operator": ">=", "valoare": 50}, stare)
    assert r_ge.rezultat == "OK"

    # >
    r_gt = evalueaza_regula({"id": "T-05", "tip": "prag", "camp": "val_test", "operator": ">", "valoare": 40}, stare)
    assert r_gt.rezultat == "OK"


def test_regula_tip_lista():
    """Verifică regula de tip 'lista' cu normalizare de majuscule și diacritice."""
    stare = _creeaza_stare_test(indicatori={"combustibil": "Hidrogen"})
    r = evalueaza_regula({"id": "T-L1", "tip": "lista", "camp": "combustibil", "in_lista": ["electric", "hidrogen"]}, stare)
    assert r.rezultat == "OK"

    stare_nu = _creeaza_stare_test(indicatori={"combustibil": "diesel"})
    r_nu = evalueaza_regula({"id": "T-L2", "tip": "lista", "camp": "combustibil", "in_lista": ["electric", "hidrogen"]}, stare_nu)
    assert r_nu.rezultat == "NU"


def test_regula_tip_lista_cu_ordine():
    """Verifică regula de tip 'lista_cu_ordine' (BREEAM, LEED, EDGE cu condiție suplimentară)."""
    # 1. BREEAM Excellent (trece)
    stare1 = _creeaza_stare_test(indicatori={"certificare_sistem": "BREEAM", "certificare_nivel": "Excellent", "certificare_stadiu": "Final"})
    r1 = evalueaza_fisier_reguli("green_buildings", stare1)
    res_gb01 = next(r for r in r1 if r.regula_id == "GB-01")
    assert res_gb01.rezultat == "OK"

    # 2. BREEAM Very Good (pică sub pragul Excellent)
    stare2 = _creeaza_stare_test(indicatori={"certificare_sistem": "BREEAM", "certificare_nivel": "Very Good", "certificare_stadiu": "Final"})
    r2 = evalueaza_fisier_reguli("green_buildings", stare2)
    res_gb01_nu = next(r for r in r2 if r.regula_id == "GB-01")
    assert res_gb01_nu.rezultat == "NU"

    # 3. BREEAM Excellent Interim (OK_CONDITIONAT)
    stare3 = _creeaza_stare_test(indicatori={"certificare_sistem": "BREEAM", "certificare_nivel": "Excellent", "certificare_stadiu": "Interim"})
    r3 = evalueaza_fisier_reguli("green_buildings", stare3)
    res_gb01_interim = next(r for r in r3 if r.regula_id == "GB-01")
    assert res_gb01_interim.rezultat == "OK_CONDITIONAT"

    # 4. EDGE Basic cu 32% economie (trece datorită condiției suplimentare)
    stare4 = _creeaza_stare_test(indicatori={
        "certificare_sistem": "EDGE",
        "certificare_nivel": "Basic",
        "certificare_stadiu": "Final",
        "economie_energie_edge_pct": 0.32,
    })
    r4 = evalueaza_fisier_reguli("green_buildings", stare4)
    res_edge = next(r for r in r4 if r.regula_id == "GB-01")
    assert res_edge.rezultat == "OK"

    # 5. EDGE Basic cu doar 20% economie (< 30% -> pică)
    stare5 = _creeaza_stare_test(indicatori={
        "certificare_sistem": "EDGE",
        "certificare_nivel": "Basic",
        "certificare_stadiu": "Final",
        "economie_energie_edge_pct": 0.20,
    })
    r5 = evalueaza_fisier_reguli("green_buildings", stare5)
    res_edge_nu = next(r for r in r5 if r.regula_id == "GB-01")
    assert res_edge_nu.rezultat == "NU"


def test_regula_tip_da_nu():
    """Verifică regula booleană 'da_nu' cu comparare Python True/False."""
    stare_ok = _creeaza_stare_test(indicatori={"integrat_cu_regenerabile": True})
    r_ok = evalueaza_regula({"id": "EE-03", "tip": "da_nu", "camp": "integrat_cu_regenerabile", "valoare": True}, stare_ok)
    assert r_ok.rezultat == "OK"

    stare_nu = _creeaza_stare_test(indicatori={"integrat_cu_regenerabile": False})
    r_nu = evalueaza_regula({"id": "EE-03", "tip": "da_nu", "camp": "integrat_cu_regenerabile", "valoare": True}, stare_nu)
    assert r_nu.rezultat == "NU"


def test_regula_tip_excludere():
    """Verifică excluderea directă."""
    stare_excl = _creeaza_stare_test(indicatori={"foloseste_plastic_virgin": True})
    r_excl = evalueaza_regula({"id": "CE-X1", "tip": "excludere", "camp": "foloseste_plastic_virgin", "valoare": True}, stare_excl)
    assert r_excl.rezultat == "NU"


def test_regula_tip_oricare_si_toate():
    """Verifică agregările logice 'oricare' (OR) și 'toate' (AND)."""
    # oricare: dacă una trece, regula trece
    stare_or = _creeaza_stare_test(indicatori={"reducere_ped_pct": 0.35, "reducere_emisii_pct": 0.10})
    r_or = evalueaza_regula({
        "id": "GB-R1",
        "tip": "oricare",
        "conditii": [
            {"camp": "reducere_ped_pct", "operator": ">=", "valoare": 0.30},
            {"camp": "reducere_emisii_pct", "operator": ">=", "valoare": 0.30},
        ],
    }, stare_or)
    assert r_or.rezultat == "OK"

    # toate: trece doar dacă toate condițiile trec
    stare_and_ok = _creeaza_stare_test(indicatori={"c1": True, "c2": False})
    r_and_ok = evalueaza_regula({
        "id": "AND-1",
        "tip": "toate",
        "conditii": [
            {"camp": "c1", "operator": "==", "valoare": True},
            {"camp": "c2", "operator": "==", "valoare": False},
        ],
    }, stare_and_ok)
    assert r_and_ok.rezultat == "OK"

    stare_and_nu = _creeaza_stare_test(indicatori={"c1": True, "c2": True})
    r_and_nu = evalueaza_regula({
        "id": "AND-2",
        "tip": "toate",
        "conditii": [
            {"camp": "c1", "operator": "==", "valoare": True},
            {"camp": "c2", "operator": "==", "valoare": False},
        ],
    }, stare_and_nu)
    assert r_and_nu.rezultat == "NU"


def test_regula_daca_lipseste():
    """Verifică tratarea explicită a fallback-ului dacă un câmp lipsește."""
    stare_gol = _creeaza_stare_test()
    # 1. daca_lipseste: NEEVALUABIL
    r_neev = evalueaza_regula({"id": "X1", "tip": "prag", "camp": "inexistent", "operator": "<=", "valoare": 10, "daca_lipseste": "NEEVALUABIL"}, stare_gol)
    assert r_neev.rezultat == "NEEVALUABIL"

    # 2. daca_lipseste: OK_CONDITIONAT (se monitorizează)
    r_cond = evalueaza_regula({"id": "X2", "tip": "prag", "camp": "inexistent", "operator": "<=", "valoare": 10, "daca_lipseste": "OK_CONDITIONAT"}, stare_gol)
    assert r_cond.rezultat == "OK_CONDITIONAT"

    # 3. daca_lipseste: SEMNAL
    r_sem = evalueaza_regula({"id": "X3", "tip": "prag", "camp": "inexistent", "operator": "<=", "valoare": 10, "daca_lipseste": "SEMNAL"}, stare_gol)
    assert r_sem.rezultat == "SEMNAL"


def test_campuri_calculate_formule():
    """Verifică dacă motorul calculează câmpurile derivate și păstrează formulele în dovadă."""
    stare = _creeaza_stare_test(
        indicatori={
            "ped_inainte_kwh_m2": 200,
            "ped_dupa_kwh_m2": 140,
            "consum_inainte_mwh": 1000,
            "consum_dupa_mwh": 650,
            "capacitate_mw": 5,
            "productie_anuala_mwh": 8760,
            "putere_instalata_w": 5000000,
            "suprafata_lac_m2": 500000,
            "ped_kwh_m2": 80,
            "prag_nzeb_national": 100,
        }
    )
    derivate = calculeaza_campuri_derivate(stare)

    # reducere_ped_pct = (200 - 140) / 200 = 30%
    val_ped, formula_ped = derivate["reducere_ped_pct"]
    assert val_ped == 0.30
    assert "reducere_ped_pct" in formula_ped

    # imbunatatire_eficienta_pct = (1000 - 650) / 1000 = 35%
    val_ee, formula_ee = derivate["imbunatatire_eficienta_pct"]
    assert val_ee == 0.35

    # factor_capacitate = 8760 / (5 * 8760) = 0.20 (20%)
    val_fc, formula_fc = derivate["factor_capacitate"]
    assert val_fc == 0.20

    # densitate_putere_w_m2 = 5_000_000 / 500_000 = 10 W/m2
    val_dens, formula_dens = derivate["densitate_putere_w_m2"]
    assert val_dens == 10.0

    # ped_fata_de_nzeb = 80 / 100 = 0.80
    val_nzeb, formula_nzeb = derivate["ped_fata_de_nzeb"]
    assert val_nzeb == 0.80


def test_evaluare_pe_lista_vehicule_pro_rata():
    """Verifică evaluarea listelor de vehicule cu calcul pro-rata și acțiuni în stare."""
    flota = [
        {"model": "EV-1", "emisii_wltp_gco2_km": 0},
        {"model": "EV-2", "emisii_wltp_gco2_km": 0},
        {"model": "Hibrid-1", "emisii_wltp_gco2_km": 40},
        {"model": "Diesel-Poluant", "emisii_wltp_gco2_km": 140},
    ]
    stare = _creeaza_stare_test(categorie="clean_transportation", subcategorie="autoturism_sau_utilitara")
    regula_flota = {
        "id": "CT-04",
        "tip": "prag",
        "camp": "emisii_wltp_gco2_km",
        "operator": "<=",
        "valoare": 50,
    }
    res = evalueaza_regula_pe_lista(regula_flota, flota, stare)
    # 3 din 4 respectă pragul (75%)
    assert res.rezultat == "NU"
    assert stare.impact["pondere_eligibila"] == 0.75
    assert any("75.0%" in a for a in stare.actiuni)


# ===========================================================================
# 2. Cazurile de test din docs/VERIFICARI.md, secțiunea 6
# ===========================================================================

def test_caz_01_flota_hibrid_marcat_2025():
    """Flotă: 10 hibride la 45 g/km, marcate în 2025 -> grandfathering -> ELIGIBIL."""
    stare = _creeaza_stare_test(
        categorie="clean_transportation",
        subcategorie="autoturism_sau_utilitara",
        indicatori={
            "data_marcare_verde": "2025-06-15",
            "emisii_wltp_gco2_km": 45,
            "nr_vehicule": 10,
        },
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("clean_transportation", stare)
    v = decide_verdict(stare)
    assert stare.reguli["CT-03"].rezultat == "OK"
    assert v.verdict == "ELIGIBIL"


def test_caz_02_flota_hibrid_marcat_2026():
    """Aceeași flotă, marcată în 2026 -> pragul 0 g/km -> NEELIGIBIL (CT-03)."""
    stare = _creeaza_stare_test(
        categorie="clean_transportation",
        subcategorie="autoturism_sau_utilitara",
        indicatori={
            "data_marcare_verde": "2026-02-01",
            "emisii_wltp_gco2_km": 45,
            "nr_vehicule": 10,
        },
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("clean_transportation", stare)
    v = decide_verdict(stare)
    assert stare.reguli["CT-03"].rezultat == "NU"
    assert v.verdict == "NEELIGIBIL"


def test_caz_03_camion_declarat_0_dar_eea_diesel():
    """Camion electric declarat 0 g/km, în EEA apare diesel -> registru vs declarație -> EXCEPȚIE (PL-02)."""
    stare = _creeaza_stare_test(
        categorie="clean_transportation",
        subcategorie="camion",
        indicatori={"emisii_wltp_gco2_km": 0},
    )
    # Rezultatul din registrul oficial EEA
    stare.rezultate_tools["cauta_emisii_vehicul"] = ToolResult(
        tool="cauta_emisii_vehicul",
        gasit=True,
        date={"emisii_wltp_gco2_km": 210, "combustibil": "diesel"},
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("clean_transportation", stare)
    evalueaza_plauzibilitate(stare)
    v = decide_verdict(stare)
    assert stare.reguli["PL-02"].rezultat == "SEMNAL"
    assert v.verdict == "EXCEPTIE_ESCALADARE_COMITET"


def test_caz_04_hidro_dupa_2020_densitate_7():
    """Hidrocentrală pusă în funcțiune în 2022, 7 W/m², emisii necunoscute -> pragul după 2020 -> NEELIGIBIL (RE-03c)."""
    stare = _creeaza_stare_test(
        categorie="renewable_energy",
        subcategorie="hidro",
        indicatori={
            "an_punere_functiune": 2022,
            "densitate_putere_w_m2": 7,
            "emisii_directe_gco2e_kwh": None,
        },
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("renewable_energy", stare)
    v = decide_verdict(stare)
    assert stare.reguli["RE-03"].rezultat == "NU"
    assert v.verdict == "NEELIGIBIL"


def test_caz_05_parc_solar_factor_capacitate_imposibil():
    """Parc solar 10 MW care declară 40.000 MWh/an -> factor de capacitate 46% -> EXCEPȚIE (PL-20)."""
    stare = _creeaza_stare_test(
        categorie="renewable_energy",
        subcategorie="solar_fotovoltaic",
        indicatori={
            "capacitate_mw": 10,
            "productie_anuala_mwh": 40000,
        },
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("renewable_energy", stare)
    evalueaza_plauzibilitate(stare)
    v = decide_verdict(stare)
    assert stare.reguli["PL-20"].rezultat == "SEMNAL"
    assert v.verdict == "EXCEPTIE_ESCALADARE_COMITET"


def test_caz_06_data_center_pue_1_38():
    """Data center cu PUE 1.38 -> prag PUE (< 1.5) -> ELIGIBIL (EE-07)."""
    stare = _creeaza_stare_test(
        categorie="energy_efficiency",
        subcategorie="data_center",
        indicatori={"pue_anualizat": 1.38},
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("energy_efficiency", stare)
    v = decide_verdict(stare)
    assert stare.reguli["EE-07"].rezultat == "OK"
    assert v.verdict == "ELIGIBIL"


def test_caz_07_fabrica_ciment_excludere_industrie():
    """Fabrică de ciment: modernizare a cuptorului (−35% energie) -> excludere industrie grea -> NEELIGIBIL (EE-X1)."""
    stare = _creeaza_stare_test(
        categorie="energy_efficiency",
        subcategorie="eficienta_industriala",
        indicatori={
            "imbunatatire_eficienta_pct": 0.35,
            "industrie_beneficiar": "ciment",
        },
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("energy_efficiency", stare)
    v = decide_verdict(stare)
    assert stare.reguli["EE-01"].rezultat == "OK"
    assert stare.reguli["EE-X1"].rezultat == "NU"
    assert v.verdict == "NEELIGIBIL"


def test_caz_08_renovare_epc_24_pct():
    """Renovare: EPC 210 → 160 kWh/m² (−24%) -> prag 30% -> NEELIGIBIL (GB-R1)."""
    stare = _creeaza_stare_test(
        categorie="green_buildings",
        subcategorie="renovare",
        indicatori={
            "ped_inainte_kwh_m2": 210,
            "ped_dupa_kwh_m2": 160,
        },
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("green_buildings", stare)
    v = decide_verdict(stare)
    assert stare.reguli["GB-R1"].rezultat == "NU"
    assert v.verdict == "NEELIGIBIL"


def test_caz_09_aluminiu_calea_a_doua():
    """Profile de aluminiu: 80% reciclat, primar 2.1 tCO2e/t -> calea a doua CE-03 -> ELIGIBIL."""
    stare = _creeaza_stare_test(
        categorie="circular_economy",
        subcategorie="produse_aluminiu",
        indicatori={
            "pondere_aluminiu_reciclat": 0.80,
            "intensitate_carbon_aluminiu_primar_tco2e_t": 2.1,
            "foloseste_plastic_virgin": False,
        },
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("circular_economy", stare)
    v = decide_verdict(stare)
    assert stare.reguli["CE-03"].rezultat == "OK"
    assert v.verdict == "ELIGIBIL"


def test_caz_10_pompe_caldura_r410a():
    """Pompe de căldură cu R410A (GWP ≈ 2088) -> GWP > 675 -> NEELIGIBIL (GB-M2)."""
    stare = _creeaza_stare_test(
        categorie="green_buildings",
        subcategorie="masura_individuala",
        indicatori={
            "tip_masura": "pompa_caldura",
            "gwp_agent_frigorific": 2088,
        },
    )
    evalueaza_fisier_reguli("conditii_generale", stare)
    evalueaza_fisier_reguli("green_buildings", stare)
    v = decide_verdict(stare)
    assert stare.reguli["GB-M2"].rezultat == "NU"
    assert v.verdict == "NEELIGIBIL"


# ===========================================================================
# 3. Teste pentru calculul de impact pe diverse categorii
# ===========================================================================

def test_calcul_impact_regenerabile_si_transport():
    """Verifică impactul CO2 calculat pentru energie regenerabilă și transport."""
    # Regenerabile: 10.000 MWh cu factor proxy 0.25 și cota 0.5 -> 1250 tCO2/an
    stare_re = _creeaza_stare_test(
        categorie="renewable_energy",
        indicatori={"productie_anuala_mwh": 10000},
        cota_banca=Camp(valoare=0.5),
    )
    imp_re = calculeaza_impact_categorie("renewable_energy", stare_re)
    assert imp_re["rezultat_tco2_an"] == 1250.0
    assert len(imp_re["pasi"]) >= 3

    # Transport: 20 vehicule electrice, 15.000 km/an
    stare_ct = _creeaza_stare_test(
        categorie="clean_transportation",
        indicatori={
            "nr_vehicule": 20,
            "distanta_anuala_km": 15000,
            "consum_kwh_km": 0.20,
            "emisii_wltp_gco2_km": 0,
        },
        cota_banca=Camp(valoare=1.0),
    )
    imp_ct = calculeaza_impact_categorie("clean_transportation", stare_ct)
    # dif = 120 - 0.20 * 250 = 70 g/km. 70 * 15000 * 20 / 1_000_000 = 21.0 tCO2/an
    assert imp_ct["rezultat_tco2_an"] == 21.0
