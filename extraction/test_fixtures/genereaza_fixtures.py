"""Generează dosare sintetice (PDF) pentru testarea extractorului, fiecare cu expected_campuri.json.

Fiecare pagină e marcată „DOCUMENT SINTETIC”. Firmele, CUI-urile și VIN-urile sunt fictive.
Rulare: python -m extraction.test_fixtures.genereaza_fixtures
"""

import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FOLDER = Path(__file__).resolve().parent
MARCAJ = "DOCUMENT SINTETIC - generat pentru teste, date fictive"

# Font cu diacritice românești (ș, ț); fără el, textul se transliterează
_FONTURI = [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
FONT = "Helvetica"
for _cale in _FONTURI:
    if _cale.exists():
        pdfmetrics.registerFont(TTFont("FontFixture", str(_cale)))
        FONT = "FontFixture"
        break


def _text(s: str) -> str:
    if FONT != "Helvetica":
        return s
    return s.translate(str.maketrans("ăâîșțĂÂÎȘȚ", "aaistAAIST"))


def _stiluri() -> dict[str, Any]:
    st = getSampleStyleSheet()
    for nume in ("Normal", "Title", "Heading2"):
        st[nume].fontName = FONT
    return st


def _marcaj(canvas: Any, _doc: Any) -> None:
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.red)
    canvas.drawString(1.5 * cm, A4[1] - 1 * cm, MARCAJ)
    canvas.restoreState()


def _tabel(randuri: list[list[str]], latimi: list[float] | None = None) -> Table:
    stil = _stiluri()["Normal"].clone("celula", fontSize=8, leading=10)
    t = Table([[Paragraph(_text(c), stil) for c in r] for r in randuri], colWidths=latimi)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _pdf(cale: Path, elemente: list[Any]) -> None:
    doc = SimpleDocTemplate(str(cale), pagesize=A4, topMargin=2 * cm)
    doc.build(elemente, onFirstPage=_marcaj, onLaterPages=_marcaj)


def _p(text: str, stil: str = "Normal") -> Paragraph:
    return Paragraph(_text(text), _stiluri()[stil])


def _cerere(cale: Path, date: list[list[str]], descriere: str, afirmatii: list[str]) -> None:
    elemente = [
        _p("CERERE DE FINANȚARE – PERSOANE JURIDICE", "Title"),
        _tabel(date, [6 * cm, 10 * cm]),
        Spacer(1, 0.5 * cm),
        _p("Descrierea proiectului", "Heading2"),
        _p(descriere),
    ]
    if afirmatii:
        elemente.append(_p("Declarații ale solicitantului privind sustenabilitatea", "Heading2"))
        elemente.extend(_p(f"• {a}") for a in afirmatii)
    _pdf(cale, elemente)


def _scrie_expected(folder: Path, expected: dict[str, Any]) -> None:
    with open(folder / "expected_campuri.json", "w", encoding="utf-8") as f:
        json.dump(expected, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------- fx_transport_flota
def fx_transport_flota() -> None:
    folder = FOLDER / "fx_transport_flota"
    folder.mkdir(parents=True, exist_ok=True)

    _cerere(
        folder / "01_cerere_finantare.pdf",
        [
            ["Solicitant", "Exemplu Curierat Urban SRL"],
            ["CUI", "9900000088"],
            ["Țara", "România"],
            ["Adresa sediului social", "Cluj-Napoca, Str. Fictivă nr. 7"],
            ["Suma solicitată de la bancă", "450.000 EUR"],
            ["Structura finanțării", "Banca 100% (450.000 EUR)"],
            ["Durata", "5 ani"],
        ],
        "Achiziția unei flote de 15 autoutilitare ușoare (categoria N1) pentru livrarea urbană de colete: "
        "10 autoutilitare electrice și 5 autoutilitare hibride plug-in. Lista vehiculelor este în anexa flotă.",
        ["Flota noastră este 100% cu emisii zero."],
    )

    antet = ["Nr. crt.", "Marca", "Model", "Combustibil", "Nr. buc.", "CO2 WLTP (g/km)", "Consum (kWh/100 km)", "Km/an"]
    latimi = [1.4 * cm, 2 * cm, 2.2 * cm, 2.6 * cm, 1.6 * cm, 2.4 * cm, 2.8 * cm, 1.8 * cm]
    _pdf(folder / "02_lista_vehicule.pdf", [
        _p("ANEXA FLOTĂ – Lista vehiculelor finanțate", "Title"),
        _p("Beneficiar: Exemplu Curierat Urban SRL, CUI 9900000088. Un rând pe lot de livrare."),
        Spacer(1, 0.3 * cm),
        _tabel([
            antet,
            ["1", "Exemplu", "EV-Van", "electric", "6", "0", "16,0", "17.746"],
            ["2", "Exemplu", "PHEV-Van", "hibrid plug-in", "3", "48", "5,0", "17.746"],
        ], latimi),
        PageBreak(),
        # continuarea tabelului, fără antet repetat
        _tabel([
            ["3", "Exemplu", "EV-Van", "electric", "4", "0", "16,0", "17.746"],
            ["4", "Exemplu", "PHEV-Van", "hibrid plug-in", "2", "48", "5,0", "17.746"],
        ], latimi),
        Spacer(1, 0.3 * cm),
        _p("Total vehicule finanțate: 15."),
    ])

    for nume, model, vin, co2, consum in [
        ("03_coc_ev_van.pdf", "EV-Van", "WEXFICTIV00000001", "0", "160 Wh/km"),
        ("04_coc_phev_van.pdf", "PHEV-Van", "WEXFICTIV00000002", "45", "50 Wh/km"),
    ]:
        _pdf(folder / nume, [
            _p("CERTIFICAT DE CONFORMITATE CE / EC CERTIFICATE OF CONFORMITY", "Title"),
            _p("pentru vehicule complete din categoria N1 (omologare de tip UE)"),
            Spacer(1, 0.3 * cm),
            _tabel([
                ["0.1 Marca (Make)", "Exemplu"],
                ["0.2 Tip / Model", model],
                ["0.4 Categoria vehiculului", "N1"],
                ["0.10 Număr de identificare vehicul (VIN)", vin],
                ["47. Emisii CO2 WLTP, combinat", f"{co2} g/km"],
                ["49. Consum de energie electrică WLTP", consum],
            ], [8 * cm, 8 * cm]),
        ])

    _pdf(folder / "05_declaratie_utilizare.pdf", [
        _p("DECLARAȚIE DE UTILIZARE A VEHICULELOR", "Title"),
        _p("Subsemnatul Ion Exemplu, administrator al Exemplu Curierat Urban SRL, CUI 9900000088, "
           "declar pe propria răspundere că vehiculele finanțate prin creditul solicitat sunt utilizate "
           "exclusiv pentru livrarea de colete și nu transportă combustibili fosili."),
        Spacer(1, 0.5 * cm),
        _p("Data: 15.10.2025"),
    ])

    _scrie_expected(folder, {
        "categorie": "clean_transportation",
        "subcategorie": "autoturism_sau_utilitara",
        "campuri": {
            "cui": "9900000088",
            "tara": "România",
            "suma_eur": 450000,
            "cota_banca": 1.0,
            "indicatori.tip": "autoturism_sau_utilitara",
            "indicatori.transporta_combustibili_fosili": False,
        },
        "liste": {
            "indicatori.vehicule": {
                "cheie": ["marca", "model"],
                "randuri": [
                    {"marca": "Exemplu", "model": "EV-Van", "bucati": 10, "emisii_wltp_gco2_km": 0,
                     "consum_kwh_km": 0.16, "distanta_anuala_km": 17746},
                    {"marca": "Exemplu", "model": "PHEV-Van", "bucati": 5, "emisii_wltp_gco2_km": 45,
                     "consum_kwh_km": 0.05, "distanta_anuala_km": 17746},
                ],
            }
        },
        "_note": "PHEV-Van: lista spune 48 g/km, CoC 45 g/km -> câștigă CoC, conflict în raport.",
    })


# ---------------------------------------------------------------------------- fx_data_center
def fx_data_center() -> None:
    folder = FOLDER / "fx_data_center"
    folder.mkdir(parents=True, exist_ok=True)

    _cerere(
        folder / "01_cerere_finantare.pdf",
        [
            ["Solicitant", "Exemplu Data Services SRL"],
            ["CUI", "9900000099"],
            ["Țara", "România"],
            ["Adresa sediului social", "Ilfov, Șos. Fictivă nr. 12"],
            ["Valoarea totală a proiectului", "10.000.000 EUR"],
            ["Suma solicitată de la bancă", "8.000.000 EUR"],
            ["Structura finanțării", "Banca 80% (8.000.000 EUR), aport propriu 20%"],
        ],
        "Modernizarea centrului de date propriu din Ilfov: înlocuirea sistemelor de răcire și a UPS-urilor "
        "cu echipamente de înaltă eficiență energetică, cu scopul de a reduce PUE-ul anual al centrului de date.",
        [],
    )

    _pdf(folder / "02_raport_pue.pdf", [
        _p("DATA CENTRE ENERGY EFFICIENCY REPORT 2025", "Title"),
        _p("Facility: Exemplu Data Centre Ilfov. Operator: Exemplu Data Services SRL. "
           "Reporting period: January 2025 – December 2025."),
        Spacer(1, 0.3 * cm),
        _tabel([
            ["Indicator", "Value"],
            ["Total facility energy", "12.420 MWh"],
            ["IT equipment energy", "9.000 MWh"],
            ["Annualised PUE", "1,38"],
        ], [8 * cm, 6 * cm]),
        Spacer(1, 0.3 * cm),
        _p("Result: the annualised PUE: 1,38 was measured over the full reporting period according to "
           "EN 50600-4-2, using sub-metering at the UPS output."),
    ])

    _scrie_expected(folder, {
        "categorie": "energy_efficiency",
        "subcategorie": "data_center",
        "campuri": {
            "cui": "9900000099",
            "tara": "România",
            "suma_eur": 8000000,
            "cota_banca": 0.8,
            "indicatori.tip_proiect": "data_center",
            "indicatori.pue_anualizat": 1.38,
        },
        "liste": {},
    })


FIXTURES = {
    "fx_transport_flota": fx_transport_flota,
    "fx_data_center": fx_data_center,
}


def main() -> None:
    for nume, functie in FIXTURES.items():
        functie()
        print(f"Generat: {nume}")


if __name__ == "__main__":
    main()
