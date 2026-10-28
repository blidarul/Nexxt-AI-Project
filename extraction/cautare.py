"""Modul pentru căutarea în trepte a paginilor candidate pentru fiecare câmp."""

from pathlib import Path
import unicodedata
from typing import Any, Optional
import yaml


def incarca_catalog_campuri(cale_catalog: Optional[Path] = None) -> dict[str, Any]:
    """Încarcă fișierul campuri.yaml."""
    if cale_catalog is None:
        cale = Path(__file__).resolve().parent / "campuri.yaml"
    else:
        cale = Path(cale_catalog)

    with open(cale, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalizeaza_text_cautare(text: str) -> str:
    """Elimină diacriticele și convertește la litere mici pentru comparare."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    fara_diacritice = "".join(c for c in nfkd if not unicodedata.combining(c))
    return fara_diacritice.lower()


def evalueaza_pagina(pagina: dict[str, Any], cuvinte_cheie: list[str]) -> int:
    """Calculează scorul de potrivire al unei pagini pe baza frecvenței cuvintelor-cheie."""
    text_pagina = pagina.get("text", "")
    # Include și textul din tabele
    for tabel in pagina.get("tabele", []):
        for rand in tabel.get("randuri", []):
            text_pagina += " " + " ".join(str(c) for c in rand)

    text_norm = normalizeaza_text_cautare(text_pagina)
    scor = 0

    for kw in cuvinte_cheie:
        kw_norm = normalizeaza_text_cautare(kw)
        if kw_norm:
            scor += text_norm.count(kw_norm)

    return scor


def gaseste_pagini_treapta_1(
    camp_nume: str,
    info_camp: dict[str, Any],
    documente_clasificate: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Treapta 1 (țintită): Caută în paginile documentelor de tip 'probabil'.

    Ordonează paginile după numărul de potriviri și ia primele maxim 3 pagini.
    """
    tipuri_probabile = info_camp.get("documente_probabile", [])
    cuvinte_cheie = info_camp.get("cuvinte_cheie", [])

    rezultate = []

    for doc in documente_clasificate:
        tip_doc = doc.get("tip_document")
        if tip_doc not in tipuri_probabile:
            continue

        pagini = doc.get("pagini", [])
        pagini_cu_scor = []

        for pag in pagini:
            scor = evalueaza_pagina(pag, cuvinte_cheie)
            pagini_cu_scor.append((scor, pag))

        # Ordonează după scor descrescător
        pagini_cu_scor.sort(key=lambda x: x[0], reverse=True)

        # Dacă sunt pagini cu scor > 0, selectează primele 3
        # Dacă niciuna nu are scor > 0 dar documentul are <= 3 pagini, le luăm pe toate
        selectate = []
        for scor, pag in pagini_cu_scor:
            if scor > 0 or len(pagini) <= 3:
                selectate.append(pag)
            if len(selectate) >= 3:
                break

        if selectate:
            rezultate.append({
                "fisier": doc.get("fisier"),
                "tip_document": tip_doc,
                "pagini": selectate,
                "doc_complet": doc,
            })

    return rezultate


def gaseste_pagini_treapta_2(
    camp_nume: str,
    info_camp: dict[str, Any],
    documente_clasificate: list[dict[str, Any]],
    documente_deja_incercate: set[str],
) -> list[dict[str, Any]]:
    """Treapta 2 (extinsă): Caută în TOATE documentele neîncercate încă."""
    cuvinte_cheie = info_camp.get("cuvinte_cheie", [])
    rezultate = []

    for doc in documente_clasificate:
        fisier = doc.get("fisier")
        if fisier in documente_deja_incercate:
            continue

        pagini = doc.get("pagini", [])
        pagini_cu_scor = []

        for pag in pagini:
            scor = evalueaza_pagina(pag, cuvinte_cheie)
            if scor > 0:
                pagini_cu_scor.append((scor, pag))

        pagini_cu_scor.sort(key=lambda x: x[0], reverse=True)
        selectate = [pag for scor, pag in pagini_cu_scor[:3]]

        if selectate:
            rezultate.append({
                "fisier": fisier,
                "tip_document": doc.get("tip_document"),
                "pagini": selectate,
                "doc_complet": doc,
            })

    return rezultate


def gaseste_bucle_treapta_3(
    documente_clasificate: list[dict[str, Any]],
    pagini_deja_vizitate: dict[str, set[int]],
    max_caractere_bucata: int = 6000,
) -> list[dict[str, Any]]:
    """Treapta 3 (completă): Parcurge restul paginilor neexaminate în bucăți de max ~6000 caractere."""
    bucati = []

    for doc in documente_clasificate:
        fisier = doc.get("fisier", "")
        pagini_viz = pagini_deja_vizitate.get(fisier, set())

        grup_pagini = []
        caractere_curente = 0

        for pag in doc.get("pagini", []):
            nr_pag = pag.get("pagina", 1)
            if nr_pag in pagini_viz:
                continue

            lungime_pag = len(pag.get("text", ""))
            if grup_pagini and (caractere_curente + lungime_pag > max_caractere_bucata):
                bucati.append({
                    "fisier": fisier,
                    "tip_document": doc.get("tip_document"),
                    "pagini": grup_pagini,
                    "doc_complet": doc,
                })
                grup_pagini = []
                caractere_curente = 0

            grup_pagini.append(pag)
            caractere_curente += lungime_pag

        if grup_pagini:
            bucati.append({
                "fisier": fisier,
                "tip_document": doc.get("tip_document"),
                "pagini": grup_pagini,
                "doc_complet": doc,
            })

    return bucati


def grupeaza_campuri_pe_documente(
    alocari_campuri: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    """Grupează câmpurile per document pentru a efectua un singur apel LLM per document.

    Ieșire:
        {
            "01_cerere_finantare.pdf": {
                "doc": doc_complet,
                "pagini": [pagina_dict, ...],
                "campuri": ["cui", "suma_eur", ...]
            }
        }
    """
    grupare: dict[str, dict[str, Any]] = {}

    for camp, lista_doc_candidat in alocari_campuri.items():
        for item in lista_doc_candidat:
            fisier = item["fisier"]
            if fisier not in grupare:
                grupare[fisier] = {
                    "fisier": fisier,
                    "tip_document": item["tip_document"],
                    "doc": item["doc_complet"],
                    "pagini_map": {},
                    "campuri": [],
                }

            if camp not in grupare[fisier]["campuri"]:
                grupare[fisier]["campuri"].append(camp)

            for p in item["pagini"]:
                nr_pag = p.get("pagina", 1)
                if nr_pag not in grupare[fisier]["pagini_map"]:
                    grupare[fisier]["pagini_map"][nr_pag] = p

    # Convertește pagini_map în listă ordonată de pagini
    rezultat = {}
    for fisier, date in grupare.items():
        pagini_ordonate = sorted(date["pagini_map"].values(), key=lambda x: x.get("pagina", 1))
        rezultat[fisier] = {
            "fisier": fisier,
            "tip_document": date["tip_document"],
            "doc": date["doc"],
            "pagini": pagini_ordonate,
            "campuri": date["campuri"],
        }

    return rezultat
