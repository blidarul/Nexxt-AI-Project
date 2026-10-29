"""Starea pașilor agentului: doar din câmpurile structurate ale trace-ului, niciodată din textul rezumatului."""

from __future__ import annotations

import pytest

from ui.pasi import CAMP_PENTRU_PAS, stare_pas

CAMPURI = {
    "cui": {"valoare": "9900000020", "sursa": "CERERE_FINANTARE.pdf, p.1"},
    "nr_certificat_declarat": {"valoare": "BREEAM-EXEMPLU-0002", "sursa": "CERERE_FINANTARE.pdf, p.1"},
    "vehicule": {"valoare": [{"marca": "Ford", "model": "E-Transit", "emisii_wltp_gco2_km": 0}],
                 "sursa": "LISTA_VEHICULE.pdf, p.2"},
}
REGULI = {"G-01": "OK", "G-03": "NEEVALUABIL", "GB-01": "NU", "GB-02": "OK", "GB-X1": "OK", "PL-01": "SEMNAL"}


def _public(nume, camp):
    return {"camp": nume, "valoare": camp["valoare"], "fisier": camp["sursa"].split(",")[0], "pagina": 1, "url": "/f"}


def _pas(actiune, argumente=None, **rezultat):
    rez = {"tool": actiune, "gasit": False, "eroare": None, "verificat_in_registru": None, "eroare_tehnica": False,
           "sumar": "Găsit"}  # sumarul nu contează niciodată
    rez.update(rezultat)
    return {"pas": 1, "tip": "tool", "actiune": actiune, "argumente": argumente or {}, "rezultat": rez}


def _stare(intrare, campuri=CAMPURI):
    return stare_pas(intrare, REGULI, campuri, _public)


# ---------------------------------------------------------------- un test pentru fiecare status din tabel
def test_verificat_cand_registrul_confirma():
    st = _stare(_pas("verifica_firma", gasit=True))
    assert (st["cheie"], st["eticheta"], st["clasa"]) == ("verificat", "Verificat", "pos")


@pytest.mark.parametrize("pas", list(CAMP_PENTRU_PAS))
def test_gasit_false_cu_valoarea_in_dosar(pas):
    st = _stare(_pas(pas, gasit=False, eroare="Nu există în registru."))
    assert (st["cheie"], st["eticheta"], st["clasa"]) == ("in_dosar", "Găsit în dosar, neverificat în registru", "warn")
    # sursa din document, ca analistul s-o poată deschide
    assert st["sursa"]["camp"] == CAMP_PENTRU_PAS[pas][0] and st["sursa"]["url"]
    assert st["detaliu"] == "Nu există în registru."


def test_negasit_nici_in_registru_nici_in_documente():
    st = _stare(_pas("cauta_certificat", gasit=False, eroare="Certificatul X nu există în registrul BREEAM."), campuri={})
    assert (st["cheie"], st["eticheta"], st["clasa"]) == ("negasit", "Negăsit", "neg")


def test_eroare_de_retea_e_eroare_la_verificare_chiar_daca_valoarea_e_in_dosar():
    st = _stare(_pas("verifica_firma", gasit=False, eroare="Mod offline: nicio sursă (ConnectionError)", eroare_tehnica=True))
    assert (st["cheie"], st["eticheta"], st["clasa"]) == ("eroare", "Eroare la verificare", "eroare")
    assert "ConnectionError" in st["detaliu"]


def test_pas_de_evaluare_arata_rezultatele_regulilor():
    st = _stare(_pas("evalueaza_conditii_generale", gasit=True))
    assert [(x["id"], x["rezultat"], x["eticheta"]) for x in st["reguli"]] == [
        ("G-01", "OK", "OK"), ("G-03", "NEEVALUABIL", "Neevaluabil")]
    cale = _stare(_pas("evalueaza_cale", {"cale_id": "GB-01"}, gasit=True))
    assert [(x["id"], x["rezultat"]) for x in cale["reguli"]] == [("GB-01", "NU")]
    plauz = _stare(_pas("verifica_plauzibilitate", gasit=True))
    assert [(x["id"], x["eticheta"]) for x in plauz["reguli"]] == [("PL-01", "Semnal")]


# ---------------------------------------------------------------- regresii: cazurile afișate „Găsit” verde din 2.1
def test_regresie_evaluare_cu_regula_nu_nu_mai_e_verde():
    # evalueaza_cale întoarce gasit=True și când calea iese NU; înainte UI-ul arăta „Găsit” verde
    st = _stare(_pas("evalueaza_cale", {"cale_id": "GB-01"}, gasit=True))
    assert st["cheie"] != "verificat" and st["reguli"][0]["rezultat"] == "NU"


@pytest.mark.parametrize("pas", ["verifica_completitudine", "cere_date_client", "escaladeaza", "stabileste_categoria"])
def test_regresie_pasii_fara_verificare_nu_sunt_gasit(pas):
    st = _stare(_pas(pas, gasit=True))
    assert st["cheie"] == "efectuat" and st["clasa"] == "neutru"


@pytest.mark.parametrize("pas", ["verifica_firma", "cauta_certificat"])
def test_regresie_date_doar_din_pdf_nu_sunt_verificate(pas):
    # tools/anaf.py și tools/breeam.py: gasit=True din PDF-ul dosarului, cu verificat_in_registru=False
    st = _stare(_pas(pas, gasit=True, verificat_in_registru=False))
    assert st["cheie"] == "in_dosar"


def test_regresie_emisii_ambigue_nu_sunt_verificate():
    # mai multe modele EEA se potrivesc: gasit=True, dar emisiile nu sunt confirmate
    st = _stare(_pas("cauta_emisii_vehicul", gasit=True, verificat_in_registru=False))
    assert st["cheie"] == "in_dosar"


def test_regresie_sumarul_text_nu_conteaza():
    st = _stare(_pas("verifica_firma", gasit=False, eroare="x", sumar="Găsit, verificat"), campuri={})
    assert st["cheie"] == "negasit"


def test_valoare_goala_sau_vehicule_fara_emisii_nu_conteaza_ca_in_dosar():
    campuri = {"cui": {"valoare": "", "sursa": ""},
               "vehicule": {"valoare": [{"marca": "Ford", "emisii_wltp_gco2_km": None}], "sursa": "L.pdf, p.1"}}
    assert _stare(_pas("verifica_firma", eroare="nu"), campuri)["cheie"] == "negasit"
    assert _stare(_pas("cauta_emisii_vehicul", eroare="nu"), campuri)["cheie"] == "negasit"


def test_eroare_interna_la_evaluare_e_eroare_la_verificare():
    st = _stare(_pas("evalueaza_categoria", gasit=False, eroare="KeyError: 'x'"))
    assert st["cheie"] == "eroare"


def test_trace_vechi_fara_campurile_noi():
    # rezultatele salvate înainte de commit-ul din trace nu au verificat_in_registru / eroare_tehnica
    intrare = {"pas": 1, "actiune": "verifica_firma", "rezultat": {"tool": "verifica_firma", "gasit": True, "eroare": None}}
    assert _stare(intrare)["cheie"] == "verificat"
    assert stare_pas({"pas": 9, "actiune": None, "rezultat": "final"}, REGULI, CAMPURI, _public) is None
