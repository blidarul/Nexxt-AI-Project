"""Teste pentru procesarea fișierelor .json în _brut și căutarea engine-ului exclusiv în _brut."""

import json

from contracts import Camp, DosarExtras, StareDosar
from engine.evaluator_generic import obtine_valoare_camp
from extraction.extrage_brut import proceseaza_dosar


def test_extragere_adapteaza_json_in_sablon_brut(tmp_path):
    """Verifică că extragerea transformă un fișier .json din dosar în formatul șablon din _brut."""
    dosar_dir = tmp_path / "dosar_test"
    dosar_dir.mkdir()

    # Creăm un fișier JSON la rădăcina dosarului
    breeam_data = {
        "building_name": "Test Eco Tower",
        "rating": "Outstanding",
        "stage": "Final",
        "certificate_no": "BREEAM-TEST-1234",
    }
    breeam_file = dosar_dir / "02_registru_breeam.json"
    with open(breeam_file, "w", encoding="utf-8") as f:
        json.dump(breeam_data, f, indent=2)

    anaf_data = {
        "found": [
            {
                "date_generale": {
                    "cui": 9999999999,
                    "denumire": "ECO SRL",
                    "cod_CAEN": "6820",
                }
            }
        ]
    }
    anaf_file = dosar_dir / "05_raspuns_anaf.json"
    with open(anaf_file, "w", encoding="utf-8") as f:
        json.dump(anaf_data, f, indent=2)

    # Rulăm procesarea dosarului
    stats = proceseaza_dosar(dosar_dir)
    assert stats["json"] == 2
    assert stats["erori"] == 0

    folder_brut = dosar_dir / "_brut"
    assert (folder_brut / "02_registru_breeam.json").exists()
    assert (folder_brut / "05_raspuns_anaf.json").exists()
    assert (folder_brut / "index.json").exists()

    # Verificăm structura fișierului adaptat conform șablonului
    with open(folder_brut / "02_registru_breeam.json", "r", encoding="utf-8") as f:
        doc = json.load(f)

    assert doc["fisier"] == "02_registru_breeam.json"
    assert doc["dosar"] == "dosar_test"
    assert doc["tip_din_nume"] == "certificat_sustenabilitate"
    assert doc["nr_pagini"] == 1
    assert "extras_la" in doc
    assert len(doc["pagini"]) == 1
    assert "text" in doc["pagini"][0]
    assert "Outstanding" in doc["pagini"][0]["text"]
    assert len(doc["pagini"][0]["tabele"]) >= 1
    assert doc["rating"] == "Outstanding"


def test_engine_cauta_exclusiv_in_brut(tmp_path):
    """Verifică că motorul caută fișierele .json exclusiv în _brut și NU în rădăcina dosarului."""
    dosar_dir = tmp_path / "dosar_engine"
    dosar_dir.mkdir()
    folder_brut = dosar_dir / "_brut"
    folder_brut.mkdir()

    # Punem un fișier doar în _brut, NU la rădăcină
    anaf_brut = {
        "fisier": "05_raspuns_anaf.json",
        "dosar": "dosar_engine",
        "tip_din_nume": "raspuns_anaf",
        "nr_pagini": 1,
        "pagini": [{"pagina": 1, "text": "cod_CAEN: 6820", "tabele": []}],
        "found": [
            {
                "date_generale": {
                    "cui": 9999999999,
                    "cod_CAEN": "6820",
                }
            }
        ]
    }
    with open(folder_brut / "05_raspuns_anaf.json", "w", encoding="utf-8") as f:
        json.dump(anaf_brut, f, indent=2)

    breeam_brut = {
        "fisier": "02_registru_breeam.json",
        "dosar": "dosar_engine",
        "tip_din_nume": "certificat_sustenabilitate",
        "nr_pagini": 1,
        "pagini": [{"pagina": 1, "text": "rating: Excellent", "tabele": []}],
        "rating": "Excellent",
        "stage": "Final",
    }
    with open(folder_brut / "02_registru_breeam.json", "w", encoding="utf-8") as f:
        json.dump(breeam_brut, f, indent=2)

    # Verificăm că la rădăcină NU există aceste fișiere
    assert not (dosar_dir / "05_raspuns_anaf.json").exists()
    assert not (dosar_dir / "02_registru_breeam.json").exists()

    stare = StareDosar(
        dosar_folder=str(dosar_dir),
        extras=DosarExtras(
            dosar_id="dosar_engine",
            cui=Camp(valoare="9999999999"),
            suma_eur=Camp(valoare=1000000),
            cota_banca=Camp(valoare=1.0),
            data_aprobare=Camp(valoare="2026-01-01"),
            tara=Camp(valoare="România"),
            adresa_cladire=Camp(valoare="București"),
            suprafata_m2=Camp(valoare=1000),
            stadiu_cladire=Camp(valoare="Finalizată"),
            nr_certificat_declarat=Camp(valoare="BREEAM-001"),
        )
    )

    # Motorul trebuie să găsească valorile din _brut
    val_caen, sursa_caen = obtine_valoare_camp(stare, "caen_imprumutat")
    assert val_caen == "6820"
    assert "_brut" in sursa_caen

    val_rating, sursa_rating = obtine_valoare_camp(stare, "certificare_rating")
    assert val_rating == "Excellent"
    assert "_brut" in sursa_rating


def test_engine_nu_citeste_din_radacina_daca_lipseste_din_brut(tmp_path):
    """Dacă fișierul este la rădăcină dar lipsește din _brut, motorul NU îl citește din rădăcină."""
    dosar_dir = tmp_path / "dosar_radacina_only"
    dosar_dir.mkdir()
    folder_brut = dosar_dir / "_brut"
    folder_brut.mkdir()

    # Punem fișierul DOAR la rădăcină
    with open(dosar_dir / "05_raspuns_anaf.json", "w", encoding="utf-8") as f:
        json.dump({"found": [{"date_generale": {"cod_CAEN": "6820"}}]}, f)

    stare = StareDosar(
        dosar_folder=str(dosar_dir),
        extras=DosarExtras(
            dosar_id="dosar_radacina_only",
            cui=Camp(valoare="9999999999"),
            suma_eur=Camp(valoare=1000000),
            cota_banca=Camp(valoare=1.0),
            data_aprobare=Camp(valoare="2026-01-01"),
            tara=Camp(valoare="România"),
            adresa_cladire=Camp(valoare="București"),
            suprafata_m2=Camp(valoare=1000),
            stadiu_cladire=Camp(valoare="Finalizată"),
            nr_certificat_declarat=Camp(valoare="BREEAM-001"),
        )
    )

    val_caen, sursa_caen = obtine_valoare_camp(stare, "caen_imprumutat")
    # Fiind absent din _brut, nu trebuie citit din rădăcină
    assert val_caen is None

