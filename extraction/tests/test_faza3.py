"""Teste pentru reparațiile de la începutul Fazei 3 și pentru Faza 3 (OCR, raport de lipsuri)."""

from pathlib import Path
import tempfile

import pytest

from extraction.cautare import incarca_catalog_campuri
from extraction.cerinte import evalueaza_documente, interpreteaza_obligativitate
from extraction.extragere_campuri import extrage_afirmatii_determinist
from extraction.llm_client import LLMClient
from extraction.ocr import aplica_ocr_pdf, tabele_din_text_ocr


# ----------------------------------------------------------------------------- date cu sens precis
def test_datele_cu_sens_precis_nu_au_cautare_extinsa():
    catalog = incarca_catalog_campuri()
    for camp in ("data_aprobare", "data_marcare_verde"):
        assert catalog[camp].get("cautare_extinsa") is False, camp


def test_descrierea_datei_de_aprobare_nu_accepta_data_cererii():
    descriere = incarca_catalog_campuri()["data_aprobare"]["descriere"].lower()
    assert "sau data cererii" not in descriere
    assert "nu data cererii" in descriere


# ----------------------------------------------------------------------------- afirmații
def _doc_cerere(text, tabele=None):
    return {"fisier": "cerere.pdf", "pagini": [{"pagina": 1, "text": text, "tabele": tabele or []}]}


@pytest.fixture
def info_afirmatii():
    return incarca_catalog_campuri()["afirmatii_client"]


def test_afirmatii_din_sectiune_si_bullet_continuat(info_afirmatii):
    text = (
        "Structura finanțării Banca 100% (450.000 EUR)\n"
        "4. Declarații ale solicitantului privind sustenabilitatea\n"
        "• Flota noastră este 100% cu emisii zero.\n"
        "• Clădirea consumă cu peste 60% mai puțină energie decât media din\n"
        "România.\n"
        "5. Documente anexate\n"
        "• Anexa 1 – lista vehiculelor\n"
    )
    tabele = [{"randuri": [["Structura finanțării", "Banca 100% (450.000 EUR)"]]}]
    afirmatii, sursa, _ = extrage_afirmatii_determinist([_doc_cerere(text, tabele)], info_afirmatii)
    assert afirmatii == [
        "Flota noastră este 100% cu emisii zero.",
        "Clădirea consumă cu peste 60% mai puțină energie decât media din România.",
    ]
    assert sursa == "cerere.pdf, p.1"


def test_afirmatii_in_afara_sectiunii_doar_fraze_cu_cuvinte_cheie(info_afirmatii):
    text = (
        "Denumire clădire Verde Business Park\n"                 # câmp de formular, nu frază
        "Proiectul nostru este neutru din punct de vedere climatic.\n"
        "Durata creditului este de 10 ani.\n"                     # frază fără cuvânt-cheie
    )
    afirmatii, _, _ = extrage_afirmatii_determinist([_doc_cerere(text)], info_afirmatii)
    assert afirmatii == ["Proiectul nostru este neutru din punct de vedere climatic."]


# ----------------------------------------------------------------------------- LLM: plic și detalii apeluri
def test_plicul_inventat_se_despacheteaza():
    plic = {"model": "gpt-4o-mini", "response": '```json\n{"pue_anualizat": {"valoare_text": "1,38"}}\n```'}
    assert LLMClient.despacheteaza_plic(plic) == {"pue_anualizat": {"valoare_text": "1,38"}}
    trunchiat = {"model": "gpt-4o-mini", "response": "{"}
    assert LLMClient.despacheteaza_plic(trunchiat) == trunchiat
    normal = {"model": "X", "response": "{}", "alt_camp": 1}
    assert LLMClient.despacheteaza_plic(normal) == normal


def test_apelurile_reale_inregistreaza_modelul_raportat_de_api(monkeypatch):
    monkeypatch.delenv("LLM_OFFLINE", raising=False)
    client = LLMClient(cache_dir=Path(tempfile.mkdtemp()))
    client.api_key = "test"
    monkeypatch.setattr(client, "_executa_apel_api", lambda **kw: ('{"ok": true}', "Qwen/Qwen3-32B"))
    client.apeleaza([{"role": "user", "content": "x"}], model="Qwen/Qwen3-32B")
    client.apeleaza([{"role": "user", "content": "x"}], model="Qwen/Qwen3-32B")  # din cache
    assert len(client.apeluri_reale_detalii) == 1
    assert client.apeluri_reale_detalii[0]["model_cerut"] == "Qwen/Qwen3-32B"
    assert client.apeluri_reale_detalii[0]["model_raspuns"] == "Qwen/Qwen3-32B"


# ----------------------------------------------------------------------------- OCR
def test_tabel_refacut_din_text_ocr():
    text = "Titlu\nMarca | Model | Nr. buc.\n|---|---|---|\nExemplu | City-EV | 5\nExemplu | Cargo | 3\nFinal"
    tabele = tabele_din_text_ocr(text)
    assert tabele[0]["randuri"] == [["Marca", "Model", "Nr. buc."], ["Exemplu", "City-EV", "5"], ["Exemplu", "Cargo", "3"]]


def test_ocr_completeaza_doar_paginile_fara_text():
    from extraction.test_fixtures.genereaza_fixtures import _pdf_scanat

    class ClientFals:
        def __init__(self):
            self.apeluri = 0

        def apeleaza_vision(self, prompt, imagine, mime_type="image/png"):
            self.apeluri += 1
            assert imagine[:8] == b"\x89PNG\r\n\x1a\n"
            return "47. Emisii CO2 WLTP, combinat: 48 g/km"

    with tempfile.TemporaryDirectory() as tmp:
        cale = Path(tmp) / "scanat.pdf"
        _pdf_scanat(cale, ["CERTIFICAT DE CONFORMITATE", "47. Emisii CO2 WLTP, combinat: 48 g/km"])
        pagini = [{"pagina": 1, "text": "", "necesita_ocr": True, "tabele": []},
                  {"pagina": 2, "text": "are text", "necesita_ocr": False, "tabele": []}]
        client = ClientFals()
        # pagina 2 nu există în PDF, dar nu trebuie atinsă (are text)
        erori = aplica_ocr_pdf(cale, pagini, client)
    assert erori == [] and client.apeluri == 1
    assert pagini[0]["ocr"] is True and "48 g/km" in pagini[0]["text"] and not pagini[0]["necesita_ocr"]
    assert "ocr" not in pagini[1]


def test_ocr_esuat_lasa_pagina_marcata():
    class ClientCuEroare:
        def apeleaza_vision(self, *a, **k):
            raise RuntimeError("model gated")

    from extraction.test_fixtures.genereaza_fixtures import _pdf_scanat
    with tempfile.TemporaryDirectory() as tmp:
        cale = Path(tmp) / "scanat.pdf"
        _pdf_scanat(cale, ["x"])
        pagini = [{"pagina": 1, "text": "", "necesita_ocr": True, "tabele": []}]
        erori = aplica_ocr_pdf(cale, pagini, ClientCuEroare())
    assert erori and "model gated" in erori[0]
    assert pagini[0]["necesita_ocr"] is True and pagini[0]["text"] == ""


# ----------------------------------------------------------------------------- documente lipsă
@pytest.mark.parametrize("valoare,sub,fel,se_aplica", [
    (True, None, "obligatoriu", True),
    (False, None, "optional", False),
    ("una_din: [GB-D1, GB-D2]", "cladire_noua_sau_existenta", "una_din", True),
    ("doar hidro nou", "hidro", "conditionat", True),
    ("doar hidro nou", "solar_fotovoltaic", "conditionat", False),
    ("doar geotermal, biomasa", "biomasa_deseuri", "conditionat", True),
    ("doar aluminiu", "produse_aluminiu", "conditionat", True),
    ("pentru impact", "camion", "recomandat", False),
])
def test_interpretare_obligativitate(valoare, sub, fel, se_aplica):
    r = interpreteaza_obligativitate(valoare, sub, None)
    assert r["fel"] == fel and r["se_aplica"] is se_aplica


def test_transport_fara_coc_are_ct_d2_lipsa():
    docs = [
        {"fisier": "a.pdf", "id_cerinte": ["D-01"]},
        {"fisier": "b.pdf", "id_cerinte": ["CT-D1"]},
    ]
    rez = evalueaza_documente("clean_transportation", "autoturism_sau_utilitara", None, docs)
    lipsa = {d["id"] for d in rez["documente_lipsa"]}
    assert "CT-D2" in lipsa and "CT-D1" not in lipsa and "D-01" not in lipsa
    assert "CT-D3" not in lipsa  # „doar marfa” nu se aplică la autoutilitare
    assert {d["id"] for d in rez["documente_gasite"]} == {"D-01", "CT-D1"}
    assert "CT-D4" in {d["id"] for d in rez["documente_recomandate_lipsa"]}


def test_una_din_e_satisfacut_de_oricare():
    docs = [{"fisier": "epc.pdf", "id_cerinte": ["GB-D2"]}]
    rez = evalueaza_documente("green_buildings", "cladire_noua_sau_existenta", None, docs)
    assert not any("GB-D1" in d["id"] for d in rez["documente_lipsa"])
    rez_gol = evalueaza_documente("green_buildings", "cladire_noua_sau_existenta", None, [])
    assert sum(1 for d in rez_gol["documente_lipsa"] if d["id"] == "GB-D1 sau GB-D2") == 1
