"""Reparațiile extractorului: chiriași fără CAEN, tip din conținut vs. nume, data aprobării, fx_ambiguu."""

import json
from pathlib import Path

import pytest

from extraction import extrage_structurat
from extraction.extrage_brut import determina_tip_din_nume
from extraction.extragere_campuri import extrage_afirmatii_determinist, extrage_chiriasi_determinist
from extraction.test_fixtures.verifica_fixtures import FOLDER as FOLDER_FIXTURES, verifica_fixture

TEXT_CHIRIASI = (
    "EXTRAS CONTRACTE CHIRIAȘI\n"
    "* Chiriaș 1: Eco Supermarket SRL | CUI 9900000201 | CAEN 4711 |\n"
    "Suprafață: 8.000 m² (43.2%) | Contract: 2025-2035\n"
    "* Pre-contracte de închiriere spații comerciale parter: Eco Market\n"
    "SRL | CUI 9900000301 | Suprafață: 1.200 m² (8%)\n"
    "* Grad ocupare: 92% (17.000 m²) | Spațiu liber: 1.500 m² (8%)\n"
)

TEXT_CERERE = (
    "CERERE DE FINANȚARE - PERSOANĂ JURIDICĂ\n"
    "Nr. înregistrare bancă: CF-2026-0099 | Data cererii: 10.03.2026\n"
    "Solicitant: S.C. EXEMPLU S.R.L. | CUI: 9900000099\n"
    "Suma solicitată de la bancă: 1.000.000 EUR\n"
    "Descrierea proiectului: achiziție clădire de birouri certificată BREEAM\n"
    "Declar pe propria răspundere că datele sunt corecte. Data: 12.03.2026\n"
)

TEXT_DECLARATIE = (
    "DECLARAȚIE PE PROPRIA RĂSPUNDERE\n"
    "Subsemnatul declar că vehiculele/clădirea nu sunt folosite pentru combustibili fosili.\n"
    "Data: 20.03.2026\n"
)

TEXT_CPE = (
    "CERTIFICAT DE PERFORMANȚĂ ENERGETICĂ (CPE)\n"
    "Clasa Energetică | A\n"
    "Consum Anual Specific de Energie Primară | 90.0 kWh/m²/an\n"
    "Consum Anual Specific de Energie Finală | 76.0 kWh/m²/an\n"
)


def _doc(fisier, tip, text):
    return {"fisier": fisier, "tip_document": tip, "pagini": [{"pagina": 1, "text": text, "tabele": []}]}


# ----------------------------------------------------------------------------- chiriași
def test_fallback_chiriasi_decide_continutul_nu_numele():
    # nume care sugerează chiriași, dar conținutul a fost clasificat altfel: nu se citește
    assert extrage_chiriasi_determinist([_doc("CONTRACTE_CHIRIASI.pdf", "raspuns_anaf", TEXT_CHIRIASI)])[0] == []
    # nume fără niciun indiciu, conținut clasificat ca contract de închiriere: se citește
    chiriasi, sursa, _ = extrage_chiriasi_determinist([_doc("scan_0007.pdf", "contract_inchiriere", TEXT_CHIRIASI)])
    assert [c["nume"] for c in chiriasi] == ["Eco Supermarket SRL", "Eco Market SRL"]
    assert sursa == "scan_0007.pdf, p.1"


def test_chirias_fara_caen_ramane_cu_caen_null():
    chiriasi, _, _ = extrage_chiriasi_determinist([_doc("c.pdf", "contract_inchiriere", TEXT_CHIRIASI)])
    assert chiriasi[0] == {"nume": "Eco Supermarket SRL", "caen": "4711", "m2": 8000.0}
    assert chiriasi[1] == {"nume": "Eco Market SRL", "caen": None, "m2": 1200.0}


def test_chirias_fara_caen_in_tabel_nu_se_pierde():
    doc = {"fisier": "t.pdf", "tip_document": "contract_inchiriere", "pagini": [{"pagina": 1, "text": "", "tabele": [
        {"randuri": [["Chiriaș", "Cod CAEN", "Suprafață (m²)"], ["Alfa SRL", "6201", "1.000"], ["Beta SRL", "", "500"]]},
    ]}]}
    chiriasi, _, _ = extrage_chiriasi_determinist([doc])
    assert chiriasi == [{"nume": "Alfa SRL", "caen": "6201", "m2": 1000.0}, {"nume": "Beta SRL", "caen": None, "m2": 500.0}]


# ----------------------------------------------------------------------------- pipeline cu LLM fals
class _ClientFals:
    """Clasificarea eșuează (se folosește fallback-ul pe conținut); categoria și câmpurile sunt date de test."""

    def __init__(self, campuri=None, categorie=None):
        self.campuri = campuri or {}
        self.categorie = categorie or {"categorie": "green_buildings", "subcategorie": "cladire_noua_sau_existenta",
                                       "incredere": 0.9, "citat": "achiziție clădire de birouri certificată BREEAM"}
        self.apeluri_reale_detalii = []

    def get_statistici(self):
        return {"apeluri_reale": 0, "apeluri_cache": 0, "apeluri_offline": 0, "total_apeluri": 0}

    def apeleaza_cu_json(self, mesaje, chei_asteptate=None, **kwargs):
        if chei_asteptate == ["candidati"]:
            return {"candidati": [self.categorie]}, None
        if chei_asteptate:
            rez = {c: v for c, v in self.campuri.items() if c in chei_asteptate}
            return (rez, None) if rez else (None, "fals")
        return None, "fals: clasificarea cade pe cuvintele cheie din conținut"


def _ruleaza(tmp_path, monkeypatch, documente, client):
    folder = tmp_path / "dosar_test"
    (folder / "_brut").mkdir(parents=True)
    for doc in documente:
        cale = folder / "_brut" / (Path(doc["fisier"]).stem + ".json")
        cale.write_text(json.dumps({**doc, "nr_pagini": len(doc["pagini"])}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(extrage_structurat, "get_llm_client", lambda: client)
    return extrage_structurat.proceseaza_dosar_structurat(folder)


def test_chirias_fara_caen_apare_in_campuri_lipsa(tmp_path, monkeypatch):
    docs = [
        {"fisier": "cerere.pdf", "pagini": [{"pagina": 1, "text": TEXT_CERERE, "tabele": []}]},
        {"fisier": "anexa_2.pdf", "pagini": [{"pagina": 1, "text": TEXT_CHIRIASI, "tabele": []}]},
    ]
    extras, raport = _ruleaza(tmp_path, monkeypatch, docs, _ClientFals())
    lipsa = [c for c in raport["campuri_lipsa"] if c["motiv"] == "caen_lipsa_chirias"]
    assert [(c["camp"], c["chirias"]) for c in lipsa] == [("chiriasi.caen", "Eco Market SRL")]
    assert "GB-X1" in lipsa[0]["pentru"]
    # lista completă, cu caen null, e în raport și în indicatori; lista tipizată are doar chiriașii cu CAEN
    assert raport["campuri_extrase"]["chiriasi"]["valoare"][1] == {"nume": "Eco Market SRL", "caen": None, "m2": 1200.0}
    assert extras.indicatori["chiriasi"].valoare[1]["caen"] is None
    assert [c.nume for c in extras.chiriasi] == ["Eco Supermarket SRL"]
    assert "" not in [c.caen for c in extras.chiriasi]


# ----------------------------------------------------------------------------- tip din nume vs. conținut
@pytest.mark.parametrize("nume,asteptat", [
    ("scan_0034.pdf", None),
    ("CERTIFICAT_PERFORMANTA.pdf", "certificat_energetic"),
    ("CERERE DE FINANȚARE - PERSOANĂ JURIDICĂ (CREDIT STANDARD)1.pdf", "cerere_finantare"),
    ("RAPORT_ETANSEITATE_AER.pdf", "raport_etanseitate"),
    ("CONTRACT_PPA_VERDE.pdf", "contract_ppa_verde"),
])
def test_tip_din_nume_e_doar_indiciu(nume, asteptat):
    assert determina_tip_din_nume(nume) == asteptat


def test_tip_din_nume_foloseste_doar_tipuri_cunoscute():
    from extraction.cerinte import incarca_tipuri_documente
    tipuri = incarca_tipuri_documente()
    for nume in ["01_x.pdf", "03_x.pdf", "04_x.pdf", "BREEAM.pdf", "RASPUNS_ANAF.pdf", "BREVIAR.pdf",
                 "TAXONOMIE_UE.pdf", "RAPORT_LCA.pdf", "RAPORT_ETANSEITATE.pdf", "PPA.pdf", "DECLARATII_DE_MEDIU.pdf"]:
        assert determina_tip_din_nume(nume) in tipuri, nume


def test_cpe_cu_nume_inselator_e_clasificat_din_continut(tmp_path, monkeypatch):
    docs = [
        {"fisier": "cerere.pdf", "pagini": [{"pagina": 1, "text": TEXT_CERERE, "tabele": []}]},
        {"fisier": "scan_0034.pdf", "pagini": [{"pagina": 1, "text": TEXT_CPE, "tabele": []}]},
        # nume de cerere, conținut de CPE: decide conținutul, iar contradicția se raportează
        {"fisier": "CERERE_FINANTARE_v2.pdf", "pagini": [{"pagina": 1, "text": TEXT_CPE, "tabele": []}]},
    ]
    _, raport = _ruleaza(tmp_path, monkeypatch, docs, _ClientFals())
    pe_fisier = {d["fisier"]: d for d in raport["documente_clasificate"]}
    scan = pe_fisier["scan_0034.pdf"]
    assert scan["tip_din_nume"] is None
    assert scan["tip_din_continut"] == scan["tip_detectat"] == "certificat_energetic"
    assert scan["nume_contrazice_continut"] is False
    inselator = pe_fisier["CERERE_FINANTARE_v2.pdf"]
    assert inselator["tip_din_nume"] == "cerere_finantare"
    assert inselator["tip_din_continut"] == "certificat_energetic"
    assert inselator["nume_contrazice_continut"] is True
    assert "GB-D2" in inselator["id_cerinte"]


# ----------------------------------------------------------------------------- data aprobării
@pytest.mark.parametrize("valoare,citat,motiv", [
    ("10.03.2026", "Data cererii: 10.03.2026", "citat_fara_cuvant_cheie"),
    ("12.03.2026", "Data: 12.03.2026", "citat_fara_cuvant_cheie"),
    # declarația separată nu e document țintă pentru data aprobării: citatul nu e în cerere
    ("20.03.2026", "Data: 20.03.2026", "citat_negasit"),
])
def test_data_cererii_sau_o_declaratie_datata_nu_dau_data_aprobare(tmp_path, monkeypatch, valoare, citat, motiv):
    docs = [
        {"fisier": "cerere.pdf", "pagini": [{"pagina": 1, "text": TEXT_CERERE, "tabele": []}]},
        {"fisier": "declaratie.pdf", "pagini": [{"pagina": 1, "text": TEXT_DECLARATIE, "tabele": []}]},
    ]
    client = _ClientFals({"data_aprobare": {"valoare_text": valoare, "citat": citat, "pagina": 1, "incredere": 0.9}})
    extras, raport = _ruleaza(tmp_path, monkeypatch, docs, client)
    assert extras.data_aprobare.valoare is None
    assert "data_aprobare" in {c["camp"] for c in raport["campuri_lipsa"]}
    assert any(r["camp"] == "data_aprobare" and r["motiv"] == motiv for r in raport["valori_respinse"])


def test_data_aprobarii_explicita_e_acceptata(tmp_path, monkeypatch):
    text = TEXT_CERERE + "Data aprobării creditului: 15.03.2026\n"
    docs = [{"fisier": "cerere.pdf", "pagini": [{"pagina": 1, "text": text, "tabele": []}]}]
    client = _ClientFals({"data_aprobare": {"valoare_text": "15.03.2026", "citat": "Data aprobării creditului: 15.03.2026",
                                            "pagina": 1, "incredere": 0.95}})
    extras, _ = _ruleaza(tmp_path, monkeypatch, docs, client)
    assert extras.data_aprobare.valoare == "2026-03-15"


def test_data_aprobare_cauta_in_d02_d05_si_cerere_doar_cu_expresii_precise():
    from extraction.cautare import incarca_catalog_campuri
    info = incarca_catalog_campuri()["data_aprobare"]
    assert {"cerere_finantare", "decizie_aprobare", "contract_credit"} <= set(info["documente_probabile"])
    assert "data" not in [k.strip().lower() for k in info["cuvinte_cheie"]]
    assert all(len(k.split()) >= 2 for k in info["cuvinte_cheie"])
    assert info["citat_cu_cuvant_cheie"] is True


# ----------------------------------------------------------------------------- fixture-uri
@pytest.mark.parametrize("fixture", sorted(p.name for p in FOLDER_FIXTURES.iterdir() if (p / "expected_campuri.json").exists()))
def test_fixture_corespunde_asteptarilor(fixture):
    gresite = [r for r in verifica_fixture(FOLDER_FIXTURES / fixture) if not r["ok"]]
    assert gresite == [], gresite


# ----------------------------------------------------------------------------- reparații după rularea reală
def test_cui_cu_prefix_ro_si_spatiu():
    from extraction.cautare import incarca_catalog_campuri
    from extraction.normalizare import normalizeaza_camp
    info = incarca_catalog_campuri()["cui"]
    assert normalizeaza_camp("cui", "RO 9900000030", info.get("tip"), info.get("validare")) == ("9900000030", None)


def test_citat_cu_cuvant_despartit_la_capat_de_rand():
    from extraction.verificare import verifica_citat_in_pagina
    text = "Certificare declarată: BREEAM Outstanding (Certificat nr. BREEAM-\nEXEMPLU-0003)"
    assert verifica_citat_in_pagina("Certificat nr. BREEAM-EXEMPLU-0003", text)
    assert not verifica_citat_in_pagina("Certificat nr. BREEAM-EXEMPLU-0004", text)


def test_valoarea_convertita_de_llm_se_aliniaza_cu_citatul():
    from extraction.extrage_structurat import aliniaza_valoare_cu_citatul
    # LLM-ul a convertit singur 4.800 kW -> 4.8: conversia se reface (și se raportează) în cod
    assert aliniaza_valoare_cu_citatul("capacitate_mw", "4.8", "Putere instalată 4.800 kW") == "4.800 kW"
    assert aliniaza_valoare_cu_citatul("capacitate_mw", "4.800 kW", "Putere instalată 4.800 kW") == "4.800 kW"
    assert aliniaza_valoare_cu_citatul("pue_anualizat", "1,38", "annualised PUE: 1,38") == "1,38"


def test_categoria_cade_pe_indicii_cand_llm_nu_da_candidati():
    from extraction.categorie import stabileste_categoria

    class _FaraRaspuns:
        def apeleaza_cu_json(self, mesaje, **kwargs):
            return None, "fără răspuns"

    rez = stabileste_categoria([_doc("BREEAM.pdf", "certificat_sustenabilitate", ""),
                                _doc("EPC.pdf", "certificat_energetic", "")], _FaraRaspuns())
    assert rez["candidati"][0]["categorie"] == "green_buildings"
    assert rez["ambiguu"] and rez["candidati"][0]["incredere"] < 0.7
    assert stabileste_categoria([_doc("x.pdf", "alt_document", "")], _FaraRaspuns())["candidati"] == []


def test_cpe_pdf_real_salvat_ca_scan_e_clasificat_din_continut(tmp_path, monkeypatch):
    """Cap-coadă: PDF real -> _brut (tip_din_nume) -> clasificare din conținut."""
    from extraction.extrage_brut import proceseaza_dosar
    from extraction.test_fixtures.genereaza_fixtures import _cerere, _p, _pdf
    folder = tmp_path / "dosar_pdf"
    folder.mkdir()
    _cerere(folder / "cerere.pdf", [["CUI", "9900000099"], ["Suma solicitată de la bancă", "1.000.000 EUR"]],
            "Achiziție clădire de birouri certificată BREEAM", [])
    _pdf(folder / "scan_0034.pdf", [_p(linie) for linie in TEXT_CPE.splitlines()])
    proceseaza_dosar(folder)
    index = json.loads((folder / "_brut" / "index.json").read_text(encoding="utf-8"))
    assert {d["fisier"]: d["tip_din_nume"] for d in index["documente"]} == {
        "cerere.pdf": "cerere_finantare", "scan_0034.pdf": None}
    monkeypatch.setattr(extrage_structurat, "get_llm_client", lambda: _ClientFals())
    _, raport = extrage_structurat.proceseaza_dosar_structurat(folder)
    scan = next(d for d in raport["documente_clasificate"] if d["fisier"] == "scan_0034.pdf")
    assert scan["tip_din_nume"] is None and scan["tip_din_continut"] == "certificat_energetic"


# ----------------------------------------------------------------------------- afirmațiile din dosarele reale
@pytest.fixture
def info_afirmatii():
    from extraction.cautare import incarca_catalog_campuri
    return incarca_catalog_campuri()["afirmatii_client"]


def test_afirmatii_sectiune_la_singular_peste_pagini_pana_la_semnatura(info_afirmatii):
    doc = {"fisier": "cerere.pdf", "pagini": [
        {"pagina": 1, "tabele": [], "text": (
            "• Obiectiv: Dezvoltarea depozitului logistic verde \"Solar\nLogistics Center\"\n"
            "DECLARAȚIE PRIVIND SUSTENABILITATEA\n"
            "Certificare declarată: BREEAM Outstanding (Certificat nr. BREEAM-\nEXEMPLU-0003)")},
        {"pagina": 2, "tabele": [], "text": (
            "Performanță energetică declarată: Clasa A+ (Consum specific 72\nkWh/m²/an)\n"
            "Semnătură autorizată: [Radu Popa]")},
    ]}
    afirmatii, sursa, _ = extrage_afirmatii_determinist([doc], info_afirmatii)
    assert afirmatii == [
        "Certificare declarată: BREEAM Outstanding (Certificat nr. BREEAM-EXEMPLU-0003)",
        "Performanță energetică declarată: Clasa A+ (Consum specific 72 kWh/m²/an)",
    ]
    assert sursa == "cerere.pdf, p.1; cerere.pdf, p.2"
