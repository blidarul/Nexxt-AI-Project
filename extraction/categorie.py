"""Stabilirea categoriei și subcategoriei proiectului.

LLM-ul alege DOAR din valorile permise citite din rules/*.yaml, cu citat și încredere.
Indiciile deterministe vin din tipurile de documente găsite (tipuri_documente.yaml: indiciu_categorie).
Sub pragul de încredere (categorii.yaml: prag_incredere) se păstrează 2 candidați.
"""

from typing import Any, Optional

from extraction.cerinte import incarca_categorii, incarca_config_categorii, incarca_tipuri_documente
from extraction.llm_client import LLMClient, get_llm_client
from extraction.verificare import verifica_citat

TIP_CERERE = "cerere_finantare"

# Un al doilea candidat cu cel puțin această încredere (și citat verificat) face proiectul mixt
PRAG_CANDIDAT_SECUNDAR = 0.5


def indicii_deterministe(documente_clasificate: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Indiciile de categorie date de documentele găsite.

    Ieșire: [{"categorie", "subcategorie", "forta", "fisier", "tip_document"}, ...]
    """
    tipuri = incarca_tipuri_documente()
    indicii = []
    for doc in documente_clasificate:
        tip = doc.get("tip_document")
        ind = (tipuri.get(tip) or {}).get("indiciu_categorie")
        if ind:
            indicii.append({
                "categorie": ind.get("categorie"),
                "subcategorie": ind.get("subcategorie"),
                "forta": ind.get("forta", "slab"),
                "fisier": doc.get("fisier"),
                "tip_document": tip,
            })
    return indicii


def _text_pentru_categorie(documente_clasificate: list[dict[str, Any]], max_caractere: int = 5000) -> tuple[str, list[dict[str, Any]]]:
    """Textul pe care se decide categoria: cererea de finanțare, altfel începutul fiecărui document."""
    cereri = [d for d in documente_clasificate if d.get("tip_document") == TIP_CERERE]
    surse = cereri or documente_clasificate
    bucati = []
    for doc in surse:
        limita = max_caractere if cereri else 1500
        text = "\n".join(p.get("text", "") for p in doc.get("pagini", [])[:2])[:limita]
        bucati.append(f"=== {doc.get('tip_document')} ===\n{text}")
    return "\n\n".join(bucati)[:max_caractere * 2], surse


def _verifica_citat_in_surse(citat: str, surse: list[dict[str, Any]]) -> Optional[str]:
    for doc in surse:
        gasit, pagina, sursa = verifica_citat(citat, 1, doc)
        if gasit:
            return sursa or f"{doc.get('fisier')}, p.{pagina}"
    return None


def _normalizeaza_candidat(cand: dict[str, Any], categorii: dict[str, Any]) -> Optional[dict[str, Any]]:
    cat = str(cand.get("categorie") or "").strip()
    if cat not in categorii:
        return None
    info = categorii[cat]
    try:
        incredere = float(cand.get("incredere", 0.5))
    except (TypeError, ValueError):
        incredere = 0.5
    incredere = max(0.0, min(1.0, incredere))

    sub = cand.get("subcategorie")
    sub = str(sub).strip() if sub else None
    if sub not in info["subcategorii"]:
        if sub:
            incredere *= 0.8  # a propus o valoare nepermisă
        sub = None

    nivel_3 = cand.get("tip_nivel_3")
    nivel_3 = str(nivel_3).strip() if nivel_3 else None
    if not (sub and sub in info["nivel_3"] and nivel_3 in info["nivel_3"][sub]["valori"]):
        nivel_3 = None

    return {
        "categorie": cat,
        "subcategorie": sub,
        "tip_nivel_3": nivel_3,
        "incredere": incredere,
        "citat": str(cand.get("citat") or ""),
    }


def stabileste_categoria(
    documente_clasificate: list[dict[str, Any]],
    llm_client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """Alege categoria, subcategoria (și tipul de nivel 3, dacă există) pentru dosar.

    Ieșire:
        {
          "candidati": [{"categorie", "subcategorie", "tip_nivel_3", "camp_nivel_3",
                         "camp_subcategorie", "incredere", "citat", "citat_verificat", "sursa"}, ...],
          "ambiguu": bool,            # încrederea primului candidat < prag
          "indicii": [...],           # indiciile deterministe folosite
        }
    """
    client = llm_client or get_llm_client()
    categorii = incarca_categorii()
    prag = float(incarca_config_categorii().get("prag_incredere", 0.7))
    indicii = indicii_deterministe(documente_clasificate)
    text, surse = _text_pentru_categorie(documente_clasificate)

    linii_valori = []
    for cat, info in categorii.items():
        linie = f"- {cat}: subcategorii permise = {info['subcategorii']}"
        for sub, n3 in info["nivel_3"].items():
            linie += f"; pentru {sub}, tip_nivel_3 permis = {n3['valori']}"
        linii_valori.append(linie)

    tipuri_gasite = sorted({d.get("tip_document") for d in documente_clasificate if d.get("tip_document")})

    prompt_sistem = (
        "Ești analist de credite verzi. Stabilește categoria proiectului finanțat conform "
        "RBI Sustainability Bond Framework.\n"
        "Valori PERMISE (folosește exact aceste chei):\n"
        + "\n".join(linii_valori) + "\n\n"
        "Reguli:\n"
        "1. Alege doar din valorile permise. Dacă subcategoria nu reiese din text, pune null.\n"
        "2. 'citat': fragment copiat EXACT din document (max 200 caractere) care justifică alegerea.\n"
        "3. Dacă proiectul acoperă clar o singură categorie, întoarce un singur candidat cu încredere mare.\n"
        "   Dacă proiectul combină două categorii sau e neclar, întoarce 2 candidați, fiecare cu încredere sub 0.7.\n"
        "4. Întoarce EXCLUSIV JSON de forma:\n"
        '{"candidati": [{"categorie": "...", "subcategorie": "...", "tip_nivel_3": null, '
        '"incredere": 0.9, "citat": "..."}]}'
    )
    prompt_utilizator = (
        f"Tipuri de documente găsite în dosar: {', '.join(tipuri_gasite) or 'necunoscute'}\n\n"
        f"Text:\n{text}\n\n"
        "Stabilește categoria."
    )
    date_json, _ = client.apeleaza_cu_json([
        {"role": "system", "content": prompt_sistem},
        {"role": "user", "content": prompt_utilizator},
    ], chei_asteptate=["candidati"], chei_permise=set())

    candidati: list[dict[str, Any]] = []
    if isinstance(date_json, dict):
        for cand in date_json.get("candidati") or []:
            if isinstance(cand, dict):
                norm = _normalizeaza_candidat(cand, categorii)
                if norm and all(c["categorie"] != norm["categorie"] for c in candidati):
                    candidati.append(norm)

    # Citatul trebuie să existe în document; altfel încrederea scade
    for c in candidati:
        sursa = _verifica_citat_in_surse(c["citat"], surse) if c["citat"] else None
        c["citat_verificat"] = sursa is not None
        c["sursa"] = sursa or ""
        if not sursa:
            c["incredere"] *= 0.7

    # Proiect mixt: LLM-ul a dat cel puțin două categorii diferite, iar a doua e susținută de un citat
    # verificat și o încredere ≥ PRAG_CANDIDAT_SECUNDAR. Atunci nicio categorie nu e sigură (sub prag).
    secundari = [
        c for c in candidati[1:]
        if c["citat_verificat"] and c["incredere"] >= PRAG_CANDIDAT_SECUNDAR and c["categorie"] != candidati[0]["categorie"]
    ]
    proiect_mixt = bool(secundari)
    if proiect_mixt:
        for c in candidati:
            c["incredere"] = min(c["incredere"], prag - 0.05)

    # Indicii deterministe puternice
    puternice = [i for i in indicii if i["forta"] == "puternic" and i["categorie"] in categorii]
    for ind in puternice:
        existent = next((c for c in candidati if c["categorie"] == ind["categorie"]), None)
        if existent is None:
            candidati.append({
                "categorie": ind["categorie"],
                "subcategorie": ind.get("subcategorie"),
                "tip_nivel_3": None,
                "incredere": 0.6,
                "citat": "",
                "citat_verificat": False,
                "sursa": f"{ind['fisier']} (tip {ind['tip_document']})",
            })
        else:
            if existent is candidati[0] and not proiect_mixt:
                existent["incredere"] = min(0.99, existent["incredere"] + 0.1)
            if not existent["subcategorie"] and ind.get("subcategorie"):
                existent["subcategorie"] = ind["subcategorie"]
    if candidati and puternice and candidati[0]["categorie"] not in {i["categorie"] for i in puternice}:
        candidati[0]["incredere"] = min(candidati[0]["incredere"], prag - 0.05)

    candidati.sort(key=lambda c: c["incredere"], reverse=True)
    for c in candidati:
        info = categorii[c["categorie"]]
        c["incredere"] = round(c["incredere"], 2)
        c["camp_subcategorie"] = info["camp_subcategorie"]
        n3 = info["nivel_3"].get(c["subcategorie"] or "")
        c["camp_nivel_3"] = n3["camp"] if n3 else None

    ambiguu = bool(candidati) and candidati[0]["incredere"] < prag
    return {
        "proiect_mixt": proiect_mixt,
        "candidati": candidati[:2] if ambiguu else candidati[:1],
        "ambiguu": ambiguu,
        "indicii": indicii,
    }
