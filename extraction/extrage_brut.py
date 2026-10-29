"""Script pentru extragerea brută a tuturor PDF-urilor din dosare în format JSON."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from extraction.ocr import MIME_IMAGINI, aplica_ocr_pdf, pagina_ocr
from extraction.pdf_text import extrage_pagini_pdf


def determina_tip_din_nume(nume_fisier: str) -> Optional[str]:
    """Ghicește tipul documentului din numele fișierului. DOAR indiciu, pentru raport:
    tipul folosit în extracție vine din conținut (extraction/clasificare.py).

    Întoarce o cheie din tipuri_documente.yaml sau None dacă numele nu spune nimic.
    """
    nume = nume_fisier.lower()
    if nume.startswith("01_") or "cerere" in nume:
        return "cerere_finantare"
    elif nume.startswith("03_") or "performan" in nume or "energetic" in nume:
        return "certificat_energetic"
    elif nume.startswith("04_") or "chirias" in nume:
        return "contract_inchiriere"
    elif "breeam" in nume or "sustenabilitate" in nume or "leed" in nume:
        return "certificat_sustenabilitate"
    elif "anaf" in nume:
        return "raspuns_anaf"
    elif "breviar" in nume or "nota_tehnica" in nume:
        return "nota_tehnica"
    elif "taxonomie" in nume or "taxonomy" in nume:
        return "raport_taxonomie_ue"
    elif "lca" in nume:
        return "analiza_ciclu_viata"
    elif "etanseitate" in nume:
        return "raport_etanseitate"
    elif "ppa" in nume:
        return "contract_ppa_verde"
    elif "epd" in nume or "declaratii_de_mediu" in nume:
        return "declaratie_mediu_produs"
    elif "eea" in nume:
        return "registru_eea"
    return None


def proceseaza_pdf(cale_pdf: Path, nume_dosar: str, folder_brut: Path) -> dict[str, Any]:
    """Extrage conținutul brut al unui PDF și îl salvează în folderul _brut.

    Întoarce metadatele documentului pentru index.json.
    """
    tip_din_nume = determina_tip_din_nume(cale_pdf.name)
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
            "tip_din_nume": tip_din_nume,
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
            "tip_din_nume": tip_din_nume,
            "json": cale_json_relativa,
            "pagini": nr_pagini,
            "tabele": nr_tabele,
            "pagini_ocr": sum(1 for p in pagini if p.get("ocr")),
            "eroare": "; ".join(erori_ocr) or None,
        }

    except Exception as e:
        return {
            "fisier": cale_pdf.name,
            "tip_din_nume": tip_din_nume,
            "json": None,
            "pagini": 0,
            "tabele": 0,
            "eroare": str(e),
        }


def json_in_text_si_tabele(date_json: Any, nume_fisier: str) -> tuple[str, list[dict[str, Any]]]:
    """Transformă datele dintr-un fișier JSON într-un text lizibil și tabele pentru șablonul _brut."""
    linii_text = [f"=== DOCUMENT JSON: {nume_fisier} ==="]
    tabele: list[dict[str, Any]] = []

    def aplatizeaza_dict(d: dict, prefix: str = "") -> list[tuple[str, Any]]:
        rez = []
        for k, v in d.items():
            if str(k).startswith("_"):
                continue
            cheie = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                rez.extend(aplatizeaza_dict(v, cheie))
            elif isinstance(v, list):
                if all(isinstance(x, dict) for x in v):
                    for idx, item in enumerate(v):
                        rez.extend(aplatizeaza_dict(item, f"{cheie}[{idx}]"))
                else:
                    rez.append((cheie, ", ".join(str(x) for x in v)))
            else:
                rez.append((cheie, v))
        return rez

    if isinstance(date_json, dict):
        perechi = aplatizeaza_dict(date_json)
        for k, v in perechi:
            linii_text.append(f"{k}: {v}")
            scurta = k.split(".")[-1]
            if scurta != k:
                linii_text.append(f"{scurta}: {v}")

        randuri_tabel = [["Camp", "Valoare"]]
        for k, v in perechi:
            randuri_tabel.append([str(k), str(v)])
        if len(randuri_tabel) > 1:
            tabele.append({"index": 0, "randuri": randuri_tabel})

        tabel_idx = 1
        for k, v in date_json.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                antet = sorted({col for item in v for col in item.keys() if not str(col).startswith("_")})
                if antet:
                    randuri = [antet]
                    for item in v:
                        randuri.append([str(item.get(col, "")) for col in antet])
                    tabele.append({"index": tabel_idx, "nume": k, "randuri": randuri})
                    tabel_idx += 1

    elif isinstance(date_json, list):
        if date_json and all(isinstance(x, dict) for x in date_json):
            antet = sorted({col for item in date_json for col in item.keys() if not str(col).startswith("_")})
            randuri = [antet]
            for item in date_json:
                randuri.append([str(item.get(col, "")) for col in antet])
                for col in antet:
                    linii_text.append(f"{col}: {item.get(col, '')}")
            tabele.append({"index": 0, "randuri": randuri})
        else:
            for item in date_json:
                linii_text.append(f"- {item}")

    linii_text.append("\n[CONTINUT STRUCTURAT JSON]")
    try:
        linii_text.append(json.dumps(date_json, ensure_ascii=False, indent=2))
    except Exception:
        linii_text.append(str(date_json))

    return "\n".join(linii_text), tabele


def proceseaza_json(cale_json: Path, nume_dosar: str, folder_brut: Path) -> dict[str, Any]:
    """Extrage conținutul unui fișier JSON dintr-un dosar, îl adaptează la șablonul _brut și îl salvează în _brut.

    Întoarce metadatele documentului pentru index.json.
    """
    tip_din_nume = determina_tip_din_nume(cale_json.name)
    cale_json_relativa = f"_brut/{cale_json.name}"
    cale_json_iesire = folder_brut / cale_json.name

    try:
        with open(cale_json, "r", encoding="utf-8") as f:
            date_json = json.load(f)

        if tip_din_nume is None and isinstance(date_json, dict):
            keys_str = str(list(date_json.keys())).lower()
            val_str = str(date_json).lower()
            if "breeam" in val_str or "certificate_no" in keys_str:
                tip_din_nume = "certificat_sustenabilitate"
            elif "found" in keys_str or ("cui" in val_str and "caen" in val_str):
                tip_din_nume = "raspuns_anaf"
            elif "eea" in keys_str or "wltp" in keys_str:
                tip_din_nume = "registru_eea"

        text_pag, tabele = json_in_text_si_tabele(date_json, cale_json.name)

        continut_brut: dict[str, Any] = {
            "fisier": cale_json.name,
            "dosar": nume_dosar,
            "tip_din_nume": tip_din_nume,
            "nr_pagini": 1,
            "extras_la": datetime.now().isoformat(timespec="seconds"),
            "pagini": [
                {
                    "pagina": 1,
                    "text": text_pag,
                    "necesita_ocr": False,
                    "tabele": tabele,
                }
            ],
            "date": date_json,
            "continut_json": date_json,
        }

        # Copiază cheile din JSON-ul original dacă este dicționar, fără a suprascrie șablonul
        if isinstance(date_json, dict):
            for k, v in date_json.items():
                if k not in continut_brut:
                    continut_brut[k] = v

        with open(cale_json_iesire, "w", encoding="utf-8") as f:
            json.dump(continut_brut, f, ensure_ascii=False, indent=2)

        return {
            "fisier": cale_json.name,
            "tip_din_nume": tip_din_nume,
            "json": cale_json_relativa,
            "pagini": 1,
            "tabele": len(tabele),
            "pagini_ocr": 0,
            "eroare": None,
        }

    except Exception as e:
        return {
            "fisier": cale_json.name,
            "tip_din_nume": tip_din_nume,
            "json": None,
            "pagini": 0,
            "tabele": 0,
            "pagini_ocr": 0,
            "eroare": str(e),
        }


def proceseaza_dosar(cale_dosar: Path) -> dict[str, int]:
    """Procesează toate fișierele PDF și JSON dintr-un dosar și generează index.json."""
    nume_dosar = cale_dosar.name
    folder_brut = cale_dosar / "_brut"
    if folder_brut.exists():
        for p in folder_brut.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass
    folder_brut.mkdir(parents=True, exist_ok=True)

    # PDF-uri și imagini (.jpg/.png, transcrise prin OCR)
    extensii = {".pdf"} | set(MIME_IMAGINI)
    fisiere_pdf = sorted([
        p for p in cale_dosar.iterdir()
        if p.is_file() and p.suffix.lower() in extensii and not p.name.startswith("._")
    ])

    # Fișiere JSON din dosar (excluzând expected.json, extras_mock.json, index.json etc.)
    fisiere_json = sorted([
        p for p in cale_dosar.iterdir()
        if p.is_file() and p.suffix.lower() == ".json"
        and not p.name.startswith("._") and not p.name.startswith(".")
        and p.name not in ("expected.json", "extras_mock.json", "index.json")
    ])

    documente_index = []
    statistici = {
        "pdf": len(fisiere_pdf),
        "json": len(fisiere_json),
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

    for json_path in fisiere_json:
        doc_info = proceseaza_json(json_path, nume_dosar, folder_brut)
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
    total_json = 0
    total_pagini = 0
    total_tabele = 0
    total_erori = 0

    for dosar in dosare:
        stats = proceseaza_dosar(dosar)
        total_pdf += stats.get("pdf", 0)
        total_json += stats.get("json", 0)
        total_pagini += stats["pagini"]
        total_tabele += stats["tabele"]
        total_erori += stats["erori"]

    print("=" * 50)
    print("REZUMAT EXTRACȚIE BRUTĂ")
    print("=" * 50)
    print(f"Dosare procesate: {total_dosare}")
    print(f"Fișiere PDF:      {total_pdf}")
    print(f"Fișiere JSON:     {total_json}")
    print(f"Pagini extrase:   {total_pagini}")
    print(f"Tabele extrase:   {total_tabele}")
    print(f"Erori întâlnite:  {total_erori}")
    print("=" * 50)


if __name__ == "__main__":
    main()
