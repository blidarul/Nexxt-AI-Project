"""OCR pentru pagini PDF fără text și pentru imagini (.jpg/.png) din dosar.

Pagina se randează cu pypdfium2 și se transcrie cu modelul de vision (LLM_MODEL_VISION).
Rândurile transcrise ca „celulă | celulă” se refac într-un tabel, ca extragerea din tabele să
funcționeze și pe documente scanate. Răspunsurile intră în cache ca orice apel LLM.
"""

import io
from pathlib import Path
from typing import Any, Optional

from extraction.llm_client import LLMClient, get_llm_client

PROMPT_OCR = (
    "Transcrie EXACT tot textul din această imagine a unui document, în ordinea citirii, rând cu rând. "
    "Pentru tabele, scrie fiecare rând al tabelului pe o singură linie, cu celulele separate prin ' | '. "
    "Nu adăuga comentarii, nu traduce, nu corecta și nu rezuma. Dacă imaginea nu conține text, răspunde cu un șir gol."
)

SCALA_RANDARE = 2.0
MIME_IMAGINI = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def randeaza_pagina_png(cale_pdf: Path, index_pagina: int, scala: float = SCALA_RANDARE) -> bytes:
    """Randează o pagină PDF (index de la 0) ca PNG."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(cale_pdf))
    try:
        imagine = pdf[index_pagina].render(scale=scala).to_pil()
        buffer = io.BytesIO()
        imagine.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        pdf.close()


def tabele_din_text_ocr(text: str) -> list[dict[str, Any]]:
    """Reface tabelele din liniile consecutive transcrise ca „a | b | c” (același număr de celule)."""
    tabele: list[dict[str, Any]] = []
    curent: list[list[str]] = []

    def inchide() -> None:
        if len(curent) >= 2:
            tabele.append({"index": len(tabele), "randuri": [list(r) for r in curent]})
        curent.clear()

    for linie in text.splitlines():
        if "|" not in linie:
            inchide()
            continue
        celule = [c.strip() for c in linie.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in celule):
            continue  # separator markdown |---|---|
        if curent and len(celule) != len(curent[0]):
            inchide()
        curent.append(celule)
    inchide()
    return tabele


def transcrie_imagine(imagine: bytes, mime_type: str, llm_client: Optional[LLMClient] = None) -> str:
    client = llm_client or get_llm_client()
    text = client.apeleaza_vision(PROMPT_OCR, imagine, mime_type=mime_type)
    text = LLMClient.curata_text_raspuns(text)
    # unele modele încadrează transcrierea în ```
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1] if "\n" in text else ""
    return text.strip()


def pagina_ocr(nr_pagina: int, imagine: bytes, mime_type: str, llm_client: Optional[LLMClient] = None) -> dict[str, Any]:
    """O pagină în formatul din _brut/, cu textul obținut prin OCR."""
    text = transcrie_imagine(imagine, mime_type, llm_client)
    return {
        "pagina": nr_pagina,
        "text": text,
        "necesita_ocr": not bool(text),
        "ocr": True,
        "tabele": tabele_din_text_ocr(text),
    }


def aplica_ocr_pdf(cale_pdf: Path, pagini: list[dict[str, Any]], llm_client: Optional[LLMClient] = None) -> list[str]:
    """Completează prin OCR paginile marcate necesita_ocr. Întoarce erorile (dacă OCR-ul a eșuat)."""
    erori = []
    for idx, pag in enumerate(pagini):
        if not pag.get("necesita_ocr"):
            continue
        try:
            rezultat = pagina_ocr(pag.get("pagina", idx + 1), randeaza_pagina_png(cale_pdf, idx), "image/png", llm_client)
            pag.update(rezultat)
        except Exception as e:  # OCR indisponibil: pagina rămâne fără text, marcată
            erori.append(f"p.{pag.get('pagina', idx + 1)}: {e}")
    return erori
