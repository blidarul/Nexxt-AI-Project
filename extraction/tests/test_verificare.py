"""Teste unitare pentru modulul de verificare anti-halucinație și rezolvare conflicte."""

from extraction.verificare import (
    verifica_citat,
    calculeaza_incredere_finala,
    sunt_valori_in_conflict,
    rezolva_conflicte_camp,
)


def test_verifica_citat_pe_pagina():
    doc = {
        "fisier": "01_test.pdf",
        "pagini": [
            {
                "pagina": 1,
                "text": "Suma solicitată este de 30.000.000 EUR pentru proiect.",
                "tabele": []
            }
        ]
    }
    gasit, pag, sursa = verifica_citat("Suma solicitată este de 30.000.000 EUR", 1, doc)
    assert gasit is True
    assert pag == 1
    assert sursa == "01_test.pdf, p.1"


def test_verifica_citat_pe_alta_pagina():
    doc = {
        "fisier": "01_test.pdf",
        "pagini": [
            {"pagina": 1, "text": "Introducere...", "tabele": []},
            {"pagina": 2, "text": "Suprafață utilă 20.000 m²", "tabele": []}
        ]
    }
    # LLM a zis pagina 1, dar citatul este pe pagina 2
    gasit, pag, sursa = verifica_citat("Suprafață utilă 20.000 m²", 1, doc)
    assert gasit is True
    assert pag == 2
    assert sursa == "01_test.pdf, p.2"


def test_verifica_citat_inexistent():
    doc = {
        "fisier": "01_test.pdf",
        "pagini": [
            {"pagina": 1, "text": "Text oarecare...", "tabele": []}
        ]
    }
    gasit, pag, sursa = verifica_citat("Valoare inventată de 999.000 EUR", 1, doc)
    assert gasit is False
    assert sursa is None


def test_calculeaza_incredere_finala():
    # Citat verificat complet
    inc = calculeaza_incredere_finala(0.95, citat_verificat=True, normalizare_reusita=True, este_document_probabil=True)
    assert inc == 0.95

    # Citat negăsit -> încredere 0.0
    inc_respins = calculeaza_incredere_finala(0.95, citat_verificat=False, normalizare_reusita=True, este_document_probabil=True)
    assert inc_respins == 0.0

    # Normalizare eșuată -> factor 0.5
    inc_norm = calculeaza_incredere_finala(1.0, citat_verificat=True, normalizare_reusita=False, este_document_probabil=True)
    assert inc_norm == 0.5

    # Document improbabil -> factor 0.8
    inc_doc = calculeaza_incredere_finala(1.0, citat_verificat=True, normalizare_reusita=True, este_document_probabil=False)
    assert inc_doc == 0.8


def test_sunt_valori_in_conflict():
    # Diferență sub 2% -> nu e conflict
    assert sunt_valori_in_conflict(20000, 20100) is False

    # Diferență peste 2% -> conflict
    assert sunt_valori_in_conflict(20000, 25000) is True

    # Șiruri identice
    assert sunt_valori_in_conflict("România", "România") is False

    # Șiruri diferite
    assert sunt_valori_in_conflict("București", "Cluj-Napoca") is True


def test_rezolva_conflicte_camp():
    catalog = {
        "suprafata_m2": {
            "documente_probabile": ["cerere_finantare", "certificat_energetic"]
        }
    }
    candidati = [
        {
            "fisier": "03_certificat.pdf",
            "tip_document": "certificat_energetic",
            "valoare_normalizata": 25000,
            "citat": "Au 25.000"
        },
        {
            "fisier": "01_cerere.pdf",
            "tip_document": "cerere_finantare",
            "valoare_normalizata": 20000,
            "citat": "Suprafață 20.000"
        }
    ]
    ales, conflicte = rezolva_conflicte_camp("suprafata_m2", candidati, catalog)
    assert ales["tip_document"] == "cerere_finantare"
    assert ales["valoare_normalizata"] == 20000
    assert len(conflicte) == 1
    assert conflicte[0]["valoare_aleasa"] == 20000
    assert conflicte[0]["valoare_alternativa"] == 25000


def test_citat_din_tabel_markdown_cu_separator():
    from extraction.verificare import verifica_citat
    doc = {"fisier": "x.pdf", "pagini": [{"pagina": 1, "text": "Țara România", "tabele": [{"randuri": [["S Țara", "România"]]}]}]}
    gasit, pag, _ = verifica_citat("S Țara | România", 1, doc)
    assert gasit and pag == 1
