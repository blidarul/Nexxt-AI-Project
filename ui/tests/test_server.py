"""Teste pentru API-ul Green Proof: fiecare endpoint, erorile și limitarea fișierelor la dosare/."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from contracts import RezultatRegula, Verdict
from ui.server import FOLDER_DOSARE, cale_sigura, creeaza_app, imparte_sursa

SECRET = "continut-secret-in-afara-dosarelor"
PDF = b"%PDF-1.4\n% test\n"


def _scrie(cale: Path, continut: object) -> None:
    cale.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(continut, bytes):
        cale.write_bytes(continut)
    elif isinstance(continut, str):
        cale.write_text(continut, encoding="utf-8")
    else:
        cale.write_text(json.dumps(continut, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def radacina(tmp_path: Path) -> Path:
    dosare = tmp_path / "dosare"
    a = dosare / "dosar_a"
    _scrie(a / "01_cerere.pdf", PDF)
    _scrie(a / "CERERE DE FINANȚARE 1.pdf", PDF)
    _scrie(a / "02_registru_breeam.json", {"rating": "Excellent"})
    _scrie(a / "expected.json", {"verdict": "ELIGIBIL"})
    _scrie(a / "extras_mock.json", {"dosar_id": "dosar_a"})
    _scrie(a / "notite.txt", "nu se previzualizează")
    _scrie(a / "_extras" / "raport_extractie.json", {
        "documente_clasificate": [
            {"fisier": "01_cerere.pdf", "tip_detectat": "cerere_finantare", "incredere": 0.95, "id_cerinte": ["D-01"]},
        ],
        "documente_lipsa": [{"id": "D-02", "nume": "Decizia de aprobare", "obligatoriu": True}],
        "campuri_extrase": {
            "tara": {"valoare": "România", "sursa": "01_cerere.pdf, p.2", "incredere": 0.95,
                     "citat": "Țara: România", "citat_verificat": True},
            "descriere_proiect": {"valoare": "Clădire de birouri A", "sursa": "01_cerere.pdf, p.1", "incredere": 0.9},
        },
        "campuri_lipsa": [{"camp": "data_aprobare", "motiv": "negasit"}],
    })
    _scrie(a / "_extras" / "dosar_extras.json", {
        "categorie": {"valoare": "green_buildings"}, "suma_eur": {"valoare": 1000000},
        "chiriasi": [{"nume": "Alfa SRL", "caen": "6201", "m2": 100.0}],
    })
    _scrie(dosare / "dosar_b" / "date.json", {"alt": "dosar"})
    _scrie(dosare / "index.csv", "dosar,descriere,verdict_asteptat\ndosar_a,Dosar de test.,ELIGIBIL\n")
    _scrie(tmp_path / "secret.json", {"secret": SECRET})
    return tmp_path


def _verdict(verdict: str = "ELIGIBIL") -> Verdict:
    return Verdict(
        dosar_id="dosar_a", verdict=verdict,
        reguli=[RezultatRegula(regula_id="G-01", rezultat="OK", dovada="Țara: România", sursa_framework="Anexa B")],
    )


def _client(radacina: Path, evalueaza=None) -> TestClient:
    app = creeaza_app(
        folder_dosare=radacina / "dosare", folder_date=radacina / "date",
        evalueaza=evalueaza or (lambda folder: _verdict()),
        moduri=lambda: {"mod_extractie": "real", "mod_tools": "offline", "mod_agent": "scriptat"},
    )
    return TestClient(app)


def _esueaza(folder: str) -> Verdict:
    raise RuntimeError("agent indisponibil")


# ------------------------------------------------------------------ stare și listă

def test_stare(radacina):
    raspuns = _client(radacina).get("/api/stare")
    assert raspuns.status_code == 200
    assert raspuns.json() == {"produs": "Green Proof", "mod_extractie": "real", "mod_tools": "offline", "mod_agent": "scriptat"}


def test_lista_dosare(radacina):
    raspuns = _client(radacina).get("/api/dosare")
    assert raspuns.status_code == 200
    dosare = {d["id"]: d for d in raspuns.json()}
    assert list(dosare) == ["dosar_a", "dosar_b"]
    a = dosare["dosar_a"]
    assert a["descriere"] == "Dosar de test."
    assert a["proiect"] == "Clădire de birouri A"
    assert a["categorie"] == "green_buildings" and a["suma_eur"] == 1000000
    assert a["nr_documente"] == 1 and a["nr_documente_lipsa"] == 1
    assert a["status"] == "in_asteptare" and a["verdict_salvat"] is None
    # Un dosar fără date extrase apare totuși, cu câmpurile goale
    assert dosare["dosar_b"]["categorie"] is None


def test_lista_fara_folder_dosare(tmp_path):
    client = TestClient(creeaza_app(folder_dosare=tmp_path / "nu_exista", folder_date=tmp_path / "date"))
    assert client.get("/api/dosare").json() == []


# ------------------------------------------------------------------ detalii

def test_detalii_dosar(radacina):
    raspuns = _client(radacina).get("/api/dosare/dosar_a")
    assert raspuns.status_code == 200
    d = raspuns.json()
    fisiere = {doc["fisier"]: doc for doc in d["documente"]}
    # Fișierele de evaluare, .txt și folderele interne (_extras) nu apar
    assert set(fisiere) == {"01_cerere.pdf", "02_registru_breeam.json", "CERERE DE FINANȚARE 1.pdf"}
    cerere = fisiere["01_cerere.pdf"]
    assert cerere["provenienta"] == "client" and cerere["tip_detectat"] == "cerere_finantare"
    assert cerere["cerinte"] == ["D-01"] and cerere["url"] == "/api/dosare/dosar_a/fisiere/01_cerere.pdf"
    assert fisiere["02_registru_breeam.json"]["provenienta"] == "registru"
    tara = next(c for c in d["campuri"] if c["camp"] == "tara")
    assert (tara["fisier"], tara["pagina"], tara["citat_verificat"]) == ("01_cerere.pdf", 2, True)
    assert d["documente_lipsa"][0]["id"] == "D-02"
    assert d["campuri_lipsa"][0]["camp"] == "data_aprobare"
    assert d["chiriasi"][0]["caen"] == "6201"
    assert d["rezultat"] is None and d["decizie"] is None and d["status"] == "in_asteptare"


@pytest.mark.parametrize("dosar_id", ["nu_exista", "..", "_extras", "dosar_a%2F..%2Fdosar_b"])
def test_detalii_dosar_inexistent(radacina, dosar_id):
    assert _client(radacina).get(f"/api/dosare/{dosar_id}").status_code == 404


# ------------------------------------------------------------------ evaluare și rezultat salvat

def test_evaluare_salveaza_rezultatul(radacina):
    client = _client(radacina)
    assert client.get("/api/dosare/dosar_a/rezultat").status_code == 404

    raspuns = client.post("/api/dosare/dosar_a/evaluare")
    assert raspuns.status_code == 200
    r = raspuns.json()
    assert r["din_salvare"] is False and r["eroare"] is None
    assert r["verdict"]["verdict"] == "ELIGIBIL" and r["recomandare"] == "aprobat"
    assert r["salvat_la"]
    # Lanțul de dovezi: regula G-01 trimite la câmpul „tara” din pagina 2 a cererii
    dovada = r["dovezi"]["G-01"][0]
    assert (dovada["camp"], dovada["fisier"], dovada["pagina"]) == ("tara", "01_cerere.pdf", 2)
    assert r["nume_reguli"]["G-01"].startswith("Tara eligibila")

    assert (radacina / "date" / "rezultate" / "dosar_a.json").is_file()
    salvat = client.get("/api/dosare/dosar_a/rezultat").json()
    assert salvat["din_salvare"] is True and salvat["verdict"]["verdict"] == "ELIGIBIL"
    assert client.get("/api/dosare").json()[0]["verdict_salvat"] == "ELIGIBIL"


@pytest.mark.parametrize("verdict,recomandare", [
    ("ELIGIBIL_CU_MONITORIZARE", "aprobat"), ("NEELIGIBIL", "respins"), ("EXCEPTIE_ESCALADARE_COMITET", "interventie"),
])
def test_recomandare_dupa_verdict(radacina, verdict, recomandare):
    raspuns = _client(radacina, lambda folder: _verdict(verdict)).post("/api/dosare/dosar_a/evaluare")
    assert raspuns.json()["recomandare"] == recomandare


def test_evaluare_esuata_foloseste_rezultatul_salvat(radacina):
    _client(radacina).post("/api/dosare/dosar_a/evaluare")
    raspuns = _client(radacina, _esueaza).post("/api/dosare/dosar_a/evaluare")
    assert raspuns.status_code == 200
    r = raspuns.json()
    assert r["din_salvare"] is True and "agent indisponibil" in r["eroare"]
    assert r["verdict"]["verdict"] == "ELIGIBIL" and r["salvat_la"]


def test_evaluare_esuata_fara_rezultat_salvat(radacina):
    raspuns = _client(radacina, _esueaza).post("/api/dosare/dosar_a/evaluare")
    assert raspuns.status_code == 503
    assert "agent indisponibil" in raspuns.json()["detail"]


def test_evaluare_dosar_inexistent(radacina):
    assert _client(radacina).post("/api/dosare/nu_exista/evaluare").status_code == 404
    assert _client(radacina).get("/api/dosare/nu_exista/rezultat").status_code == 404


def test_rezultat_salvat_corupt_e_ignorat(radacina):
    _scrie(radacina / "date" / "rezultate" / "dosar_a.json", "{nu e json")
    assert _client(radacina).get("/api/dosare/dosar_a/rezultat").status_code == 404


# ------------------------------------------------------------------ fișiere

def test_fisier_pdf_inline(radacina):
    raspuns = _client(radacina).get("/api/dosare/dosar_a/fisiere/01_cerere.pdf")
    assert raspuns.status_code == 200
    assert raspuns.headers["content-type"] == "application/pdf"
    assert raspuns.headers["content-disposition"].startswith("inline")
    assert raspuns.content == PDF


def test_fisier_json_si_nume_cu_diacritice(radacina):
    client = _client(radacina)
    raspuns = client.get("/api/dosare/dosar_a/fisiere/02_registru_breeam.json")
    assert raspuns.status_code == 200 and raspuns.json() == {"rating": "Excellent"}
    assert raspuns.headers["content-type"].startswith("application/json")
    url = client.get("/api/dosare/dosar_a").json()["documente"][-1]["url"]
    assert client.get(url).content == PDF


@pytest.mark.parametrize("cale", [
    "nu_exista.pdf",
    "notite.txt",                # extensie care nu se previzualizează
    "expected.json",             # răspunsul așteptat nu se arată
    "extras_mock.json",
    "_extras",                   # folder, nu fișier
])
def test_fisier_refuzat(radacina, cale):
    assert _client(radacina).get(f"/api/dosare/dosar_a/fisiere/{cale}").status_code == 404


@pytest.mark.parametrize("cale", [
    "..%2F..%2Fsecret.json",
    "%2e%2e/%2e%2e/secret.json",
    "%2E%2E%2F%2E%2E%2Fsecret.json",
    "..%5C..%5Csecret.json",
    "_extras/..%2F..%2F..%2Fsecret.json",
    "..%2Fdosar_b%2Fdate.json",  # alt dosar: tot în afara folderului cerut
])
def test_fisier_iesire_din_dosar_refuzata(radacina, cale):
    raspuns = _client(radacina).get(f"/api/dosare/dosar_a/fisiere/{cale}")
    assert raspuns.status_code == 404
    # Refuzul vine din verificarea căii (cererea a ajuns la endpoint), nu din rutare
    assert raspuns.json()["detail"].startswith("Fișierul nu există")
    assert SECRET not in raspuns.text


def test_fisier_cale_absoluta_refuzata(radacina):
    absoluta = quote(str(radacina / "secret.json"), safe="")
    raspuns = _client(radacina).get(f"/api/dosare/dosar_a/fisiere/{absoluta}")
    assert raspuns.status_code == 404 and SECRET not in raspuns.text


def test_fisier_dosar_iesire_prin_id(radacina):
    raspuns = _client(radacina).get("/api/dosare/..%2F/fisiere/secret.json")
    assert raspuns.status_code == 404 and SECRET not in raspuns.text


def test_cale_sigura(radacina):
    folder = radacina / "dosare" / "dosar_a"
    assert cale_sigura(folder, "01_cerere.pdf") == (folder / "01_cerere.pdf").resolve()
    for cale in ["../../secret.json", "..\\..\\secret.json", str(radacina / "secret.json"), "", "a\x00.pdf",
                 "_extras/../../dosar_b/date.json"]:
        assert cale_sigura(folder, cale) is None, cale


def test_imparte_sursa():
    assert imparte_sursa("01_cerere_finantare.pdf, p.3") == ("01_cerere_finantare.pdf", 3)
    assert imparte_sursa("BREEAM.pdf") == ("BREEAM.pdf", None)
    assert imparte_sursa("") == (None, None)


# ------------------------------------------------------------------ decizii

def test_decizia_cere_solutia_deschisa(radacina):
    raspuns = _client(radacina).post("/api/dosare/dosar_a/decizie", json={"decizie": "aprobat"})
    assert raspuns.status_code == 409
    assert "soluția" in raspuns.json()["detail"]


@pytest.mark.parametrize("decizie", ["respins", "interventie"])
def test_comentariu_obligatoriu(radacina, decizie):
    client = _client(radacina)
    client.post("/api/dosare/dosar_a/evaluare")
    for comentariu in ["", "   "]:
        raspuns = client.post("/api/dosare/dosar_a/decizie",
                              json={"decizie": decizie, "comentariu": comentariu, "confirmat": True})
        assert raspuns.status_code == 422


def test_decizie_invalida(radacina):
    client = _client(radacina)
    client.post("/api/dosare/dosar_a/evaluare")
    assert client.post("/api/dosare/dosar_a/decizie", json={"decizie": "poate"}).status_code == 422
    assert client.post("/api/dosare/dosar_a/decizie", json={}).status_code == 422
    assert client.post("/api/dosare/nu_exista/decizie", json={"decizie": "aprobat"}).status_code == 404


def test_decizie_la_fel_ca_agentul(radacina):
    client = _client(radacina)
    client.post("/api/dosare/dosar_a/evaluare")
    raspuns = client.post("/api/dosare/dosar_a/decizie", json={"decizie": "aprobat"})
    assert raspuns.status_code == 200
    d = raspuns.json()
    assert d["dosar"] == "dosar_a" and d["decizie"] == "aprobat" and d["comentariu"] == ""
    assert d["recomandare_agent"] == "aprobat" and d["verdict_agent"] == "ELIGIBIL"
    assert d["difera_de_agent"] is False and d["data"]


def test_decizie_diferita_cere_confirmare(radacina):
    client = _client(radacina)
    client.post("/api/dosare/dosar_a/evaluare")
    cerere = {"decizie": "respins", "comentariu": "Lipsește decizia de aprobare."}
    raspuns = client.post("/api/dosare/dosar_a/decizie", json=cerere)
    assert raspuns.status_code == 409
    detaliu = raspuns.json()["detail"]
    assert detaliu["necesita_confirmare"] is True and detaliu["recomandare_agent"] == "aprobat"
    assert client.get("/api/decizii").json() == []

    raspuns = client.post("/api/dosare/dosar_a/decizie", json={**cerere, "confirmat": True})
    assert raspuns.status_code == 200
    assert raspuns.json()["difera_de_agent"] is True
    assert raspuns.json()["comentariu"] == "Lipsește decizia de aprobare."


def test_decizia_persista_si_ultima_conteaza(radacina):
    client = _client(radacina)
    client.post("/api/dosare/dosar_a/evaluare")
    client.post("/api/dosare/dosar_a/decizie", json={"decizie": "aprobat"})
    client.post("/api/dosare/dosar_a/decizie",
                json={"decizie": "interventie", "comentariu": "Verific chiriașul.", "confirmat": True})

    # Un server nou (ca după refresh sau repornire) citește aceleași decizii de pe disc
    alt_client = _client(radacina)
    istoric = alt_client.get("/api/decizii").json()
    assert [d["decizie"] for d in istoric] == ["aprobat", "interventie"]
    assert alt_client.get("/api/dosare/dosar_a").json()["decizie"]["decizie"] == "interventie"
    assert alt_client.get("/api/dosare").json()[0]["status"] == "interventie"
    salvat = json.loads((radacina / "date" / "decizii.json").read_text(encoding="utf-8"))
    assert salvat[-1]["comentariu"] == "Verific chiriașul."


def test_reset_decizii(radacina):
    client = _client(radacina)
    client.post("/api/dosare/dosar_a/evaluare")
    client.post("/api/dosare/dosar_a/decizie", json={"decizie": "aprobat"})
    raspuns = client.delete("/api/decizii")
    assert raspuns.status_code == 200
    assert client.get("/api/decizii").json() == []
    assert client.get("/api/dosare").json()[0]["status"] == "in_asteptare"
    # Rezultatul agentului rămâne salvat (pentru demo fără agent)
    assert client.get("/api/dosare/dosar_a/rezultat").status_code == 200


def test_decizii_fisier_corupt(radacina):
    _scrie(radacina / "date" / "decizii.json", "{stricat")
    client = _client(radacina)
    assert client.get("/api/decizii").json() == []
    client.post("/api/dosare/dosar_a/evaluare")
    assert client.post("/api/dosare/dosar_a/decizie", json={"decizie": "aprobat"}).status_code == 200


# ------------------------------------------------------------------ pagina și agentul real

def test_pagina_principala(radacina):
    client = _client(radacina)
    raspuns = client.get("/")
    assert raspuns.status_code == 200 and raspuns.headers["content-type"].startswith("text/html")
    assert "<title>Green Proof</title>" in raspuns.text and 'lang="ro"' in raspuns.text
    for cale in ["/static/style.css", "/static/app.js", "/static/fonts/geist-latin-ext-wght-normal.woff2"]:
        assert client.get(cale).status_code == 200, cale
    assert client.get("/static/..%2F..%2Fcontracts.py").status_code == 404


def test_agentul_real_pe_un_dosar(tmp_path):
    """Integrare: dosarele reale și agentul real (modul din .env), cu deciziile într-un folder temporar."""
    client = TestClient(creeaza_app(folder_dosare=FOLDER_DOSARE, folder_date=tmp_path))
    raspuns = client.post("/api/dosare/dosar_01_complet_eligibil/evaluare")
    assert raspuns.status_code == 200
    r = raspuns.json()
    assert r["din_salvare"] is False
    assert r["verdict"]["verdict"] in {"ELIGIBIL", "ELIGIBIL_CU_MONITORIZARE", "NEELIGIBIL", "EXCEPTIE_ESCALADARE_COMITET"}
    assert r["verdict"]["trace"] and r["recomandare"] in {"aprobat", "respins", "interventie"}
    assert any(r["dovezi"].values())
    detalii = client.get("/api/dosare/dosar_01_complet_eligibil").json()
    assert all(d["fisier"] not in {"expected.json", "extras_mock.json"} for d in detalii["documente"])
    assert client.get(detalii["documente"][0]["url"]).status_code == 200


# ------------------------------------------------------------------ raport și anularea deciziei

def test_raport_cere_evaluare(radacina):
    client = _client(radacina)
    assert client.get("/api/dosare/dosar_a/raport").status_code == 404
    assert client.get("/api/dosare/dosar_a/raport.html").status_code == 404
    assert client.get("/api/dosare/nu_exista/raport").status_code == 404


def test_raport_structurat_si_printabil(radacina):
    client = _client(radacina)
    client.post("/api/dosare/dosar_a/evaluare")
    r = client.get("/api/dosare/dosar_a/raport").json()
    assert r["verdict"] == "ELIGIBIL" and r["categorie"] == "Green Buildings" and r["salvat_la"]
    assert [s["cheie"] for s in r["sectiuni"]] == ["indeplinite", "de_verificat"]
    lipsa = r["sectiuni"][1]["grupuri"][-1]
    assert lipsa["cheie"] == "documente_lipsa" and lipsa["elemente"][0]["id"] == "D-02"
    pagina = client.get("/api/dosare/dosar_a/raport.html")
    assert pagina.status_code == 200 and pagina.headers["content-type"].startswith("text/html")
    assert "Clădire de birouri A" in pagina.text and "✓ Ce îndeplinește" in pagina.text


def test_anuleaza_decizia(radacina):
    client = _client(radacina)
    assert client.delete("/api/dosare/dosar_a/decizie").status_code == 404
    client.post("/api/dosare/dosar_a/evaluare")
    client.post("/api/dosare/dosar_a/decizie", json={"decizie": "aprobat"})
    client.post("/api/dosare/dosar_a/decizie", json={"decizie": "interventie", "comentariu": "Verific.", "confirmat": True})
    raspuns = client.delete("/api/dosare/dosar_a/decizie")
    assert raspuns.status_code == 200
    assert raspuns.json()["anulata"]["decizie"] == "interventie" and raspuns.json()["status"] == "aprobat"
    client.delete("/api/dosare/dosar_a/decizie")
    assert client.get("/api/dosare").json()[0]["status"] == "in_asteptare"
    assert client.delete("/api/dosare/nu_exista/decizie").status_code == 404
