"""Teste pentru raportul de la pasul 2 (ui/raport.py): fiecare afirmație vine dintr-un rezultat al agentului."""

from __future__ import annotations

import pytest

from ui.raport import MESAJ_INCONSISTENTA, ca_html, construieste_raport, eticheta_pagina, recomandare, reguli_cunoscute


def _regula(regula_id: str, rezultat: str, dovada: str, sursa: str) -> dict:
    return {"regula_id": regula_id, "rezultat": rezultat, "dovada": dovada, "sursa_framework": sursa}


GENERALE_OK = [
    _regula("G-01", "OK", "Tara: Romania (Anexa B)", "Anexa B, p. 26"),
    _regula("G-02", "OK", "CAEN imprumutat 6820 - imobiliare, nu e sector exclus", "Anexa A, p. 25"),
    _regula("G-04", "OK", "Aprobat 2026-03-15, in fereastra de 24 luni", "p. 6"),
]

ELIGIBIL = {
    "dosar_id": "dosar_eligibil",
    "verdict": "ELIGIBIL",
    "cale_eligibilitate": "GB-01 (certificare BREEAM Excellent, Final)",
    "reguli": GENERALE_OK + [
        _regula("GB-01", "OK", "Registru BREEAM: Excellent, Final", "Framework p.7"),
        _regula("GB-X1", "OK", "Niciun chirias cu CAEN din lista de semnal", "Framework p.7, nota 6"),
    ],
    "impact_tco2_an": 606.0,
    "impact_detalii": {
        "formula": "(baseline - energie_finala) x suprafata x cota_banca x factor_emisie",
        "sursa": "Allocation & Impact Report 2025, p. 22",
        "pasi": ["1. Diferenta consum: 300 - 95 = 205 kWh/m2/an"],
        "atentie": "Factorul de emisie e valoare EXEMPLU.",
    },
    "actiuni": [],
}

NEELIGIBIL = {
    "dosar_id": "dosar_neeligibil",
    "verdict": "NEELIGIBIL",
    "cale_eligibilitate": None,
    "reguli": [
        _regula("G-01", "NU", "Tara: Brazilia, nu e in Anexa B", "Anexa B, p. 26"),
        _regula("G-02", "OK", "CAEN 6820, nu e sector exclus", "Anexa A, p. 25"),
        _regula("GB-01", "NU", "BREEAM 'Good' < pragul 'Excellent'", "Framework p.7"),
    ],
    "impact_tco2_an": None,
    "impact_detalii": {},
    "actiuni": [],
}

EXCEPTIE = {
    "dosar_id": "dosar_exceptie",
    "verdict": "EXCEPTIE_ESCALADARE_COMITET",
    "cale_eligibilitate": "GB-01 ar fi indeplinita, dar exista un posibil motiv de excludere",
    "reguli": GENERALE_OK + [
        _regula("GB-01", "OK", "Registru BREEAM: Excellent, Final", "Framework p.7"),
        _regula("GB-X1", "SEMNAL", "Chirias 'Carpați Petrol Upstream SA', CAEN 0610, 7.000 m2 = 35% din cladire",
                "Framework p.7, nota 6"),
    ],
    "impact_tco2_an": None,
    "impact_detalii": {},
    "actiuni": ["Escaladare la Sustainability Bond Committee cu dovezile de mai sus"],
}
LIPSA = [{"id": "D-02", "nume": "Decizia de aprobare a creditului", "obligatoriu": True},
         {"id": "GB-D4", "nume": "Extras de carte funciara", "obligatoriu": True}]


def _sectiune(raport: dict, cheie: str) -> dict:
    return next(s for s in raport["sectiuni"] if s["cheie"] == cheie)


def _ids(sectiune: dict) -> list[str]:
    return [e.get("id") or e.get("text") for g in sectiune["grupuri"] for e in g["elemente"]]


def test_eligibil():
    r = construieste_raport(ELIGIBIL, "green_buildings")
    assert r["concluzie"][0] == ("Dosarul îndeplinește criteriile categoriei Green Buildings pe calea "
                                 "GB-01 „Certificare internationala” (p. 7): certificare BREEAM Excellent, Final.")
    assert "Nu s-au găsit excluderi." in r["concluzie"]
    assert r["concluzie"][-1] == "Impact estimat: 606,0 tCO₂/an."
    # secțiunile goale nu apar
    assert [s["cheie"] for s in r["sectiuni"]] == ["indeplinite"]
    grupuri = _sectiune(r, "indeplinite")["grupuri"]
    assert [g["titlu"] for g in grupuri] == ["Condiții generale", "Criteriile categoriei", "Excluderi"]
    gb01 = grupuri[1]["elemente"][0]
    assert (gb01["id"], gb01["nume"], gb01["pagina"]) == ("GB-01", "Certificare internationala", "p. 7")
    assert gb01["dovada"] == "Registru BREEAM: Excellent, Final"
    assert r["impact"]["tco2_an"] == 606.0 and r["impact"]["proxy"] is True
    assert r["impact"]["sursa"] == "Allocation & Impact Report 2025, p. 22"
    assert r["referinte"] == ["Anexa B, p. 26", "Anexa A, p. 25", "p. 6", "p. 7", "p. 7, nota 6",
                              "Allocation & Impact Report 2025, p. 22"]


def test_neeligibil():
    r = construieste_raport(NEELIGIBIL, "green_buildings")
    # cauza citată e condiția obligatorie, cu dovada și pagina din rezultatul regulii
    assert r["concluzie"] == [
        "Dosarul nu poate fi inclus: G-01 „Tara eligibila pentru utilizare verde” nu e îndeplinită "
        "(Tara: Brazilia, nu e in Anexa B), Anexa B, p. 26."
    ]
    assert [s["cheie"] for s in r["sectiuni"]] == ["indeplinite", "neindeplinite"]
    assert _ids(_sectiune(r, "neindeplinite")) == ["G-01", "GB-01"]
    assert r["impact"] is None


def test_neeligibil_doar_pe_criteriile_categoriei():
    verdict = {**NEELIGIBIL, "reguli": GENERALE_OK + [_regula("GB-01", "NU", "BREEAM 'Good'", "Framework p.7")]}
    r = construieste_raport(verdict, "green_buildings")
    assert r["concluzie"][0].startswith("Dosarul nu poate fi inclus: GB-01 „Certificare internationala” nu e îndeplinită")


def test_exceptie_cu_lipsuri():
    r = construieste_raport(EXCEPTIE, "green_buildings", LIPSA)
    assert r["concluzie"] == [
        "Dosarul nu poate fi decis automat: GB-X1 „Cladiri folosite pentru extractia/fabricarea combustibililor "
        "fosili” (p. 7, nota 6) a ridicat un semnal care cere evaluarea comitetului.",
        "În plus, lipsesc 2 documente obligatorii.",
        "Criteriile categoriei Green Buildings sunt îndeplinite pe calea GB-01 (p. 7).",
    ]
    assert [s["cheie"] for s in r["sectiuni"]] == ["indeplinite", "de_verificat"]
    de_verificat = _sectiune(r, "de_verificat")
    assert [g["cheie"] for g in de_verificat["grupuri"]] == ["excluderi", "actiuni", "documente_lipsa"]
    semnal = de_verificat["grupuri"][0]["elemente"][0]
    assert semnal["eticheta_rezultat"] == "Semnal" and "35% din cladire" in semnal["dovada"]
    assert de_verificat["grupuri"][1]["elemente"][0]["text"].startswith("Escaladare")
    documente = de_verificat["grupuri"][2]
    assert documente["titlu"] == "Documente lipsă (2)"
    assert [d["id"] for d in documente["elemente"]] == ["D-02", "GB-D4"]
    assert all(d["actiune"] == "de solicitat clientului" for d in documente["elemente"])
    assert "Nu s-au găsit excluderi." not in r["concluzie"]


def test_monitorizare_cu_conditionat():
    verdict = {**ELIGIBIL, "verdict": "ELIGIBIL_CU_MONITORIZARE", "impact_tco2_an": None,
               "cale_eligibilitate": "GB-01 (BREEAM Excellent, stadiu Interim)",
               "reguli": GENERALE_OK + [_regula("GB-01", "OK_CONDITIONAT", "certificare interim acceptata", "Framework p.7")]}
    r = construieste_raport(verdict, "green_buildings")
    assert r["concluzie"][0] == "Dosarul poate fi inclus în categoria Green Buildings, cu monitorizare: GB-01 „Certificare internationala” (p. 7)."
    assert _ids(_sectiune(r, "de_verificat")) == ["GB-01"]


def test_nicio_afirmatie_fara_regula():
    # fiecare element de regulă din raport corespunde unei reguli din verdict, cu dovada ei neschimbată
    r = construieste_raport(EXCEPTIE, "green_buildings", LIPSA)
    din_verdict = {x["regula_id"]: x["dovada"] for x in EXCEPTIE["reguli"]}
    for s in r["sectiuni"]:
        for g in s["grupuri"]:
            for e in g["elemente"]:
                if e["tip"] == "regula":
                    assert din_verdict[e["id"]] == e["dovada"]
    assert sum(1 for s in r["sectiuni"] for g in s["grupuri"] for e in g["elemente"] if e["tip"] == "regula") == len(din_verdict)


def test_verdict_gol():
    r = construieste_raport({"dosar_id": "x", "verdict": "ELIGIBIL", "reguli": [], "actiuni": []})
    assert r["sectiuni"] == [] and r["referinte"] == [] and r["impact"] is None


def test_grupuri_din_yaml():
    cunoscute = reguli_cunoscute()
    assert cunoscute["G-01"]["grup"] == "conditii_generale"
    assert cunoscute["GB-01"]["grup"] == "categorie"
    assert cunoscute["GB-X1"]["grup"] == "excluderi"
    assert cunoscute["PL-01"]["grup"] == "plauzibilitate"


def test_eticheta_pagina():
    assert eticheta_pagina("Framework p.7, nota 6") == "p. 7, nota 6"
    assert eticheta_pagina("Framework p.7") == "p. 7"
    assert eticheta_pagina("Anexa B, p. 26") == "Anexa B, p. 26"
    assert eticheta_pagina("p. 6") == "p. 6"


def test_html_are_aceeasi_structura():
    r = construieste_raport(EXCEPTIE, "green_buildings", LIPSA)
    pagina = ca_html(r, "Verde Business Park", "2026-10-29T02:10:00")
    for text in ["Concluzie", "✓ Ce îndeplinește", "! De verificat", "Documente lipsă (2)", "Referințe Framework"]:
        assert text in pagina
    assert "Ce nu îndeplinește" not in pagina and "<h2>Impact</h2>" not in pagina
    assert "<script" not in pagina.replace("onclick", "")


# ------------------------------------------------------------------ recomandarea (doar din câmpul verdict)

def test_concluzie_exceptie_fara_semnal():
    verdict = {**ELIGIBIL, "verdict": "EXCEPTIE_ESCALADARE_COMITET", "impact_tco2_an": None,
               "reguli": [*GENERALE_OK, _regula("G-03", "NEEVALUABIL", "lipsește decizia de aprobare", "p. 19"),
                          _regula("GB-01", "OK", "Registru BREEAM: Excellent, Final", "Framework p.7")]}
    r = construieste_raport(verdict, "green_buildings", LIPSA)
    assert r["concluzie"][0] == ("Verificarea nu e completă: 1 criteriu nu a putut fi verificat (G-03); "
                                 "lipsesc 2 documente obligatorii.")


@pytest.mark.parametrize("verdict,cheie,eticheta", [
    ("ELIGIBIL", "aprobat", "Aprobare"),
    ("ELIGIBIL_CU_MONITORIZARE", "aprobat_conditionat", "Aprobare condiționată"),
    ("EXCEPTIE_ESCALADARE_COMITET", "interventie", "Intervenție umană"),
    ("NEELIGIBIL", "respins", "Respingere"),
])
def test_recomandare_pentru_fiecare_verdict(verdict, cheie, eticheta):
    v = {**ELIGIBIL, "verdict": verdict, "actiuni": ["Motiv: Neevaluabil G-03 (x): lipsește D-02"]}
    if verdict == "ELIGIBIL":
        v["actiuni"] = []
    rec = recomandare(v, construieste_raport(v, "green_buildings"))
    assert (rec["cheie"], rec["eticheta"]) == (cheie, eticheta)
    assert rec["inconsistenta"] is None
    if verdict == "ELIGIBIL":
        assert rec["motive"] == ["Toate cele 5 criterii aplicabile sunt îndeplinite."]
    else:
        assert rec["motive"] == ["Neevaluabil G-03 (x): lipsește D-02"]


def test_recomandare_de_ce_maxim_trei_motive():
    v = {**EXCEPTIE, "actiuni": [f"Motiv: motivul {i}" for i in range(5)] + ["Escaladare la comitet"]}
    rec = recomandare(v, construieste_raport(v, "green_buildings"))
    assert rec["motive"] == ["motivul 0", "motivul 1", "motivul 2"] and len(rec["toate_motivele"]) == 5


def test_inconsistenta_eligibil_cu_de_verificat():
    """ELIGIBIL, dar raportul are o regulă neevaluabilă -> nu „Aprobare”, ci avertisment."""
    v = {**ELIGIBIL, "reguli": [*ELIGIBIL["reguli"], _regula("G-03", "NEEVALUABIL", "lipsește D-02", "p. 19")]}
    rec = recomandare(v, construieste_raport(v, "green_buildings"))
    assert rec["cheie"] == "interventie" and rec["inconsistenta"] == MESAJ_INCONSISTENTA
    assert any(m.startswith("G-03") for m in rec["motive"])
    # un semnal de plauzibilitate informativ nu face inconsistență
    v = {**ELIGIBIL, "reguli": [*ELIGIBIL["reguli"], _regula("PL-03", "SEMNAL", "afirmație nesusținută", "")]}
    assert recomandare(v, construieste_raport(v, "green_buildings"))["cheie"] == "aprobat"


def test_motivele_cu_rand_propriu_nu_se_repeta():
    v = {**EXCEPTIE, "actiuni": ["Motiv: Semnal GB-X1 (Cladiri...): chirias", "Motiv: Câmp obligatoriu negăsit: x",
                                  "Motiv: Document obligatoriu lipsă: D-02", "Escaladare la comitet"]}
    de_verificat = _sectiune(construieste_raport(v, "green_buildings", LIPSA), "de_verificat")
    texte = {g["cheie"]: [e.get("text") for e in g["elemente"]] for g in de_verificat["grupuri"]}
    assert texte["actiuni"] == ["Escaladare la comitet"]
    assert texte["alte_motive"] == ["Câmp obligatoriu negăsit: x"]
