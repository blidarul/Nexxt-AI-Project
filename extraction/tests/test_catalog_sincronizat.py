"""Test automat de sincronizare între cerinte_dosar.yaml și campuri.yaml."""

import pytest
from extraction.verifica_catalog import verifica_sincronizare_catalog
from extraction.cautare import incarca_catalog_campuri


def test_toate_campurile_cerinte_in_catalog():
    """Verifică că orice câmp din cerinte_dosar.yaml este descris în campuri.yaml și are flag-ul corect."""
    lipsa, flag_gresit, informative = verifica_sincronizare_catalog()
    assert lipsa == [], f"Câmpuri din cerinte_dosar.yaml lipsă din campuri.yaml: {lipsa}"
    assert flag_gresit == [], f"Câmpuri din cerinte marcate cu extras_din_document=False: {flag_gresit}"
    # Informativ: trebuie să existe câmpuri calculate/externe din reguli
    assert len(informative) > 0


def test_extractorul_cere_doar_campuri_extras_din_document_true():
    """Verifică faptul că extractorul nu trimite către LLM câmpuri cu extras_din_document: false."""
    from extraction.extragere_campuri import extrage_campuri_document_llm

    catalog = incarca_catalog_campuri()

    # Căutăm câmpuri cu extras_din_document: False
    campuri_false = [c for c, v in catalog.items() if v.get("extras_din_document") is False]
    assert len(campuri_false) == 35, f"Așteptam 35 de câmpuri cu extras_din_document: False, am găsit {len(campuri_false)}"

    # Mock LLMClient care înregistrează mesajele
    class MockLLMClient:
        def __init__(self):
            self.ultimele_mesaje = None

        def apeleaza_cu_json(self, mesaje):
            self.ultimele_mesaje = mesaje
            return {}, None

    mock_client = MockLLMClient()
    pagini_test = [{"pagina": 1, "text": "Document de test", "tabele": []}]

    # 1. Dacă transmitem doar câmpuri cu extras_din_document: false -> nu apelează deloc LLM
    rez = extrage_campuri_document_llm(
        fisier="test.pdf",
        pagini=pagini_test,
        campuri=campuri_false[:3],
        catalog_campuri=catalog,
        llm_client=mock_client,
    )
    assert rez == {}
    assert mock_client.ultimele_mesaje is None, "LLM-ul nu trebuia apelat pentru câmpuri cu extras_din_document: false"

    # 2. Dacă transmitem o combinație -> LLM primește doar cele cu extras_din_document: true
    campuri_mixte = ["cui", "suma_eur", campuri_false[0]]
    rez = extrage_campuri_document_llm(
        fisier="test.pdf",
        pagini=pagini_test,
        campuri=campuri_mixte,
        catalog_campuri=catalog,
        llm_client=mock_client,
    )
    assert mock_client.ultimele_mesaje is not None
    prompt_user = mock_client.ultimele_mesaje[1]["content"]

    assert "- cui:" in prompt_user
    assert "- suma_eur:" in prompt_user
    assert f"- {campuri_false[0]}:" not in prompt_user, f"{campuri_false[0]} nu trebuia să apară în promptul LLM!"
