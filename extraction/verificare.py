"""Modul pentru verificarea anti-halucinație, calculul încrederii și detectarea conflictelor."""

import re
from typing import Any, Optional
import unicodedata


def curata_text_pentru_verificare(text: str) -> str:
    """Normalizează un text pentru verificarea prezenței citatului (spații, litere mici, fără diacritice)."""
    if not text:
        return ""
    # Elimină diacritice
    nfkd = unicodedata.normalize("NFKD", text)
    fara_diacritice = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Tabelele ajung la LLM în markdown: '|' separă celule, nu e text din document
    fara_separatori = fara_diacritice.replace("|", " ")
    # Comprimă spațiile albe (newline, tab etc.) la un singur spațiu
    curatat = re.sub(r"\s+", " ", fara_separatori).strip().lower()
    return curatat


def verifica_citat_in_pagina(citat: str, text_pagina: str) -> bool:
    """Verifică dacă un citat se regăsește în textul unei pagini."""
    if not citat:
        return False

    citat_norm = curata_text_pentru_verificare(citat)
    text_norm = curata_text_pentru_verificare(text_pagina)

    if not citat_norm:
        return False

    # 1. Căutare exactă a fragmentului normalizat
    if citat_norm in text_norm:
        return True

    # 2. Dacă citatul e mai lung, verificăm dacă o sub-fereastră de cuvinte cheie din citat se regăsește
    cuvinte_citat = citat_norm.split()
    if len(cuvinte_citat) >= 4:
        # Caută primele 4 cuvinte sau ultimele 4 cuvinte
        inceput = " ".join(cuvinte_citat[:4])
        sfarsit = " ".join(cuvinte_citat[-4:])
        if inceput in text_norm or sfarsit in text_norm:
            return True

    return False


def extrage_text_complet_pagina(pagina: dict[str, Any]) -> str:
    """Reunește textul principal și celulele din tabelele unei pagini."""
    bucati = [pagina.get("text", "")]
    for t in pagina.get("tabele", []):
        for r in t.get("randuri", []):
            bucati.append(" ".join(str(c) for c in r if c))
    return " ".join(bucati)


def verifica_citat(
    citat: str,
    pagina_indicata: int,
    doc_brut: dict[str, Any],
) -> tuple[bool, int, Optional[str]]:
    """Verifică existența citatului pe pagina indicată sau în restul documentului.

    Întoarce:
        (este_verificat, pagina_gasita, sursa_formatata)
    """
    if not citat:
        return False, pagina_indicata, None

    nume_fisier = doc_brut.get("fisier", "")
    pagini = doc_brut.get("pagini", [])

    # 1. Caută pe pagina indicată
    for p in pagini:
        if p.get("pagina") == pagina_indicata:
            text_p = extrage_text_complet_pagina(p)
            if verifica_citat_in_pagina(citat, text_p):
                return True, pagina_indicata, f"{nume_fisier}, p.{pagina_indicata}"

    # 2. Dacă nu a fost găsit pe pagina indicată, caută în tot documentul
    for p in pagini:
        nr_p = p.get("pagina", 1)
        if nr_p != pagina_indicata:
            text_p = extrage_text_complet_pagina(p)
            if verifica_citat_in_pagina(citat, text_p):
                return True, nr_p, f"{nume_fisier}, p.{nr_p}"

    # 3. Nu a fost găsit deloc în document
    return False, pagina_indicata, None


def calculeaza_incredere_finala(
    incredere_llm: float,
    citat_verificat: bool,
    normalizare_reusita: bool,
    este_document_probabil: bool,
    provine_din_ocr: bool = False,
) -> float:
    """Calculează scorul de încredere final conform cerințelor:

    - ×1.0 dacă citatul e verificat
    - ×0.5 dacă normalizarea a eșuat
    - ×0.8 dacă documentul nu e de tipul „probabil”
    - ×0.7 dacă vine din OCR
    Rotunjește la 2 zecimale.
    """
    if not citat_verificat:
        # Citatul nu a fost găsit deloc => valoarea e respinsă
        return 0.0

    incredere = float(incredere_llm)
    incredere *= 1.0

    if not normalizare_reusita:
        incredere *= 0.5

    if not este_document_probabil:
        incredere *= 0.8

    if provine_din_ocr:
        incredere *= 0.7

    return round(max(0.0, min(1.0, incredere)), 2)


def sunt_valori_in_conflict(val1: Any, val2: Any) -> bool:
    """Verifică dacă două valori ale aceluiași câmp diferă semnificativ (> 2% pentru numere)."""
    if val1 is None or val2 is None:
        return False

    if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
        max_val = max(abs(val1), abs(val2))
        if max_val == 0:
            return False
        diferenta_relativa = abs(val1 - val2) / max_val
        return diferenta_relativa > 0.02

    # Pentru șiruri de caractere / alte tipuri
    return str(val1).strip().lower() != str(val2).strip().lower()


def rezolva_conflicte_camp(
    camp_nume: str,
    candidati: list[dict[str, Any]],
    catalog_campuri: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """Selectează valoarea din documentul preferat și notează conflictele identificate.

    Întoarce (candidat_selectat, lista_conflicte).
    """
    if not candidati:
        return None, []

    # Ordonează candidații după ordinea documentelor probabile din catalog
    doc_probabile = catalog_campuri.get(camp_nume, {}).get("documente_probabile", [])

    def rang_preferinta(c: dict[str, Any]) -> int:
        tip = c.get("tip_document")
        if tip in doc_probabile:
            return doc_probabile.index(tip)
        return 999

    candidati_ordonati = sorted(candidati, key=rang_preferinta)
    ales = candidati_ordonati[0]

    conflicte = []
    for alt in candidati_ordonati[1:]:
        if sunt_valori_in_conflict(ales.get("valoare_normalizata"), alt.get("valoare_normalizata")):
            conflicte.append({
                "camp": camp_nume,
                "valoare_aleasa": ales.get("valoare_normalizata"),
                "document_ales": ales.get("fisier"),
                "valoare_alternativa": alt.get("valoare_normalizata"),
                "document_alternativ": alt.get("fisier"),
                "citat_alternativ": alt.get("citat"),
            })

    return ales, conflicte


# Cuvinte care neagă o afirmație (RO + EN), comparate fără diacritice, ca cuvinte întregi
NEGATII = {
    "nu", "fara", "niciun", "nicio", "nici", "niciodata", "nimic", "neutilizat",
    "not", "no", "without", "never", "none", "non", "nor", "doesn't", "don't", "isn't", "aren't", "won't",
}


def numara_negatii(citat: str) -> int:
    """Numărul de cuvinte de negație din citat."""
    cuvinte = re.findall(r"[a-z']+", curata_text_pentru_verificare(citat))
    return sum(1 for c in cuvinte if c in NEGATII)


def verifica_da_nu(valoare: Optional[bool], citat: str) -> tuple[Optional[bool], Optional[str]]:
    """Confruntă o valoare da/nu cu negațiile din citat.

    - true cu citat negat sau false cu citat fără negație -> ambiguu (null);
    - mai mult de o negație (ex. dublă negație) -> ambiguu (null).
    Întoarce (valoare, motiv) — motiv e „citat ambiguu” când valoarea devine null.
    """
    if valoare is None:
        return None, None
    if not citat or not citat.strip():
        return None, "citat ambiguu"
    negatii = numara_negatii(citat)
    if negatii > 1:
        return None, "citat ambiguu"
    if valoare is True and negatii == 1:
        return None, "citat ambiguu"
    if valoare is False and negatii == 0:
        return None, "citat ambiguu"
    return valoare, None
