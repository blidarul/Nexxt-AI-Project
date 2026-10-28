"""Teste pentru Faza 2: tipuri de documente, categorii, selecția câmpurilor, tabele, da/nu."""

import json

import pytest

from extraction.cautare import incarca_catalog_campuri
from extraction.categorie import stabileste_categoria
from extraction.cerinte import (
    campuri_cerute,
    id_pentru_document,
    incarca_categorii,
    incarca_tipuri_documente,
    tipuri_pentru_id,
    toate_id_documentele,
)
from extraction.tabele import (
    agrega_randuri,
    aplica_document_autoritate,
    extrage_lista_din_tabele,
    potriveste_antet,
)
from extraction.verificare import verifica_da_nu


# ----------------------------------------------------------------------------- tipuri de documente
def test_fiecare_id_din_cerinte_e_acoperit_de_un_tip():
    neacoperite = sorted(i for i in toate_id_documentele() if not tipuri_pentru_id(i))
    assert neacoperite == [], f"ID-uri fără tip de document: {neacoperite}"


def test_tipurile_refera_doar_id_uri_existente():
    ids = toate_id_documentele()
    for tip, info in incarca_tipuri_documente().items():
        assert set(info.get("id_cerinte") or []) <= ids, tip
        for rol, lista in (info.get("roluri") or {}).items():
            assert set(lista) <= set(info["id_cerinte"]), f"{tip}.{rol}"


def test_indiciile_de_categorie_sunt_valori_permise():
    categorii = incarca_categorii()
    for tip, info in incarca_tipuri_documente().items():
        ind = info.get("indiciu_categorie")
        if not ind:
            continue
        assert ind["categorie"] in categorii, tip
        if ind.get("subcategorie"):
            assert ind["subcategorie"] in categorii[ind["categorie"]]["subcategorii"], tip
        assert ind.get("forta") in ("puternic", "slab"), tip


def test_tipurile_cerute_de_handoff_exista():
    tipuri = incarca_tipuri_documente()
    for tip in ["cerere_finantare", "decizie_aprobare", "certificat_conformitate_vehicul", "raport_pue",
                "lista_vehicule", "declaratie_utilizare", "alt_document", "date_productie",
                "contract_materie_prima", "descriere_tehnica", "plan_gestionare_deseuri",
                "proiectie_dupa_investitie", "descriere_produs"]:
        assert tip in tipuri, tip


def test_rolul_alege_id_ul_pentru_epc():
    permise = {"GB-D6", "GB-D7", "GB-D8"}
    assert id_pentru_document("certificat_energetic", "inainte", permise) == ["GB-D6"]
    assert id_pentru_document("certificat_energetic", "dupa", permise) == ["GB-D7"]
    assert id_pentru_document("certificat_conformitate_vehicul", None, {"CT-D2"}) == ["CT-D2"]


# ----------------------------------------------------------------------------- categorii și câmpuri
def test_categorii_citite_din_reguli():
    categorii = incarca_categorii()
    assert "data_center" in categorii["energy_efficiency"]["subcategorii"]
    assert categorii["clean_transportation"]["camp_subcategorie"] == "tip"
    assert categorii["renewable_energy"]["camp_subcategorie"] == "tehnologie"
    n3 = categorii["green_buildings"]["nivel_3"]["masura_individuala"]
    assert n3["camp"] == "tip_masura" and "pompa_caldura" in n3["valori"]


def test_doar_pentru_filtreaza_campurile():
    dc = [c["camp"] for c in campuri_cerute("energy_efficiency", "data_center")]
    fibra = [c["camp"] for c in campuri_cerute("energy_efficiency", "fibra_optica")]
    assert "pue_anualizat" in dc and "pue_anualizat" not in fibra
    assert "nr_gospodarii_conectate" in fibra and "nr_gospodarii_conectate" not in dc
    pompa = [c["camp"] for c in campuri_cerute("green_buildings", "masura_individuala", "pompa_caldura")]
    assert "gwp_agent_frigorific" in pompa and "statie_in_cladire" not in pompa
    # comun e mereu inclus
    assert "cui" in dc and "cui" in pompa


def test_catalogul_are_descriere_pentru_campurile_din_documente():
    catalog = incarca_catalog_campuri()
    fara = [k for k, v in catalog.items() if v.get("extras_din_document", True) and not v.get("descriere")]
    assert fara == []


class _ClientFals:
    def __init__(self, raspuns):
        self.raspuns = raspuns

    def apeleaza_cu_json(self, mesaje, **kwargs):
        return self.raspuns, None


def _doc(fisier, tip, text):
    return {"fisier": fisier, "tip_document": tip, "pagini": [{"pagina": 1, "text": text, "tabele": []}]}


def test_categoria_respinge_valori_nepermise_si_foloseste_indicii():
    docs = [
        _doc("a.pdf", "cerere_finantare", "Achiziția unei flote de autoutilitare electrice."),
        _doc("b.pdf", "lista_vehicule", "Lista vehiculelor"),
    ]
    rez = stabileste_categoria(docs, _ClientFals({"candidati": [
        {"categorie": "inexistenta", "subcategorie": "x", "incredere": 0.99, "citat": "flota"},
        {"categorie": "clean_transportation", "subcategorie": "autoturism_sau_utilitara", "incredere": 0.85,
         "citat": "Achiziția unei flote de autoutilitare electrice"},
    ]}))
    assert not rez["ambiguu"]
    assert rez["candidati"][0]["categorie"] == "clean_transportation"
    assert rez["candidati"][0]["citat_verificat"]
    assert rez["candidati"][0]["incredere"] >= 0.9  # indiciul puternic (lista_vehicule) confirmă


def test_categoria_ambigua_pastreaza_doi_candidati():
    docs = [_doc("a.pdf", "cerere_finantare", "Modernizarea iluminatului și panouri fotovoltaice pe hala de producție")]
    rez = stabileste_categoria(docs, _ClientFals({"candidati": [
        {"categorie": "energy_efficiency", "subcategorie": "eficienta_industriala", "incredere": 0.55,
         "citat": "Modernizarea iluminatului"},
        {"categorie": "renewable_energy", "subcategorie": "solar_fotovoltaic", "incredere": 0.45,
         "citat": "panouri fotovoltaice pe hala de producție"},
    ]}))
    assert rez["ambiguu"]
    assert [c["categorie"] for c in rez["candidati"]] == ["energy_efficiency", "renewable_energy"]
    assert all(c["incredere"] < 0.7 for c in rez["candidati"])


def test_citat_inventat_scade_increderea():
    docs = [_doc("a.pdf", "cerere_finantare", "Centru de date")]
    rez = stabileste_categoria(docs, _ClientFals({"candidati": [
        {"categorie": "energy_efficiency", "subcategorie": "data_center", "incredere": 0.9, "citat": "text care nu există"},
    ]}))
    assert rez["candidati"][0]["citat_verificat"] is False
    assert rez["ambiguu"]


# ----------------------------------------------------------------------------- tabele
@pytest.fixture
def info_vehicule():
    return incarca_catalog_campuri()["vehicule"]


ANTET = ["Nr. crt.", "Marca", "Model", "Combustibil", "Nr. buc.", "CO2 WLTP (g/km)", "Consum (kWh/100 km)", "Km/an"]


def _doc_lista(pagini_tabele):
    return {"fisier": "lista.pdf", "pagini": [
        {"pagina": i + 1, "text": "", "tabele": [{"randuri": r}] if r else []} for i, r in enumerate(pagini_tabele)
    ]}


def test_antet_nr_crt_nu_e_cantitate(info_vehicule):
    mapare = potriveste_antet(ANTET, info_vehicule["coloane"])
    assert 0 not in mapare
    assert mapare[4] == "bucati" and mapare[6] == "consum_kwh_km" and mapare[5] == "emisii_wltp_gco2_km"


def test_tabel_pe_doua_pagini_fara_antet_se_uneste_si_se_agrega(info_vehicule):
    doc = _doc_lista([
        [ANTET, ["1", "Exemplu", "EV-Van", "electric", "6", "0", "16,0", "17.746"]],
        [["2", "Exemplu", "EV-Van", "electric", "4", "0", "16,0", "17.746"]],
    ])
    rez = extrage_lista_din_tabele("vehicule", info_vehicule, [doc])
    assert rez["sursa"] == "lista.pdf, p.1-2"
    assert rez["valoare"] == [{"marca": "Exemplu", "model": "EV-Van", "combustibil": "electric", "bucati": 10,
                               "emisii_wltp_gco2_km": 0, "consum_kwh_km": 0.16, "distanta_anuala_km": 17746}]
    assert {c["unitate_originala"] for c in rez["conversii"]} == {"kWh/100km"}


def test_antet_repetat_pe_pagina_urmatoare(info_vehicule):
    doc = _doc_lista([
        [ANTET, ["1", "Exemplu", "EV-Van", "electric", "6", "0", "16", "1000"]],
        [ANTET, ["2", "Exemplu", "PHEV-Van", "hibrid", "2", "45", "5", "1000"]],
    ])
    rez = extrage_lista_din_tabele("vehicule", info_vehicule, [doc])
    assert [r["model"] for r in rez["valoare"]] == ["EV-Van", "PHEV-Van"]


def test_tabel_pe_pagini_neconsecutive_nu_se_uneste(info_vehicule):
    doc = _doc_lista([
        [ANTET, ["1", "Exemplu", "EV-Van", "electric", "6", "0", "16", "1000"]],
        [],
        [["9", "Altceva", "X", "y", "1", "1", "1", "1"]],
    ])
    rez = extrage_lista_din_tabele("vehicule", info_vehicule, [doc])
    assert len(rez["valoare"]) == 1


def test_g_pe_mila_se_converteste(info_vehicule):
    antet = ["Marca", "Model", "Combustibil", "Qty", "CO2 (g/mi)"]
    doc = _doc_lista([[antet, ["Exemplu", "X", "diesel", "1", "160,9"]]])
    rez = extrage_lista_din_tabele("vehicule", info_vehicule, [doc])
    assert rez["valoare"][0]["emisii_wltp_gco2_km"] == pytest.approx(100.0, abs=0.01)


def test_fara_tabel_recognoscibil_intoarce_none(info_vehicule):
    doc = _doc_lista([[["Indicator", "Valoare"], ["PUE", "1,38"]]])
    assert extrage_lista_din_tabele("vehicule", info_vehicule, [doc]) is None


def test_agregare_valori_diferite_genereaza_conflict():
    randuri = [{"model": "A", "bucati": 2, "emisii": 48}, {"model": "A", "bucati": 3, "emisii": 45}]
    agregate, conflicte = agrega_randuri(randuri, ["model"], "bucati")
    assert agregate == [{"model": "A", "bucati": 5, "emisii": 48}]
    assert conflicte and conflicte[0]["camp"] == "emisii"


def test_coc_castiga_la_emisii(info_vehicule):
    lista = [{"marca": "Exemplu", "model": "PHEV-Van", "bucati": 5, "emisii_wltp_gco2_km": 48, "consum_kwh_km": 0.05}]
    conflicte = aplica_document_autoritate(lista, [
        {"valori": {"marca": "Exemplu", "model": "PHEV-Van", "emisii_wltp_gco2_km": 45, "consum_kwh_km": 0.05},
         "sursa": "coc.pdf"},
    ], info_vehicule)
    assert lista[0]["emisii_wltp_gco2_km"] == 45
    assert len(conflicte) == 1 and conflicte[0]["valoare_lista"] == 48 and conflicte[0]["ales"] == 45


# ----------------------------------------------------------------------------- da / nu
@pytest.mark.parametrize("valoare,citat,asteptat", [
    (False, "Vehiculele finanțate nu transportă combustibili fosili", False),
    (False, "Fără plastic virgin în produs", False),
    (True, "Echipamentul este integrat cu panouri fotovoltaice", True),
    (True, "Vehiculele nu transportă combustibili fosili", None),        # negație contrazice valoarea
    (False, "Vehiculele transportă colete", None),                        # „nu” dedus, nu explicit
    (True, "Nu este exclus să nu transporte combustibili", None),         # dublă negație
    (False, "", None),                                                    # fără citat
])
def test_negatii_da_nu(valoare, citat, asteptat):
    rezultat, motiv = verifica_da_nu(valoare, citat)
    assert rezultat is asteptat
    assert (motiv == "citat ambiguu") == (asteptat is None)


def test_coc_nu_se_potriveste_pe_model_subsir(info_vehicule):
    lista = [{"marca": "Exemplu", "model": "EV-Van", "emisii_wltp_gco2_km": 0},
             {"marca": "Exemplu", "model": "PHEV-Van", "emisii_wltp_gco2_km": 48}]
    aplica_document_autoritate(lista, [
        {"valori": {"marca": "Exemplu", "model": "PHEV-Van", "emisii_wltp_gco2_km": 45}, "sursa": "coc.pdf"},
    ], info_vehicule)
    assert lista[0]["emisii_wltp_gco2_km"] == 0 and lista[1]["emisii_wltp_gco2_km"] == 45


def test_citat_reconstituit_doar_din_linie_unica():
    from extraction.extrage_structurat import reconstituie_citat
    doc = {"pagini": [{"pagina": 1, "text": "Adresa București, România\nȚara România\nDurata 10 ani"}]}
    assert reconstituie_citat("România", ["țara", "country"], doc) == "Țara România"
    assert reconstituie_citat("Franța", ["țara"], doc) is None
    doc_dublu = {"pagini": [{"pagina": 1, "text": "Țara România\nȚara de origine România"}]}
    assert reconstituie_citat("România", ["țara"], doc_dublu) is None
