"""Unelte de acțiune și flux pentru agent (stabilire categorie, completitudine, comunicare, escaladare)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from contracts import StareDosar, ToolResult
from engine.evaluator_generic import obtine_valoare_camp
from registry import tool

logger = logging.getLogger(__name__)

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


# ---------------------------------------------------------------------------
# Modele de intrare pentru unelte
# ---------------------------------------------------------------------------

class CereDateClientInput(BaseModel):
    ce_lipseste: str = Field(..., description="Descrierea datelor sau documentelor lipsă")
    motiv: str = Field(default="", description="Motivul pentru care datele sunt necesare")


class EscaladeazaInput(BaseModel):
    motiv: str = Field(..., description="Motivul escaladării către Sustainability Bond Committee")


class StabilesteCategoriaInput(BaseModel):
    motivare: str = Field(default="", description="Motivarea alegerii categoriei în caz de ambiguitate sau candidați apropiați")


class VerificaCompletitudineInput(BaseModel):
    categorie: str = Field(default="", description="Categoria pentru care se verifică cerințele din cerinte_dosar.yaml")


# ---------------------------------------------------------------------------
# Unelte înregistrate în Registry
# ---------------------------------------------------------------------------

@tool(
    nume="cere_date_client",
    descriere="Solicită date sau clarificări suplimentare de la client când lipsesc documente sau informații necesare.",
    model_intrare=CereDateClientInput,
)
def cere_date_client(intrare: CereDateClientInput, stare: StareDosar) -> ToolResult:
    """Adaugă o solicitare de informații către client în acțiunile dosarului."""
    if intrare.motiv:
        text_actiune = f"{intrare.ce_lipseste} (motiv: {intrare.motiv})"
    else:
        text_actiune = intrare.ce_lipseste

    if text_actiune not in stare.actiuni:
        stare.actiuni.append(text_actiune)
    logger.info("Acțiune cerere date adăugată: %s", text_actiune)

    return ToolResult(
        tool="cere_date_client",
        gasit=True,
        date={"ce_lipseste": intrare.ce_lipseste, "motiv": intrare.motiv},
        sursa="agent.actiuni",
    )


@tool(
    nume="escaladeaza",
    descriere="Escaladează dosarul către Sustainability Bond Committee din cauza unui semnal de risc sau ambiguitate.",
    model_intrare=EscaladeazaInput,
)
def escaladeaza(intrare: EscaladeazaInput, stare: StareDosar) -> ToolResult:
    """Marchează dosarul ca escaladat și adaugă motivul în acțiunile dosarului."""
    stare.escaladat = True
    if intrare.motiv not in stare.actiuni:
        stare.actiuni.append(intrare.motiv)
    logger.warning("Dosar escaladat: %s", intrare.motiv)

    return ToolResult(
        tool="escaladeaza",
        gasit=True,
        date={"escaladat": True, "motiv": intrare.motiv},
        sursa="agent.actiuni",
    )


@tool(
    nume="stabileste_categoria",
    descriere="Stabilește categoria și subcategoria proiectului folosind extras.categorie și raportul de extracție.",
    model_intrare=StabilesteCategoriaInput,
)
def stabileste_categoria(intrare: StabilesteCategoriaInput, stare: StareDosar) -> ToolResult:
    """Stabilește categoria verde a dosarului.
    
    Nu reclasifică de la zero: folosește extras.categorie.
    Dacă raport_extractie.categorie_candidati are 2 candidați cu încredere sub 0.7,
    semnalează ambiguitatea pentru ca agentul să aleagă motivat sau să escaladeze.
    """
    extras = stare.extras
    cat_raw = extras.categorie.valoare if extras.categorie else None
    subcat_raw = extras.subcategorie.valoare if extras.subcategorie else None

    raport = stare.raport_extractie or {}
    candidati = raport.get("categorie_candidati") or raport.get("candidati") or []

    incredere = 1.0
    if extras.categorie and hasattr(extras.categorie, "incredere") and extras.categorie.incredere is not None:
        incredere = float(extras.categorie.incredere)

    # Identificăm candidații cu încredere sub 0.7
    candidati_slabi = [c for c in candidati if isinstance(c, dict) and float(c.get("incredere", 1.0)) < 0.7]
    ambiguu = len(candidati_slabi) >= 2 or (incredere < 0.7 and len(candidati) > 1)

    cat_final = str(cat_raw or (candidati[0].get("categorie") if candidati else "green_buildings")).strip().lower()
    subcat_final = str(subcat_raw or (candidati[0].get("subcategorie") if candidati and "subcategorie" in candidati[0] else "")).strip().lower()

    # Motivare automată dacă nu este furnizată una explicită
    if intrare.motivare:
        motivare = intrare.motivare
    elif ambiguu:
        motivare = (
            f"Ambiguitate detectată între candidați ({[c.get('categorie') for c in candidati if isinstance(c, dict)]}). "
            f"Selectat '{cat_final}' conform descrierii proiectului și documentelor primare."
        )
    else:
        motivare = f"Categorie stabilită din extracție: {cat_final}"

    rezultat_date = {
        "categorie": cat_final,
        "subcategorie": subcat_final,
        "incredere": incredere,
        "candidati": candidati,
        "ambiguu": ambiguu,
        "motivare": motivare,
    }

    logger.info("Categorie stabilită: %s (subcat: %s, ambiguu: %s)", cat_final, subcat_final, ambiguu)

    return ToolResult(
        tool="stabileste_categoria",
        gasit=True,
        date=rezultat_date,
        sursa="extras.categorie / raport_extractie",
    )


@tool(
    nume="verifica_completitudine",
    descriere="Verifică completitudinea dosarului conform rules/cerinte_dosar.yaml și raport_extractie.",
    model_intrare=VerificaCompletitudineInput,
)
def verifica_completitudine(intrare: VerificaCompletitudineInput, stare: StareDosar) -> ToolResult:
    """Compară ce s-a extras cu cerinte_dosar.yaml și identifică lipsurile exacte."""
    cerinte_path = RULES_DIR / "cerinte_dosar.yaml"
    cerinte: dict = {}
    if cerinte_path.exists():
        with open(cerinte_path, "r", encoding="utf-8") as f:
            cerinte = yaml.safe_load(f) or {}

    cat = intrare.categorie or (stare.extras.categorie and stare.extras.categorie.valoare) or "green_buildings"
    cat_str = str(cat).strip().lower()

    map_cat = {
        "cladiri": "green_buildings",
        "transport": "clean_transportation",
        "regenerabile": "renewable_energy",
        "eficienta": "energy_efficiency",
        "poluare": "pollution_prevention",
        "circular": "circular_economy",
    }
    cat_key = map_cat.get(cat_str, cat_str)

    raport = stare.raport_extractie or {}
    docs_lipsa = list(raport.get("documente_lipsa", []))
    camps_lipsa = list(raport.get("campuri_lipsa", []))

    lipsuri: list[dict[str, Any]] = []

    # 1. Verificare cerințe comune
    comun = cerinte.get("comun", {})
    for doc in comun.get("documente", []):
        if doc.get("obligatoriu") is True:
            doc_id = doc.get("id")
            doc_nume = doc.get("nume")
            if doc_id in docs_lipsa or doc_nume in docs_lipsa:
                lipsuri.append({
                    "tip": "document",
                    "id": doc_id,
                    "nume": doc_nume,
                    "regula": "conditii_generale",
                    "mesaj": f"Lipsește documentul obligatoriu {doc_id} ({doc_nume}).",
                })

    for camp_info in comun.get("campuri", []):
        c_nume = camp_info.get("camp")
        pentru = camp_info.get("pentru", [])
        if camp_info.get("obligatoriu", True) is not False:
            val, _ = obtine_valoare_camp(stare, c_nume)
            if val is None or c_nume in camps_lipsa:
                # Nu semnalăm dacă este un câmp comun opțional pentru anumite categorii
                if c_nume in ("cui", "tara", "data_aprobare"):
                    doc_asoc = camp_info.get("document", [])
                    reg_str = ", ".join(str(x) for x in pentru)
                    lipsuri.append({
                        "tip": "camp",
                        "camp": c_nume,
                        "document": doc_asoc,
                        "regula": reg_str,
                        "mesaj": f"Lipsește câmpul obligatoriu '{c_nume}' ({doc_asoc}), necesar pentru {reg_str}.",
                    })

    # 2. Verificare cerințe specifice categoriei
    cat_cerinte = cerinte.get(cat_key, {})
    subcat_val, _ = obtine_valoare_camp(stare, "subcategorie")
    subcat_str = str(subcat_val or "").strip().lower()

    sectiune = None
    if subcat_str and isinstance(cat_cerinte, dict) and subcat_str in cat_cerinte:
        sectiune = cat_cerinte[subcat_str]
    elif isinstance(cat_cerinte, dict):
        if "documente" in cat_cerinte or "campuri" in cat_cerinte:
            sectiune = cat_cerinte
        else:
            # Luăm prima subcategorie definită ca referință
            for v in cat_cerinte.values():
                if isinstance(v, dict) and ("documente" in v or "campuri" in v):
                    sectiune = v
                    break

    if isinstance(sectiune, dict):
        # Documente categorie
        for doc in sectiune.get("documente", []):
            doc_id = doc.get("id")
            doc_nume = doc.get("nume")
            ob = doc.get("obligatoriu")
            if ob is True and (doc_id in docs_lipsa or doc_nume in docs_lipsa):
                lipsuri.append({
                    "tip": "document",
                    "id": doc_id,
                    "nume": doc_nume,
                    "regula": cat_key,
                    "mesaj": f"Lipsește documentul {doc_id} ({doc_nume}) necesar pentru {cat_key}.",
                })

        # Câmpuri categorie
        # Dacă raport_extractie conține explicit campuri_lipsa, le raportăm pe acelea
        if camps_lipsa:
            for camp_info in sectiune.get("campuri", []):
                c_nume = camp_info.get("camp")
                if c_nume in camps_lipsa:
                    doc_asoc = camp_info.get("document", [])
                    pentru = camp_info.get("pentru", [])
                    reg_str = ", ".join(str(x) for x in pentru)
                    lipsuri.append({
                        "tip": "camp",
                        "camp": c_nume,
                        "document": doc_asoc,
                        "regula": reg_str,
                        "mesaj": f"Lipsește câmpul '{c_nume}' ({doc_asoc}), necesar pentru {reg_str}.",
                    })
        else:
            # Fără campuri_lipsa raportate explicit: verificăm doar dacă nicio cale alternativă nu are date
            has_certificat = bool(getattr(stare.extras, "nr_certificat_declarat", None) and stare.extras.nr_certificat_declarat.valoare)
            has_epc = bool(getattr(stare.extras, "epc_clasa", None) and stare.extras.epc_clasa.valoare)
            
            for camp_info in sectiune.get("campuri", []):
                c_nume = camp_info.get("camp")
                pentru = camp_info.get("pentru", [])
                val, _ = obtine_valoare_camp(stare, c_nume)
                if val is None:
                    # Dacă avem cale de certificat, câmpurile BREEAM se iau din registru, iar câmpurile EPC nu sunt obligatorii
                    if has_certificat and (c_nume.startswith("certificare_") or c_nume in ("ped_kwh_m2", "epc_clasa", "energie_finala_kwh_m2")):
                        continue
                    if has_epc and c_nume.startswith("certificare_"):
                        continue
                    doc_asoc = camp_info.get("document", [])
                    reg_str = ", ".join(str(x) for x in pentru)
                    lipsuri.append({
                        "tip": "camp",
                        "camp": c_nume,
                        "document": doc_asoc,
                        "regula": reg_str,
                        "mesaj": f"Lipsește câmpul '{c_nume}' ({doc_asoc}), necesar pentru {reg_str}.",
                    })

    complet = len(lipsuri) == 0

    return ToolResult(
        tool="verifica_completitudine",
        gasit=True,
        date={
            "complet": complet,
            "nr_lipsuri": len(lipsuri),
            "lipsuri": lipsuri,
            "documente_lipsa": docs_lipsa,
            "campuri_lipsa": camps_lipsa,
        },
        sursa="rules/cerinte_dosar.yaml",
    )
