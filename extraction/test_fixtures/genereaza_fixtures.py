"""Generează dosare sintetice (PDF) pentru testarea extractorului, fiecare cu expected_campuri.json.

Fiecare pagină e marcată „DOCUMENT SINTETIC”. Firmele, CUI-urile și VIN-urile sunt fictive.
Rulare: python -m extraction.test_fixtures.genereaza_fixtures
"""

import io
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
            "afirmatii_client": ["Flota noastră este 100% cu emisii zero."],
            # fără decizie de aprobare (D-02): data declarației de utilizare NU e data aprobării
            "data_aprobare": None,
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


# ---------------------------------------------------------------------------- imagini (documente scanate)
def _imagine_document(linii: list[str], latime: int = 1240, inaltime: int = 1754) -> bytes:
    """Imagine A4 (aprox. 150 dpi) cu textul dat: simulează un document scanat, fără strat de text."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (latime, inaltime), "white")
    desen = ImageDraw.Draw(img)
    cale_font = next((c for c in _FONTURI if c.exists()), None)
    font_titlu = ImageFont.truetype(str(cale_font), 34) if cale_font else ImageFont.load_default()
    font = ImageFont.truetype(str(cale_font), 28) if cale_font else ImageFont.load_default()
    desen.text((80, 40), MARCAJ, fill="red", font=font)
    y = 120
    for i, linie in enumerate(linii):
        desen.text((80, y), _text(linie), fill="black", font=font_titlu if i == 0 else font)
        y += 60
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_scanat(cale: Path, linii: list[str]) -> None:
    """PDF cu o singură pagină care conține doar imaginea (fără text extractibil)."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(cale), pagesize=A4)
    c.drawImage(ImageReader(io.BytesIO(_imagine_document(linii))), 0, 0, width=A4[0], height=A4[1])
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------- fx_hidro_2022
def fx_hidro_2022() -> None:
    folder = FOLDER / "fx_hidro_2022"
    folder.mkdir(parents=True, exist_ok=True)

    _cerere(
        folder / "01_cerere_finantare.pdf",
        [
            ["Solicitant", "Exemplu Hidro Energie SRL"],
            ["CUI", "9900000111"],
            ["Țara", "România"],
            ["Suma solicitată de la bancă", "6.000.000 EUR"],
            ["Structura finanțării", "Banca 75% (6.000.000 EUR), aport propriu 25%"],
        ],
        "Refinanțarea centralei hidroelectrice Exemplu-Râu (producție de energie electrică din sursă hidro), "
        "pusă în funcțiune în 2022, cu lac de acumulare propriu.",
        [],
    )
    _pdf(folder / "02_studiu_fezabilitate.pdf", [
        _p("STUDIU DE FEZABILITATE – CHE Exemplu-Râu", "Title"),
        _p("Soluția tehnică: centrală hidroelectrică cu acumulare, două hidroagregate Francis."),
        _tabel([
            ["Parametru", "Valoare"],
            ["Putere instalată", "4.800 kW"],
            ["Suprafața lacului de acumulare", "60 ha"],
            ["Producția medie anuală estimată", "18,5 GWh"],
        ], [8 * cm, 6 * cm]),
        Spacer(1, 0.3 * cm),
        _p("Centrala nu funcționează pe firul apei; dispune de un lac de acumulare de 60 ha."),
    ])
    _pdf(folder / "03_autorizatie_anre.pdf", [
        _p("LICENȚĂ PENTRU EXPLOATAREA COMERCIALĂ A CAPACITĂȚILOR DE PRODUCERE A ENERGIEI ELECTRICE", "Title"),
        _p("Emisă de ANRE pentru Exemplu Hidro Energie SRL, CUI 9900000111, pentru CHE Exemplu-Râu."),
        _tabel([
            ["Capacitate autorizată", "4,8 MW"],
            ["Data punerii în funcțiune", "15.06.2022"],
            ["Anul punerii în funcțiune", "2022"],
        ], [8 * cm, 6 * cm]),
    ])
    _pdf(folder / "04_studiu_impact_mediu.pdf", [
        _p("RAPORT PRIVIND EVALUAREA IMPACTULUI ASUPRA MEDIULUI (EIA)", "Title"),
        _p("Proiect: CHE Exemplu-Râu. Evaluarea a analizat impactul asupra faunei acvatice, debitului de servitute "
           "și calității apei."),
        _p("Concluzie: în urma evaluării nu au fost identificate riscuri semnificative asupra mediului."),
    ])
    _scrie_expected(folder, {
        "categorie": "renewable_energy",
        "subcategorie": "hidro",
        "campuri": {
            "cui": "9900000111",
            "suma_eur": 6000000,
            "cota_banca": 0.75,
            "indicatori.tehnologie": "hidro",
            "indicatori.capacitate_mw": 4.8,
            "indicatori.productie_anuala_mwh": 18500,
            "indicatori.an_punere_functiune": "2022",
            "indicatori.eia_risc_semnificativ": False,
            "indicatori.fir_de_apa_fara_rezervor": False,
        },
        "conversii_contin": ["kW", "GWh"],
        "liste": {},
    })


# ---------------------------------------------------------------------------- fx_renovare
def fx_renovare() -> None:
    folder = FOLDER / "fx_renovare"
    folder.mkdir(parents=True, exist_ok=True)

    _cerere(
        folder / "01_cerere_finantare.pdf",
        [
            ["Solicitant", "Exemplu Imobiliare SRL"],
            ["CUI", "9900000122"],
            ["Țara", "România"],
            ["Adresa clădirii", "Timișoara, Str. Fictivă nr. 3"],
            ["Suma solicitată de la bancă", "5.000.000 EUR"],
            ["Structura finanțării", "Banca 100% (5.000.000 EUR)"],
        ],
        "Renovarea energetică majoră a unei clădiri de birouri existente: anvelopare termică, înlocuirea "
        "tâmplăriei și instalarea de pompe de căldură.",
        ["După renovare, clădirea va consuma cu 50% mai puțină energie."],
    )
    for nume, titlu, situatie, clasa, ped in [
        ("02_epc_inainte.pdf", "CERTIFICAT DE PERFORMANȚĂ ENERGETICĂ – situația existentă",
         "Certificat emis pentru clădirea în starea existentă, înainte de lucrările de renovare.", "D", "245"),
        ("03_epc_dupa.pdf", "CERTIFICAT DE PERFORMANȚĂ ENERGETICĂ – după renovare",
         "Certificat pentru clădirea după renovare, estimat conform proiectului tehnic de renovare.", "B", "120"),
    ]:
        _pdf(folder / nume, [
            _p(titlu, "Title"),
            _p(situatie),
            _tabel([
                ["Clasa energetică", clasa],
                ["Consum anual specific de energie primară", f"{ped} kWh/m²·an"],
                ["Aria utilă (Au)", "8.000 m²"],
            ], [8 * cm, 6 * cm]),
        ])
    _pdf(folder / "04_deviz_lucrari.pdf", [
        _p("DEVIZ GENERAL AL LUCRĂRILOR DE RENOVARE", "Title"),
        _tabel([
            ["Capitol", "Valoare"],
            ["Anvelopare termică și tâmplărie", "2.750.000 EUR"],
            ["Pompe de căldură și instalații", "1.500.000 EUR"],
            ["Alte lucrări (amenajări interioare)", "750.000 EUR"],
            ["Total", "5.000.000 EUR"],
        ], [9 * cm, 5 * cm]),
        Spacer(1, 0.3 * cm),
        _p("Ponderea lucrărilor de renovare energetică în valoarea totală a devizului: 85%."),
    ])
    _scrie_expected(folder, {
        "categorie": "green_buildings",
        "subcategorie": "renovare",
        "campuri": {
            "cui": "9900000122",
            "suma_eur": 5000000,
            "indicatori.ped_inainte_kwh_m2": 245,
            "indicatori.ped_dupa_kwh_m2": 120,
            "indicatori.pondere_suma_pentru_renovare": 0.85,
        },
        "liste": {},
    })


# ---------------------------------------------------------------------------- fx_aluminiu
def fx_aluminiu() -> None:
    folder = FOLDER / "fx_aluminiu"
    folder.mkdir(parents=True, exist_ok=True)

    _cerere(
        folder / "01_cerere_finantare.pdf",
        [
            ["Solicitant", "Exemplu Profile Metalice SRL"],
            ["CUI", "9900000133"],
            ["Țara", "România"],
            ["Suma solicitată de la bancă", "3.000.000 EUR"],
            ["Structura finanțării", "Banca 60% (3.000.000 EUR), aport propriu 40%"],
        ],
        "Linie nouă de producție pentru profile din aluminiu pentru construcții, fabricate cu un conținut "
        "ridicat de aluminiu reciclat.",
        [],
    )
    _pdf(folder / "02_declaratie_furnizor.pdf", [
        _p("DECLARAȚIA FURNIZORULUI PRIVIND MATERIALUL LIVRAT", "Title"),
        _p("Furnizor: Exemplu Aluminium Supply SRL. Beneficiar: Exemplu Profile Metalice SRL, CUI 9900000133."),
        _tabel([
            ["Indicator", "Valoare"],
            ["Conținut de aluminiu reciclat", "75%"],
            ["Intensitatea de carbon a aluminiului primar utilizat", "2,1 tCO2e/t"],
        ], [9 * cm, 5 * cm]),
        Spacer(1, 0.3 * cm),
        _p("Valorile sunt calculate pentru loturile livrate în anul 2025."),
    ])
    _scrie_expected(folder, {
        "categorie": "circular_economy",
        "subcategorie": "produse_aluminiu",
        "campuri": {
            "cui": "9900000133",
            "suma_eur": 3000000,
            "cota_banca": 0.6,
            "indicatori.tip": "produse_aluminiu",
            "indicatori.pondere_aluminiu_reciclat": 0.75,
            "indicatori.intensitate_carbon_aluminiu_primar_tco2e_t": 2.1,
        },
        "liste": {},
    })


# ---------------------------------------------------------------------------- fx_scanat
def fx_scanat() -> None:
    folder = FOLDER / "fx_scanat"
    folder.mkdir(parents=True, exist_ok=True)

    _cerere(
        folder / "01_cerere_finantare.pdf",
        [
            ["Solicitant", "Exemplu Logistică SRL"],
            ["CUI", "9900000144"],
            ["Țara", "România"],
            ["Suma solicitată de la bancă", "300.000 EUR"],
            ["Structura finanțării", "Banca 100% (300.000 EUR)"],
        ],
        "Achiziția a 8 autoutilitare ușoare (categoria N1): 5 electrice și 3 hibride plug-in, pentru livrări urbane.",
        [],
    )
    _pdf(folder / "02_lista_vehicule.pdf", [
        _p("ANEXA FLOTĂ – Lista vehiculelor finanțate", "Title"),
        _tabel([
            ["Marca", "Model", "Combustibil", "Nr. buc.", "CO2 WLTP (g/km)", "Km/an"],
            ["Exemplu", "City-EV", "electric", "5", "0", "15.000"],
            ["Exemplu", "Cargo-PHEV", "hibrid plug-in", "3", "52", "15.000"],
        ]),
    ])
    # CoC scanat: pagină PDF fără text, doar imagine (lista spune 52 g/km, CoC 48 g/km)
    _pdf_scanat(folder / "03_coc_cargo_phev_scanat.pdf", [
        "CERTIFICAT DE CONFORMITATE CE / EC CERTIFICATE OF CONFORMITY",
        "0.1 Marca (Make): Exemplu",
        "0.2 Tip / Model: Cargo-PHEV",
        "0.4 Categoria vehiculului: N1",
        "47. Emisii CO2 WLTP, combinat: 48 g/km",
        "49. Consum de energie electrică WLTP: 180 Wh/km",
    ])
    # CoC fotografiat: fișier imagine direct în dosar
    (folder / "04_coc_city_ev_foto.png").write_bytes(_imagine_document([
        "CERTIFICAT DE CONFORMITATE CE / EC CERTIFICATE OF CONFORMITY",
        "0.1 Marca (Make): Exemplu",
        "0.2 Tip / Model: City-EV",
        "47. Emisii CO2 WLTP, combinat: 0 g/km",
        "49. Consum de energie electrică WLTP: 150 Wh/km",
    ]))
    _scrie_expected(folder, {
        "categorie": "clean_transportation",
        "subcategorie": "autoturism_sau_utilitara",
        "campuri": {"cui": "9900000144", "suma_eur": 300000},
        "liste": {
            "indicatori.vehicule": {
                "cheie": ["marca", "model"],
                "randuri": [
                    {"marca": "Exemplu", "model": "City-EV", "bucati": 5, "emisii_wltp_gco2_km": 0, "consum_kwh_km": 0.15},
                    {"marca": "Exemplu", "model": "Cargo-PHEV", "bucati": 3, "emisii_wltp_gco2_km": 48, "consum_kwh_km": 0.18},
                ],
            }
        },
        "pagini_ocr_minim": 2,
        "_note": "Emisiile Cargo-PHEV (48) și consumurile vin DOAR din CoC-urile scanate (OCR).",
    })


# ---------------------------------------------------------------------------- fx_incomplet
def fx_incomplet() -> None:
    folder = FOLDER / "fx_incomplet"
    folder.mkdir(parents=True, exist_ok=True)

    _cerere(
        folder / "01_cerere_finantare.pdf",
        [
            ["Solicitant", "Exemplu Distribuție SRL"],
            ["CUI", "9900000155"],
            ["Țara", "România"],
            ["Suma solicitată de la bancă", "200.000 EUR"],
            ["Structura finanțării", "Banca 100% (200.000 EUR)"],
        ],
        "Achiziția a 6 autoutilitare ușoare (categoria N1) electrice pentru distribuție urbană.",
        [],
    )
    # Lista NU conține emisii, iar dosarul NU conține CoC
    _pdf(folder / "02_lista_vehicule.pdf", [
        _p("ANEXA FLOTĂ – Lista vehiculelor finanțate", "Title"),
        _tabel([
            ["Marca", "Model", "Combustibil", "Nr. buc.", "Km/an"],
            ["Exemplu", "Urban-EV", "electric", "6", "20.000"],
        ]),
    ])
    _scrie_expected(folder, {
        "categorie": "clean_transportation",
        "subcategorie": "autoturism_sau_utilitara",
        "campuri": {
            "cui": "9900000155",
            "suma_eur": 200000,
            "indicatori.transporta_combustibili_fosili": None,
        },
        "liste": {
            "indicatori.vehicule": {
                "cheie": ["marca", "model"],
                "randuri": [
                    {"marca": "Exemplu", "model": "Urban-EV", "bucati": 6, "emisii_wltp_gco2_km": None,
                     "consum_kwh_km": None, "distanta_anuala_km": 20000},
                ],
            }
        },
        "documente_lipsa_contine": ["CT-D2", "D-02"],
        "_note": "Fără CoC: CT-D2 în documente_lipsa, emisiile rămân null (nu se inventează).",
    })


# ---------------------------------------------------------------------------- fx_ambiguu
def fx_ambiguu() -> None:
    folder = FOLDER / "fx_ambiguu"
    folder.mkdir(parents=True, exist_ok=True)

    _cerere(
        folder / "01_cerere_finantare.pdf",
        [
            ["Solicitant", "Exemplu Industrie SRL"],
            ["CUI", "9900000166"],
            ["Țara", "România"],
            ["Suma solicitată de la bancă", "1.200.000 EUR"],
            ["Structura finanțării", "Banca 100% (1.200.000 EUR)"],
        ],
        "Modernizarea iluminatului și panouri fotovoltaice pe hala de producție.",
        [],
    )
    _scrie_expected(folder, {
        "categorie_ambigua": True,
        "categorie_candidati": ["energy_efficiency", "renewable_energy"],
        "campuri": {"cui": "9900000166", "suma_eur": 1200000},
        "liste": {},
    })


FIXTURES = {
    "fx_transport_flota": fx_transport_flota,
    "fx_data_center": fx_data_center,
    "fx_hidro_2022": fx_hidro_2022,
    "fx_renovare": fx_renovare,
    "fx_aluminiu": fx_aluminiu,
    "fx_scanat": fx_scanat,
    "fx_incomplet": fx_incomplet,
    "fx_ambiguu": fx_ambiguu,
}


def main() -> None:
    for nume, functie in FIXTURES.items():
        functie()
        print(f"Generat: {nume}")


if __name__ == "__main__":
    main()
