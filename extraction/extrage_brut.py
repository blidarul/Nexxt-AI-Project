"""Script pentru extragerea brută a tuturor PDF-urilor din dosare în format JSON."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from extraction.ocr import MIME_IMAGINI, aplica_ocr_pdf, pagina_ocr
from extraction.pdf_text import extrage_pagini_pdf


def determina_tip_document(nume_fisier: str) -> str:
    """Deduce tipul documentului pe baza prefixului din numele fișierului."""
    if nume_fisier.startswith("01_"):
        return "cerere_finantare"
    elif nume_fisier.startswith("03_"):
        return "certificat_energetic"
    elif nume_fisier.startswith("04_"):
        return "contract_inchiriere"
    return "necunoscut"


def proceseaza_pdf(cale_pdf: Path, nume_dosar: str, folder_brut: Path) -> dict[str, Any]:
    """Extrage conținutul brut al unui PDF și îl salvează în folderul _brut.

    Întoarce metadatele documentului pentru index.json.
    """
    tip_document = determina_tip_document(cale_pdf.name)
    cale_json_relativa = f"_brut/{cale_pdf.stem}.json"
    cale_json_iesire = folder_brut / f"{cale_pdf.stem}.json"

    try:
        if cale_pdf.suffix.lower() in MIME_IMAGINI:
            pagini = [pagina_ocr(1, cale_pdf.read_bytes(), MIME_IMAGINI[cale_pdf.suffix.lower()])]
            erori_ocr = []
        else:
            pagini = extrage_pagini_pdf(cale_pdf)
            erori_ocr = aplica_ocr_pdf(cale_pdf, pagini)
        nr_pagini = len(pagini)
        nr_tabele = sum(len(p.get("tabele", [])) for p in pagini)

        continut_brut = {
            "fisier": cale_pdf.name,
            "dosar": nume_dosar,
            "tip_document": tip_document,
            "nr_pagini": nr_pagini,
            "extras_la": datetime.now().isoformat(timespec="seconds"),
            "pagini": pagini,
        }
        if erori_ocr:
            continut_brut["erori_ocr"] = erori_ocr

        with open(cale_json_iesire, "w", encoding="utf-8") as f:
            json.dump(continut_brut, f, ensure_ascii=False, indent=2)

        return {
            "fisier": cale_pdf.name,
            "tip_document": tip_document,
            "json": cale_json_relativa,
            "pagini": nr_pagini,
            "tabele": nr_tabele,
            "pagini_ocr": sum(1 for p in pagini if p.get("ocr")),
            "eroare": "; ".join(erori_ocr) or None,
        }

    except Exception as e:
        return {
            "fisier": cale_pdf.name,
            "tip_document": tip_document,
            "json": None,
            "pagini": 0,
            "tabele": 0,
            "eroare": str(e),
        }


def proceseaza_dosar(cale_dosar: Path) -> dict[str, int]:
    """Procesează toate fișierele PDF dintr-un dosar și generează index.json."""
    nume_dosar = cale_dosar.name
    folder_brut = cale_dosar / "_brut"
    folder_brut.mkdir(parents=True, exist_ok=True)

    # PDF-uri și imagini (.jpg/.png, transcrise prin OCR)
    extensii = {".pdf"} | set(MIME_IMAGINI)
    fisiere_pdf = sorted([
        p for p in cale_dosar.iterdir()
        if p.is_file() and p.suffix.lower() in extensii and not p.name.startswith("._")
    ])

    documente_index = []
    statistici = {
        "pdf": len(fisiere_pdf),
        "pagini": 0,
        "tabele": 0,
        "erori": 0,
    }

    for pdf_path in fisiere_pdf:
        doc_info = proceseaza_pdf(pdf_path, nume_dosar, folder_brut)
        documente_index.append(doc_info)

        if doc_info["eroare"] is not None:
            statistici["erori"] += 1
        else:
            statistici["pagini"] += doc_info["pagini"]
            statistici["tabele"] += doc_info["tabele"]

    index_data = {
        "dosar": nume_dosar,
        "documente": documente_index,
    }

    cale_index = folder_brut / "index.json"
    with open(cale_index, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    return statistici


def rezolva_cale_dosar(cale_str: str) -> Path:
    """Rezolvă calea unui dosar fie relativă la cwd, fie la rădăcina proiectului."""
    cale = Path(cale_str)
    if cale.exists():
        return cale.resolve()

    # Încearcă relativ la folderul părinte al extraction
    radacina_proiect = Path(__file__).resolve().parent.parent
    cale_alt = radacina_proiect / cale_str
    if cale_alt.exists():
        return cale_alt.resolve()

    return cale


def gaseste_dosare(argumente: list[str]) -> list[Path]:
    """Identifică dosarele care trebuie procesate."""
    if argumente:
        dosare = []
        for arg in argumente:
            cale = rezolva_cale_dosar(arg)
            if cale.is_dir():
                dosare.append(cale)
            else:
                print(f"[AVERTISMENT] Folderul specificat nu a fost găsit: {arg}", file=sys.stderr)
        return dosare

    # Căutare automată în dosare/
    cale_dosare = Path("dosare")
    if not cale_dosare.exists():
        radacina_proiect = Path(__file__).resolve().parent.parent
        cale_dosare = radacina_proiect / "dosare"

    if not cale_dosare.exists():
        print(f"[EROARE] Nu s-a găsit directorul 'dosare/'.", file=sys.stderr)
        return []

    return sorted([
        p.resolve() for p in cale_dosare.iterdir()
        if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("_")
    ])


def main() -> None:
    """Punctul de intrare pentru scriptul de extragere brută."""
    dosare = gaseste_dosare(sys.argv[1:])

    if not dosare:
        print("Nu a fost găsit niciun dosar de procesat.")
        return

    total_dosare = len(dosare)
    total_pdf = 0
    total_pagini = 0
    total_tabele = 0
    total_erori = 0

    for dosar in dosare:
        stats = proceseaza_dosar(dosar)
        total_pdf += stats["pdf"]
        total_pagini += stats["pagini"]
        total_tabele += stats["tabele"]
        total_erori += stats["erori"]

    print("=" * 50)
    print("REZUMAT EXTRACȚIE BRUTĂ")
    print("=" * 50)
    print(f"Dosare procesate: {total_dosare}")
    print(f"Fișiere PDF:      {total_pdf}")
    print(f"Pagini extrase:   {total_pagini}")
    print(f"Tabele extrase:   {total_tabele}")
    print(f"Erori întâlnite:  {total_erori}")
    print("=" * 50)


if __name__ == "__main__":
    main()
