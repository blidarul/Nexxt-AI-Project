"""Modul pentru extragerea valorilor câmpurilor folosind tabele markdown și apeluri LLM."""

import json
import re
from typing import Any, Optional
import unicodedata

from contracts import Chirias
from extraction.llm_client import LLMClient, get_llm_client
from extraction.normalizare import normalizeaza_caen, normalizeaza_numar


def tabel_in_markdown(tabel: dict[str, Any]) -> str:
    """Transformă un tabel brut din JSON într-un tabel în format Markdown."""
    randuri = tabel.get("randuri", [])
    if not randuri:
        return ""

    linii_md = []
    antet = randuri[0]
    antet_str = " | ".join(str(c) if c else "" for c in antet)
    linii_md.append(f"| {antet_str} |")
    linii_md.append("| " + " | ".join("---" for _ in antet) + " |")

    for r in randuri[1:]:
        linie_str = " | ".join(str(c) if c else "" for c in r)
        linii_md.append(f"| {linie_str} |")

    return "\n".join(linii_md)


def formateaza_pagini_pentru_prompt(pagini: list[dict[str, Any]]) -> str:
    """Construiește reprezentarea paginilor pentru LLM, cu marcaje clare și tabele markdown."""
    segmente = []

    for pag in pagini:
        nr_pag = pag.get("pagina", 1)
        text_pag = pag.get("text", "").strip()

        segmente.append(f"=== PAGINA {nr_pag} ===")
        if text_pag:
            segmente.append(text_pag)

        tabele = pag.get("tabele", [])
        if tabele:
            segmente.append(f"\n[TABELE PE PAGINA {nr_pag}]")
            for idx, tab in enumerate(tabele):
                md_tab = tabel_in_markdown(tab)
                if md_tab:
                    segmente.append(f"--- Tabel {idx+1} ---")
                    segmente.append(md_tab)

        segmente.append("\n")

    return "\n".join(segmente)


def extrage_chiriasi_determinist(
    documente_clasificate: list[dict[str, Any]]
) -> tuple[list[Chirias], Optional[str], Optional[str]]:
    """Încearcă extragerea chiriașilor în mod determinist direct din tabelele din documente.

    Întoarce (lista_chiriasi, sursa, citat).
    """
    sinonime_chirias = ["chiriaș", "chirias", "locatar", "tenant", "client", "denumire chiriaș"]
    sinonime_caen = ["caen", "cod caen", "nace", "cod caen principal"]
    sinonime_suprafata = ["suprafață", "suprafata", "suprafață închiriată", "suprafata inchiriata", "area", "m2", "m²", "mp"]

    for doc in documente_clasificate:
        fisier = doc.get("fisier", "")
        for pag in doc.get("pagini", []):
            nr_pag = pag.get("pagina", 1)
            for tab in pag.get("tabele", []):
                randuri = tab.get("randuri", [])
                if len(randuri) < 2:
                    continue

                antet = [str(c).lower().strip() for c in randuri[0]]

                col_chirias = None
                col_caen = None
                col_suprafata = None

                for idx, col in enumerate(antet):
                    if any(s in col for s in sinonime_chirias) and col_chirias is None:
                        col_chirias = idx
                    elif any(s in col for s in sinonime_caen) and col_caen is None:
                        col_caen = idx
                    elif any(s in col for s in sinonime_suprafata) and col_suprafata is None:
                        col_suprafata = idx

                # Dacă am identificat coloanele esențiale
                if col_chirias is not None and col_caen is not None and col_suprafata is not None:
                    chiriasi_gasiti = []
                    citate_colectate = []

                    for r in randuri[1:]:
                        if len(r) <= max(col_chirias, col_caen, col_suprafata):
                            continue

                        val_nume = str(r[col_chirias]).strip()
                        val_caen_raw = str(r[col_caen]).strip()
                        val_sup_raw = str(r[col_suprafata]).strip()

                        if not val_nume or val_nume.lower() in ("total", "subtotal"):
                            continue

                        caen_norm = normalizeaza_caen(val_caen_raw)
                        sup_norm = normalizeaza_numar(val_sup_raw)

                        if caen_norm and sup_norm:
                            chiriasi_gasiti.append(
                                Chirias(
                                    nume=val_nume,
                                    caen=caen_norm,
                                    m2=float(sup_norm),
                                )
                            )
                            citate_colectate.append(f"{val_nume} | {val_caen_raw} | {val_sup_raw}")

                    if chiriasi_gasiti:
                        sursa = f"{fisier}, p.{nr_pag}"
                        citat = "; ".join(citate_colectate[:3])
                        return chiriasi_gasiti, sursa, citat

    return [], None, None


_BULLET = re.compile(r"^\s*[•\-\*–·▪]\s+")
_TITLU_NUMEROTAT = re.compile(r"^\s*\d+[\.\)]\s+\S")


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def extrage_afirmatii_determinist(
    documente: list[dict[str, Any]],
    info_camp: dict[str, Any],
) -> tuple[list[str], Optional[str], list[str]]:
    """Afirmațiile de sustenabilitate ale clientului, extrase determinist din text.

    Se păstrează:
    - toate bullet-urile/frazele din secțiunea de declarații (titluri_sectiune din campuri.yaml);
    - în restul documentului, bullet-urile și frazele încheiate cu punct care conțin un cuvânt
      din cuvinte_afirmatii (rândurile de formular din tabele se ignoră).
    Bullet-urile continuate pe rândul următor se unesc. Întoarce (afirmatii, sursa, citate).
    """
    titluri = [_norm(t) for t in info_camp.get("titluri_sectiune") or []]
    cuvinte = [_norm(c) for c in info_camp.get("cuvinte_afirmatii") or []]
    afirmatii: list[str] = []
    surse: list[str] = []

    def adauga(text: str, fisier: str, pagina: int, in_sectiune: bool) -> None:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 8 or text in afirmatii:
            return
        if in_sectiune or any(c in _norm(text) for c in cuvinte):
            afirmatii.append(text)
            surse.append(f"{fisier}, p.{pagina}")

    for doc in documente:
        fisier = doc.get("fisier", "")
        for pag in doc.get("pagini", []):
            nr = pag.get("pagina", 1)
            randuri_tabel = {
                _norm(" ".join(str(c) for c in r)).strip()
                for t in pag.get("tabele", []) for r in t.get("randuri", [])
            }
            in_sectiune = False
            curent: Optional[str] = None

            def inchide_bullet() -> None:
                nonlocal curent
                if curent is not None:
                    adauga(curent, fisier, nr, in_sectiune)
                    curent = None

            for linie in (pag.get("text") or "").splitlines():
                linie_norm = _norm(linie).strip()
                if not linie_norm:
                    inchide_bullet()
                    continue
                este_titlu = any(t in linie_norm for t in titluri)
                if este_titlu or _TITLU_NUMEROTAT.match(linie):
                    inchide_bullet()
                    in_sectiune = este_titlu
                    continue
                if _BULLET.match(linie):
                    inchide_bullet()
                    curent = _BULLET.sub("", linie)
                    continue
                if curent is not None and not curent.rstrip().endswith("."):
                    curent += " " + linie.strip()  # bullet continuat pe rândul următor
                    continue
                inchide_bullet()
                if linie_norm in randuri_tabel:
                    continue  # rând de formular (cheie | valoare), nu o afirmație
                if in_sectiune:
                    adauga(linie, fisier, nr, True)
                elif linie.strip().endswith(".") and ":" not in linie and len(linie) <= 300:
                    # în afara secțiunii: doar rânduri care sunt fraze complete, nu câmpuri de formular
                    adauga(linie, fisier, nr, False)
            inchide_bullet()

    sursa = "; ".join(dict.fromkeys(surse)) or None
    return afirmatii, sursa, afirmatii[:3]


def extrage_campuri_document_llm(
    fisier: str,
    pagini: list[dict[str, Any]],
    campuri: list[str],
    catalog_campuri: dict[str, Any],
    llm_client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """Trimite paginile selectate la LLM pentru a extrage lista de câmpuri cerute.

    Include reguli stricte împotriva halucinației:
    - null dacă valoarea nu apare explicit
    - citat exact (max 200 caractere)
    - valoare_text brută
    """
    client = llm_client or get_llm_client()
    text_document = formateaza_pagini_pentru_prompt(pagini)

    # Filtrăm exclusiv câmpurile care trebuie extrase din documente (extras_din_document: True)
    campuri_cerute = [
        c for c in campuri
        if catalog_campuri.get(c, {}).get("extras_din_document", True)
    ]
    if not campuri_cerute:
        return {}

    descrieri = []
    are_da_nu = False
    for c in campuri_cerute:
        info = catalog_campuri.get(c, {})
        desc = info.get("descriere", c)
        tip = info.get("tip")
        if tip == "da_nu":
            are_da_nu = True
            descrieri.append(f"- {c} (da/nu): {desc}")
        else:
            descrieri.append(f"- {c}: {desc}")
    descrieri_str = "\n".join(descrieri)
    regula_da_nu = (
        "\nPentru câmpurile (da/nu): 'valoare_text' este \"da\" sau \"nu\", iar 'citat' trebuie să conțină "
        "afirmația sau negația explicită din document. Atenție la negații (\"nu\", \"fără\", \"not\"). "
        "Dacă documentul nu spune explicit, întoarce null (NU \"nu\").\n"
        if are_da_nu else ""
    )

    prompt_sistem = (
        "Ești un asistent de extracție precisă a datelor din documente financiare și tehnice.\n"
        "Sarcina ta este să extragi valorile pentru o listă de câmpuri din paginile furnizate.\n\n"
        "REGULI STRICTE:\n"
        "1. Dacă o valoare nu apare EXPLICIT în textul sau tabelele furnizate, întoarce null. "
        "NU deduce, NU calcula, NU presupune, NU inventa.\n"
        "2. 'citat': fragment copiat EXACT din document (maxim 200 de caractere), care conține valoarea extrasă.\n"
        "3. 'valoare_text': valoarea exact cum apare în document (curățarea și conversia o face codul).\n"
        "4. 'pagina': numărul paginii (ex: 1, 2) unde apare citatul.\n"
        "5. 'incredere': număr între 0.0 și 1.0 (nivelul de siguranță că fragmentul răspunde exact câmpului).\n\n"
        "Pentru câmpul 'afirmatii_client', întoarce o listă de afirmații făcute de client privind sustenabilitatea.\n"
        f"{regula_da_nu}\n"
        "Formatul răspunsului trebuie să fie EXCLUSIV un JSON valid de forma:\n"
        "{\n"
        '  "cui": {"valoare_text": "9900000010", "citat": "CUI 9900000010", "pagina": 1, "incredere": 0.98},\n'
        '  "suma_eur": {"valoare_text": "30.000.000 EUR", "citat": "Suma solicitată de la bancă 30.000.000 EUR", "pagina": 1, "incredere": 0.95}\n'
        "}"
    )

    prompt_utilizator = (
        f"Document: {fisier}\n\n"
        f"Câmpuri de extras:\n{descrieri_str}\n\n"
        f"Conținutul paginilor selectate:\n{text_document}\n\n"
        "Extrage câmpurile cerute în formatul JSON specificat."
    )

    mesaje = [
        {"role": "system", "content": prompt_sistem},
        {"role": "user", "content": prompt_utilizator},
    ]

    date_json, eroare = client.apeleaza_cu_json(mesaje, chei_asteptate=campuri_cerute)
    if date_json and isinstance(date_json, dict):
        return date_json

    return {}
