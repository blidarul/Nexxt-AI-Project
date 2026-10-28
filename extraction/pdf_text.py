"""Modul pentru extragerea textului și tabelelor brute din fișiere PDF."""

from pathlib import Path
from typing import Any
import pdfplumber


def curata_celula(val: Any) -> str:
    """Înlocuiește newline-urile cu un spațiu și elimină spațiile de la capete."""
    if val is None:
        return ""
    return str(val).replace("\n", " ").strip()


def extrage_tabele_pagina(page: pdfplumber.page.Page) -> list[dict[str, Any]]:
    """Extrage și curăță toate tabelele de pe o pagină PDF."""
    tabele_extrase = []
    tables = page.extract_tables() or []
    for idx, table in enumerate(tables):
        randuri = []
        for row in table:
            randuri.append([curata_celula(cell) for cell in row])
        tabele_extrase.append({
            "index": idx,
            "randuri": randuri
        })
    return tabele_extrase


def extrage_pagini_pdf(cale_pdf: Path | str) -> list[dict[str, Any]]:
    """Extrage textul și tabelele pe fiecare pagină a unui document PDF.

    Dacă o pagină nu conține text, este marcată cu necesita_ocr=True.
    """
    cale = Path(cale_pdf)
    pagini = []

    with pdfplumber.open(cale) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text_brut = page.extract_text()
            if text_brut is None or not text_brut.strip():
                text = ""
                necesita_ocr = True
            else:
                text = text_brut
                necesita_ocr = False

            tabele = extrage_tabele_pagina(page)
            pagini.append({
                "pagina": idx,
                "text": text,
                "necesita_ocr": necesita_ocr,
                "tabele": tabele
            })

    return pagini


# Alias pentru compatibilitate directă
extrage_text_pdf = extrage_pagini_pdf
