"""Teste de contract pentru tools: ToolResult la orice intrare, offline și online (rețeaua e simulată)."""

import csv
import shutil
from pathlib import Path

import pytest

from contracts import DosarExtras, StareDosar, ToolResult
from registry import TOOLS, apeleaza, schema_pentru_llm
from tools import anaf, breeam, emisii_vehicul, factor_emisie
from tools.anaf import verifica_firma
from tools.breeam import cauta_certificat, parseaza_rezultate
from tools.data import descarca_eea, descarca_ember
from tools.emisii_vehicul import cauta_emisii_vehicul
from tools.factor_emisie import factor_emisie_tara
from tools.tari import corespondenta_tari, gaseste_tara, tari_anexa_b

RADACINA = Path(__file__).resolve().parents[2]
DOSAR = RADACINA / "dosare" / "dosar3"
TOOLS_NOI = ["verifica_firma", "cauta_certificat", "cauta_emisii_vehicul", "factor_emisie_tara"]
FUNCTII = {"verifica_firma": verifica_firma, "cauta_certificat": cauta_certificat,
           "cauta_emisii_vehicul": cauta_emisii_vehicul, "factor_emisie_tara": factor_emisie_tara}


def _stare(folder=DOSAR):
    gol = {"valoare": None}
    extras = DosarExtras(dosar_id="t", cui=gol, suma_eur=gol, cota_banca=gol, data_aprobare=gol, tara=gol,
                         adresa_cladire=gol, suprafata_m2=gol, stadiu_cladire=gol, nr_certificat_declarat=gol)
    return StareDosar(dosar_folder=str(folder), extras=extras)


@pytest.fixture(autouse=True)
def mod_offline(monkeypatch):
    monkeypatch.setenv("MOD_TOOLS", "offline")


@pytest.fixture
def fara_retea(monkeypatch, tmp_path):
    """Orice cerere HTTP eșuează ca la o rețea oprită; cache-ul local e gol (izolat de tools/cache/)."""
    import requests

    import tools._comun

    monkeypatch.setattr(tools._comun, "FOLDER_CACHE", tmp_path / "cache")

    def cade(*a, **k):
        raise requests.ConnectionError("rețea oprită (test)")

    monkeypatch.setattr(requests, "get", cade)
    monkeypatch.setattr(requests, "post", cade)
    monkeypatch.setenv("MOD_TOOLS", "online")


# ----------------------------------------------------------------------------- contract comun
INTRARI_PROASTE = [None, {}, [], "text", 123, {"x": 1}, {"cui": None}, {"marca": None, "model": None},
                   {"tara": ""}, {"tara": "România", "an": "anul trecut"}, {"nr_certificat": ""},
                   {"cui": "∑∂ƒ" * 50}, {"marca": "a" * 10_000, "model": "b"}]


@pytest.mark.parametrize("nume", TOOLS_NOI)
@pytest.mark.parametrize("argumente", INTRARI_PROASTE)
def test_mereu_toolresult_prin_registry_si_direct(nume, argumente):
    for rezultat in (apeleaza(nume, argumente, _stare()), FUNCTII[nume](argumente, _stare())):
        assert isinstance(rezultat, ToolResult)
        assert rezultat.tool == nume
        if not rezultat.gasit:
            assert rezultat.eroare


@pytest.mark.parametrize("nume", TOOLS_NOI)
def test_fara_stare_sau_cu_dosar_inexistent(nume, tmp_path):
    argumente = {"verifica_firma": {"cui": "9900000030"}, "cauta_certificat": {"nr_certificat": "X-1"},
                 "cauta_emisii_vehicul": {"marca": "Exemplu", "model": "EV-Van"},
                 "factor_emisie_tara": {"tara": "Romania"}}[nume]
    for stare in (None, _stare(tmp_path / "nu_exista")):
        assert isinstance(FUNCTII[nume](argumente, stare), ToolResult)


def test_toate_tools_sunt_in_registry_cu_schema():
    assert set(TOOLS_NOI) <= set(TOOLS)
    scheme = {s["function"]["name"]: s["function"]["parameters"] for s in schema_pentru_llm()}
    assert set(scheme["cauta_emisii_vehicul"]["required"]) == {"marca", "model"}
    assert scheme["factor_emisie_tara"]["required"] == ["tara"]


# ----------------------------------------------------------------------------- verifica_firma
def test_firma_offline_gasita_cu_prefix_ro():
    r = verifica_firma({"cui": "RO 9900000030"}, _stare())
    assert r.gasit and r.date["date_generale"]["cod_CAEN"] == "6820"
    assert r.date["stare_inactiv"]["statusInactivi"] is False


def test_firma_offline_alt_cui_nu_e_gasit():
    r = verifica_firma({"cui": "12345678"}, _stare())
    assert not r.gasit and "12345678" in r.eroare


def test_firma_cui_invalid():
    r = verifica_firma({"cui": "abc"}, _stare())
    assert not r.gasit and "CUI invalid" in r.eroare


def test_firma_din_pdf_nu_inventeaza(tmp_path):
    shutil.copy(DOSAR / "RASPUNS_ANAF.pdf", tmp_path / "fisa.pdf")  # nume neobișnuit: se găsește după clasificare
    (tmp_path / "_extras").mkdir()
    (tmp_path / "_extras" / "raport_extractie.json").write_text(
        '{"documente_clasificate": [{"fisier": "fisa.pdf", "tip_din_continut": "raspuns_anaf"}]}', encoding="utf-8")
    r = verifica_firma({"cui": "9900000030"}, _stare(tmp_path))
    assert r.gasit and r.date["verificat_in_registru"] is False
    assert r.date["date_generale"]["cod_CAEN"] == "6820" and "extras direct din document" in r.sursa


def test_firma_online_fara_retea_cade_pe_offline(fara_retea):
    r = verifica_firma({"cui": "9900000030"}, _stare())
    assert r.gasit and "indisponibil" in r.sursa


def test_firma_online_cui_inexistent_e_raspuns_nu_eroare_de_retea(monkeypatch):
    monkeypatch.setenv("MOD_TOOLS", "online")
    monkeypatch.setattr(anaf, "_interogheaza_anaf", lambda cui: {"found": [], "notFound": [int(cui)]})
    r = verifica_firma({"cui": "9900000030"}, _stare())
    assert not r.gasit and r.sursa == anaf.SURSA_API


def test_eroarea_tehnica_e_marcata_separat_de_negasit(tmp_path):
    # „nu există în registru” e un răspuns, nu o eroare tehnică
    assert not verifica_firma({"cui": "12345678"}, _stare()).date.get("eroare_tehnica")
    assert not cauta_certificat({"nr_certificat": "BREEAM-EXEMPLU-0099"}, _stare()).date.get("eroare_tehnica")
    # argument invalid, nicio sursă disponibilă, argumente greșite: verificarea nu a putut rula
    assert verifica_firma({"cui": "abc"}, _stare()).date["eroare_tehnica"] is True
    assert verifica_firma({"cui": "9900000030"}, _stare(tmp_path)).date["eroare_tehnica"] is True
    assert cauta_certificat({"nr_certificat": "  "}, _stare()).date["eroare_tehnica"] is True
    assert verifica_firma({"cod": 1}, _stare()).date["eroare_tehnica"] is True


# ----------------------------------------------------------------------------- cauta_certificat
def test_certificat_offline_numar_corect_si_gresit():
    assert cauta_certificat({"nr_certificat": "breeam-exemplu-0003"}, _stare()).date["rating"] == "Outstanding"
    gresit = cauta_certificat({"nr_certificat": "BREEAM-EXEMPLU-0099"}, _stare())
    assert not gresit.gasit and "BREEAM-EXEMPLU-0099" in gresit.eroare


def test_certificat_din_pdf_nu_inventeaza(tmp_path):
    shutil.copy(DOSAR / "BREEAM.pdf", tmp_path / "BREEAM.pdf")
    r = cauta_certificat({"nr_certificat": "BREEAM-EXEMPLU-0003"}, _stare(tmp_path))
    assert r.gasit and r.date["verificat_in_registru"] is False and r.date["stage"] == "Final Certificate"
    assert not cauta_certificat({"nr_certificat": "ALT-NUMAR"}, _stare(tmp_path)).gasit


HTML_REGISTRU = """<table><tr><th>Building</th></tr>
<tr> <td><a href="x"> Globalworth Campus - Building A </a></td> <td>Netron Investment </td>
<td>International 2013 New Construction: Offices</td> <td>Excellent <br>70.2% </td> <td>Final</td>
<td>BREEAM-0060-0429</td> <td>Cundall</td> <td> Bucharest <br />020339 </td> <td>Romania</td> </tr></table>"""


def test_registru_breeam_html_se_parseaza():
    [rand] = parseaza_rezultate(HTML_REGISTRU)
    assert rand["rating"] == "Excellent" and rand["score_pct"] == 70.2 and rand["stage"] == "Final"
    assert rand["certificate_no"] == "BREEAM-0060-0429" and rand["town"] == "Bucharest" and rand["postcode"] == "020339"


def test_certificat_online_fara_retea_cade_pe_offline(fara_retea):
    r = cauta_certificat({"nr_certificat": "BREEAM-EXEMPLU-0003"}, _stare())
    assert r.gasit and "indisponibil" in r.sursa


# ----------------------------------------------------------------------------- cauta_emisii_vehicul
@pytest.mark.parametrize("marca,model", [("Exemplu", "EV-Van"), ("exemplu", "ev van"), ("EXEMPLU", "EV_VAN"), ("Exemplu", "evvan")])
def test_emisii_potrivire_toleranta(marca, model):
    r = cauta_emisii_vehicul({"marca": marca, "model": model}, _stare())
    assert r.gasit and r.date["emisii_wltp_gco2_km"] == 0 and r.date["combustibil"] == "electric"
    assert isinstance(r.date["an_date"], int) and r.date["sintetic"] is True


def test_emisii_mai_multe_potriviri_in_candidati():
    r = cauta_emisii_vehicul({"marca": "Exemplu", "model": "PHEV"}, _stare())
    assert r.gasit and r.date["ambiguu"] and r.date["emisii_wltp_gco2_km"] is None
    assert {c["model"] for c in r.date["candidati"]} == {"PHEV-Van", "Cargo-PHEV"}


def test_emisii_model_negasit():
    r = cauta_emisii_vehicul({"marca": "Exemplu", "model": "Camion-X"}, _stare())
    assert not r.gasit and "Camion-X" in r.eroare and "modele" in r.eroare
    assert "marca nu există" in cauta_emisii_vehicul({"marca": "Necunoscut", "model": "A"}, _stare()).eroare


def test_emisii_online_fara_retea_cade_pe_offline(fara_retea):
    r = cauta_emisii_vehicul({"marca": "Exemplu", "model": "PHEV-Van"}, _stare())
    assert r.gasit and r.date["emisii_wltp_gco2_km"] == 45 and "indisponibil" in r.sursa


def test_fisierul_offline_marcheaza_valorile_sintetice():
    with open(emisii_vehicul.CALE_CSV, encoding="utf-8", newline="") as f:
        randuri = list(csv.DictReader(f))
    assert randuri and all(r["sursa"] for r in randuri)
    assert all(r["sursa"].startswith("SINTETIC") or r["sursa"].startswith("EEA") for r in randuri)


def test_eea_agregare_pe_marca_model_combustibil(tmp_path):
    cale = tmp_path / "eea.csv"
    cale.write_text(
        "ID,Mk,Cn,Ft,Fm,Ewltp (g/km),year,Electric range (km),z (Wh/km)\n"
        "1,DACIA,SPRING,electric,E,0,2024,225,140\n"
        "2,DACIA,SPRING,electric,E,0,2025,225,140\n"
        "3,DACIA,SANDERO,petrol,M,120,2025,,\n"
        "4,DACIA,SANDERO,petrol,M,130,2025,,\n"
        "5,DACIA,SANDERO,lpg,B,110,2025,,\n"
        "6,DACIA,SANDERO,petrol,M,,2025,,\n"
        "7,TOYOTA,TOYOTA COROLLA,petrol/electric,P,102,2025,,\n"
        "8,VOLVO,XC60,petrol/electric,P,177,2025,,\n"
        "9,VOLVO,XC60,petrol/electric,P,23,2025,80,180\n"
        "10,MERCEDES - BENZ,GLC,diesel,M,150,2025,,\n"
        "11,MERCEDES-BENZ,GLC,diesel,M,160,2025,,\n"
        "12,MERCEDES-BENZ,GLA,diesel,M,140,2025,,\n"
        '13,"VOLKSWAGEN, VW",VW GOLF,petrol,M,125,2025,,\n', encoding="utf-8")
    randuri = descarca_eea.agrega(descarca_eea.citeste_fisier(cale), top=50, sursa="EEA test")
    grup = {(r["marca"], r["model"], r["combustibil"]): r for r in randuri}
    # combustibilii diferiți ai aceluiași model rămân separați
    assert grup[("DACIA", "SANDERO", "petrol")]["emisii_wltp_gco2_km"] == 125
    assert grup[("DACIA", "SANDERO", "lpg")]["emisii_wltp_gco2_km"] == 110
    assert grup[("DACIA", "SPRING", "electric")]["an_date"] == 2025
    # hibrid simplu vs plug-in: după autonomia electrică, nu după Fm
    assert grup[("VOLVO", "XC60", "petrol/electric")]["emisii_wltp_gco2_km"] == 177
    assert grup[("VOLVO", "XC60", "petrol/electric (plug-in)")]["emisii_wltp_gco2_km"] == 23
    # marca scoasă din model, grafii unificate, alias din sursă
    assert ("TOYOTA", "COROLLA", "petrol/electric") in grup
    assert grup[("MERCEDES-BENZ", "GLC", "diesel")]["nr_inmatriculari"] == 2
    assert grup[("VOLKSWAGEN", "GOLF", "petrol")]["alias_marca"] == "VW"
    assert descarca_eea._mediana_ponderata([(10, 1), (20, 1)]) == 15


def test_emisii_alias_marca_si_marca_repetata_in_model(tmp_path, monkeypatch):
    cale = tmp_path / "emisii.csv"
    cale.write_text("marca,model,combustibil,emisii_wltp_gco2_km,an_date,nr_inmatriculari,sursa,alias_marca\n"
                    "VOLKSWAGEN,GOLF,petrol,125,2025,10,EEA test,VW\n"
                    "TOYOTA,COROLLA,petrol/electric,102,2025,10,EEA test,\n", encoding="utf-8")
    monkeypatch.setattr(emisii_vehicul, "CALE_CSV", cale)
    assert cauta_emisii_vehicul({"marca": "VW", "model": "Golf"}, None).date["emisii_wltp_gco2_km"] == 125
    assert cauta_emisii_vehicul({"marca": "Toyota", "model": "Toyota Corolla"}, None).date["emisii_wltp_gco2_km"] == 102


def test_eea_fara_retea_eroare_clara(fara_retea, capsys):
    with pytest.raises(SystemExit) as exc:
        list(descarca_eea.citeste_discodata(descarca_eea.TABEL_IMPLICIT))
    assert "EROARE" in str(exc.value) and "--din-fisier" in str(exc.value)


# ----------------------------------------------------------------------------- factor_emisie_tara
@pytest.mark.parametrize("tara", ["România", "Romania", "romania", "ROU", " ROMÂNIA "])
def test_factor_tara_ro_si_en_ultimul_an(tara):
    r = factor_emisie_tara({"tara": tara}, _stare())
    assert r.gasit and r.date["tip"] == "proxy" and r.date["tara"] == "Romania"
    assert r.date["kgco2_kwh"] == pytest.approx(r.date["gco2e_kwh"] / 1000)
    with open(factor_emisie.CALE_CSV, encoding="utf-8") as f:
        ani_ro = [int(x["an"]) for x in csv.DictReader(f) if x["iso3"] == "ROU"]
    assert r.date["an"] == max(ani_ro)


def test_factor_an_cerut_si_an_viitor():
    assert factor_emisie_tara({"tara": "Germania", "an": 2020}, _stare()).date["an"] == 2020
    viitor = factor_emisie_tara({"tara": "Germany", "an": 2099}, _stare())
    assert viitor.gasit and viitor.date["an"] < 2099 and viitor.date["an_cerut"] == 2099
    vechi = factor_emisie_tara({"tara": "Albania", "an": 1995}, _stare())  # seria Albaniei începe în 2000
    assert not vechi.gasit and "1995" in vechi.eroare


def test_factor_tara_necunoscuta():
    r = factor_emisie_tara({"tara": "Atlantida"}, _stare())
    assert not r.gasit and "Atlantida" in r.eroare


def test_factor_online_fara_retea_cade_pe_offline(fara_retea):
    r = factor_emisie_tara({"tara": "Romania"}, _stare())
    assert r.gasit and "indisponibil" in r.sursa


def test_fiecare_tara_din_anexa_b_are_corespondenta_si_date():
    tari = corespondenta_tari()
    assert [t for t in tari_anexa_b() if t not in tari] == []
    with open(factor_emisie.CALE_CSV, encoding="utf-8") as f:
        cu_date = {r["iso3"] for r in csv.DictReader(f)}
    assert [t for t in tari_anexa_b() if tari[t]["iso3"] not in cu_date] == []
    assert gaseste_tara("Țările de Jos")["iso3"] == "NLD" and gaseste_tara("SUA")["anexa_b"]


def test_ember_filtreaza_doar_tarile_cerute():
    text = "Entity,Code,Year,Carbon intensity\nRomania,ROU,2024,251.33\nWorld,OWID_WRL,2024,470\nRomania,ROU,2025,\n"
    assert descarca_ember.filtreaza(text, {"ROU": "Romania"}) == [
        {"tara": "Romania", "iso3": "ROU", "an": 2024, "gco2e_kwh": 251.33, "sursa": descarca_ember.SURSA}]
    with pytest.raises(SystemExit):
        descarca_ember.filtreaza("a,b\n1,2\n", {"ROU": "Romania"})


def _zip_eea(cale, randuri):
    import zipfile
    antet = "ID\tMs\tMk\tCn\tFt\tEwltp (g/km)\tyear\tAlta coloana\n"
    corp = "".join(f"{i}\t{ms}\t{mk}\t{cn}\t{ft}\t{e}\t2025\tx\n" for i, (ms, mk, cn, ft, e) in enumerate(randuri))
    with zipfile.ZipFile(cale, "w") as z:
        z.writestr("readme.txt", "x")
        z.writestr("data.csv", antet + corp)


def test_eea_din_zip_in_flux_cu_filtru_tara_si_limita(tmp_path):
    cale = tmp_path / "eea.zip"
    _zip_eea(cale, [("RO", "DACIA", "SPRING", "electric", 0), ("DE", "VW", "GOLF", "petrol", 130),
                    ("RO", "VW", "GOLF", "petrol", 120), ("ro", "VW", "GOLF", "petrol", 124)])
    toate = {r["model"]: r for r in descarca_eea.agrega(descarca_eea.citeste_fisier(cale), 10, "t")}
    assert toate["GOLF"]["nr_inmatriculari"] == 3 and toate["GOLF"]["emisii_wltp_gco2_km"] == 124
    ro = {r["model"]: r for r in descarca_eea.agrega(descarca_eea.citeste_fisier(cale, tara="RO"), 10, "t")}
    assert ro["GOLF"]["nr_inmatriculari"] == 2 and ro["GOLF"]["emisii_wltp_gco2_km"] == 122
    assert sum(1 for _ in descarca_eea.citeste_fisier(cale, max_randuri=2)) == 2


def test_eea_cli_din_fisier_pastreaza_randurile_sintetice(tmp_path, monkeypatch):
    iesire = tmp_path / "emisii.csv"
    shutil.copy(emisii_vehicul.CALE_CSV, iesire)
    monkeypatch.setattr(descarca_eea, "CALE_IESIRE", iesire)
    cale = tmp_path / "eea.zip"
    _zip_eea(cale, [("RO", "DACIA", "SPRING", "electric", 0)] * 3 + [("RO", "VW", "GOLF", "petrol", 120)])
    descarca_eea.main(["--din-fisier", str(cale), "--top", "1"])
    with open(iesire, encoding="utf-8", newline="") as f:
        randuri = list(csv.DictReader(f))
    assert sum(r["sursa"].startswith("SINTETIC") for r in randuri) == 5
    reale = [r for r in randuri if r["sursa"].startswith("EEA")]
    assert [(r["marca"], r["model"], r["nr_inmatriculari"]) for r in reale] == [("DACIA", "SPRING", "3")]
