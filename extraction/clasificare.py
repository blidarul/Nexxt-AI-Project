"""Modul pentru clasificarea documentelor pe baza conținutului primelor pagini."""

import json
from pathlib import Path
from typing import Any, Optional

from extraction.llm_client import LLMClient, get_llm_client

TIPURI_DOCUMENTE_PERMISE = {
    "cerere_finantare",
    "certificat_energetic",
    "contract_inchiriere",
    "certificat_sustenabilitate",
    "extras_carte_funciara",
    "situatii_financiare",
    "alt_document",
}


def construieste_text_clasificare(doc_brut: dict[str, Any], max_caractere: int = 3000) -> str:
    """Extrage textul primelor 2 pagini pentru clasificare, limitat la max_caractere."""
    pagini = doc_brut.get("pagini", [])
    fragmente = []
    total_len = 0

    for pag in pagini[:2]:
        nr_pag = pag.get("pagina", 1)
        text_pag = pag.get("text", "")
        fragmente.append(f"=== PAGINA {nr_pag} ===\n{text_pag}\n")
        total_len += len(text_pag)
        if total_len >= max_caractere:
            break

    text_complet = "\n".join(fragmente)
    return text_complet[:max_caractere]


def clasifica_document(
    doc_brut: dict[str, Any],
    llm_client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """Clasifică documentul în funcție de conținutul textului primelor 2 pagini.

    Întoarce un dicționar cu:
        - tip_document: unul din TIPURI_DOCUMENTE_PERMISE
        - incredere: float 0.0 - 1.0
        - motiv: explicație scurtă
    """
    client = llm_client or get_llm_client()
    nume_fisier = doc_brut.get("fisier", "necunoscut.pdf")
    text_document = construieste_text_clasificare(doc_brut)

    prompt_sistem = (
        "Ești un asistent bancar expert în analiza documentelor pentru credite verzi.\n"
        "Sarcina ta este să clasifici documentul primit într-unul din următoarele tipuri fixe:\n"
        "- cerere_finantare (cerere de credit / finanțare depusă la bancă)\n"
        "- certificat_energetic (certificat de performanță energetică, date EPC, consum kWh/m2)\n"
        "- contract_inchiriere (contract de închiriere, extras chiriași, suprafețe închiriate)\n"
        "- certificat_sustenabilitate (certificat BREEAM, LEED, DGNB etc.)\n"
        "- extras_carte_funciara (carte funciară, cadastru)\n"
        "- situatii_financiare (bilanț, cont de profit și pierdere)\n"
        "- alt_document (orice altceva ce nu se încadrează în cele de mai sus)\n\n"
        "Reguli:\n"
        "1. Clasifică DOAR pe baza conținutului din text. Numele fișierului este doar un indiciu secundar.\n"
        "2. Întoarce EXCLUSIV un obiect JSON de forma:\n"
        '{"tip_document": "...", "incredere": 0.95, "motiv": "..."}'
    )

    prompt_utilizator = (
        f"Nume fișier (indiciu): {nume_fisier}\n\n"
        f"Conținut primele pagini:\n"
        f"{text_document}\n\n"
        "Clasifică acest document."
    )

    mesaje = [
        {"role": "system", "content": prompt_sistem},
        {"role": "user", "content": prompt_utilizator},
    ]

    date_json, eroare = client.apeleaza_cu_json(mesaje)

    if date_json and isinstance(date_json, dict):
        tip = date_json.get("tip_document")
        if tip in TIPURI_DOCUMENTE_PERMISE:
            incredere = float(date_json.get("incredere", 0.9))
            return {
                "tip_document": tip,
                "incredere": round(max(0.0, min(1.0, incredere)), 2),
                "motiv": date_json.get("motiv", "Clasificare pe baza conținutului de către LLM"),
            }

    # Fallback euristic dacă LLM nu a întors un tip valid
    text_lower = text_document.lower()
    if "cerere de finanțare" in text_lower or "cerere de finantare" in text_lower or "solicitant" in text_lower:
        return {"tip_document": "cerere_finantare", "incredere": 0.8, "motiv": "Fallback euristic: cerere de finanțare"}
    elif "certificat de performanță energetică" in text_lower or "certificat de performanta energetica" in text_lower or "clasa energetică" in text_lower:
        return {"tip_document": "certificat_energetic", "incredere": 0.8, "motiv": "Fallback euristic: certificat energetic"}
    elif "chiriaș" in text_lower or "chirias" in text_lower or "contracte de închiriere" in text_lower or "contracte de inchiriere" in text_lower:
        return {"tip_document": "contract_inchiriere", "incredere": 0.8, "motiv": "Fallback euristic: contract închiriere"}

    return {
        "tip_document": "alt_document",
        "incredere": 0.5,
        "motiv": f"Clasificare nedecisă. Eroare LLM: {eroare}",
    }
