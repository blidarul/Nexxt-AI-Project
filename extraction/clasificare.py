"""Modul pentru clasificarea documentelor pe baza conținutului primelor pagini.

Tipurile permise, descrierile și cuvintele-cheie vin din extraction/tipuri_documente.yaml.
Numele fișierului NU se folosește: clasificarea e strict din conținut.
"""

from typing import Any, Optional

from extraction.cautare import normalizeaza_text_cautare
from extraction.cerinte import incarca_tipuri_documente
from extraction.llm_client import LLMClient, get_llm_client

TIP_REZERVA = "alt_document"


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


def calculeaza_pre_scor(text: str) -> list[tuple[str, int]]:
    """Pre-scor determinist: câte cuvinte-cheie distincte ale fiecărui tip apar în text.

    Întoarce tipurile cu scor > 0, ordonate descrescător.
    """
    text_norm = normalizeaza_text_cautare(text)
    scoruri = []
    for tip, info in incarca_tipuri_documente().items():
        cuvinte = {normalizeaza_text_cautare(k) for k in info.get("cuvinte_cheie") or []}
        scor = sum(1 for k in cuvinte if k and k in text_norm)
        if scor > 0:
            scoruri.append((tip, scor))
    scoruri.sort(key=lambda x: x[1], reverse=True)
    return scoruri


def _rol_valid(tip: str, rol: Any) -> Optional[str]:
    roluri = incarca_tipuri_documente().get(tip, {}).get("roluri") or {}
    rol_str = str(rol).strip().lower() if rol else ""
    return rol_str if rol_str in roluri else None


def clasifica_document(
    doc_brut: dict[str, Any],
    llm_client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """Clasifică documentul în funcție de conținutul textului primelor 2 pagini.

    Întoarce un dicționar cu:
        - tip_document: o cheie din tipuri_documente.yaml
        - rol: "inainte" / "dupa" / None (doar pentru tipurile cu roluri)
        - incredere: float 0.0 - 1.0
        - motiv: explicație scurtă
        - pre_scor: candidații deterministi [(tip, scor), ...]
    """
    client = llm_client or get_llm_client()
    tipuri = incarca_tipuri_documente()
    text_document = construieste_text_clasificare(doc_brut)
    pre_scor = calculeaza_pre_scor(text_document)

    lista_tipuri = "\n".join(f"- {tip}: {info.get('descriere', '')}" for tip, info in tipuri.items())
    tipuri_cu_rol = [t for t, info in tipuri.items() if info.get("roluri")]

    prompt_sistem = (
        "Ești un asistent bancar expert în analiza documentelor pentru credite verzi.\n"
        "Clasifică documentul primit într-unul din următoarele tipuri fixe:\n"
        f"{lista_tipuri}\n\n"
        "Reguli:\n"
        "1. Clasifică DOAR pe baza conținutului din text.\n"
        f"2. Pentru tipurile {', '.join(tipuri_cu_rol)} completează 'rol': \"inainte\" dacă documentul descrie "
        "situația dinaintea investiției/renovării, \"dupa\" dacă descrie situația de după (realizată sau estimată), "
        "altfel null. Pentru celelalte tipuri, 'rol' este null.\n"
        "3. Întoarce EXCLUSIV un obiect JSON de forma:\n"
        '{"tip_document": "...", "rol": null, "incredere": 0.95, "motiv": "..."}'
    )

    indiciu = ", ".join(f"{t} ({s})" for t, s in pre_scor[:3]) or "niciunul"
    prompt_utilizator = (
        f"Tipuri sugerate de potrivirea cuvintelor-cheie (doar indiciu): {indiciu}\n\n"
        f"Conținut primele pagini:\n"
        f"{text_document}\n\n"
        "Clasifică acest document."
    )

    mesaje = [
        {"role": "system", "content": prompt_sistem},
        {"role": "user", "content": prompt_utilizator},
    ]

    date_json, eroare = client.apeleaza_cu_json(mesaje, motiv="clasificare_document")

    if date_json and isinstance(date_json, dict):
        tip = date_json.get("tip_document")
        if tip in tipuri:
            try:
                incredere = float(date_json.get("incredere", 0.9))
            except (TypeError, ValueError):
                incredere = 0.9
            return {
                "tip_document": tip,
                "rol": _rol_valid(tip, date_json.get("rol")),
                "incredere": round(max(0.0, min(1.0, incredere)), 2),
                "motiv": date_json.get("motiv", "Clasificare pe baza conținutului de către LLM"),
                "pre_scor": pre_scor[:3],
            }

    # Fallback determinist: cel mai bun pre-scor, dacă e suficient de clar
    if pre_scor and pre_scor[0][1] >= 2:
        tip, scor = pre_scor[0]
        return {
            "tip_document": tip,
            "rol": None,
            "incredere": 0.6,
            "motiv": f"Fallback pe cuvinte-cheie ({scor} potriviri). Eroare LLM: {eroare}",
            "pre_scor": pre_scor[:3],
        }

    return {
        "tip_document": TIP_REZERVA,
        "rol": None,
        "incredere": 0.5,
        "motiv": f"Clasificare nedecisă. Eroare LLM: {eroare}",
        "pre_scor": pre_scor[:3],
    }
