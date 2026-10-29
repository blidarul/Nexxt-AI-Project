"""Evaluarea regulilor de eligibilitate pentru orice categorie și condiții generale."""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from contracts import RezultatRegula, StareDosar, ToolResult
from engine.evaluator_generic import (
    evalueaza_fisier_reguli,
    evalueaza_regula,
    incarca_reguli_yaml,
)
from engine.impact import calculeaza_impact_categorie
from engine.plauzibilitate import evalueaza_plauzibilitate
from registry import tool

logger = logging.getLogger(__name__)

# Prefixe CAEN de referință (pentru compatibilitate directă)
PREFIXE_CAEN_EXCLUSE_GENERAL = [
    "254", "304", "2446", "05", "06", "0910", "19", "352",
    "07", "08", "099", "1101", "1102", "1103", "1104", "1105", "12", "92",
]
PREFIXE_CAEN_SEMNAL_GENERAL = ["3511"]
PREFIXE_CAEN_SEMNAL_CHIRIASI = ["0510", "0520", "0610", "0620", "0910", "1910", "1920"]

TARI_ELIGIBILE = {
    "austria", "belgia", "bulgaria", "croatia", "cipru", "cehia", "danemarca", "estonia",
    "finlanda", "franta", "germania", "grecia", "ungaria", "irlanda", "italia", "letonia",
    "lituania", "luxemburg", "malta", "olanda", "polonia", "portugalia", "romania", "românia",
    "slovacia", "slovenia", "spania", "suedia",
    "albania", "bosnia si hertegovina", "kosovo", "serbia", "ucraina",
    "china", "india", "japonia", "regatul unit", "statele unite", "brazilia",
}


# ---------------------------------------------------------------------------
# Modele de intrare pentru Tools
# ---------------------------------------------------------------------------

class ConditiiGeneraleInput(BaseModel):
    pass


class EvalueazaCaleInput(BaseModel):
    cale_id: str = Field(..., description="Identificatorul căii (ex: GB-01, GB-02, GB-03, GB-04)")


class VerificaChiriasiInput(BaseModel):
    pass


class EvalueazaCategoriaInput(BaseModel):
    categorie: str = Field(default="", description="Numele categoriei (ex: green_buildings, clean_transportation, renewable_energy)")


class VerificaPlauzibilitateInput(BaseModel):
    pass


class CalculeazaImpactInput(BaseModel):
    categorie: str = Field(default="", description="Categoria de finanțare verde (ex: green_buildings, clean_transportation)")


# ---------------------------------------------------------------------------
# Unelte înregistrate în Registry
# ---------------------------------------------------------------------------

@tool(
    nume="evalueaza_conditii_generale",
    descriere="Evaluează condițiile generale (G-01, G-02, G-03, G-04, G-05) din conditii_generale.yaml.",
    model_intrare=ConditiiGeneraleInput,
)
def evalueaza_conditii_generale(intrare: ConditiiGeneraleInput, stare: StareDosar) -> ToolResult:
    """Evaluează condițiile generale aplicabile tuturor dosarelor."""
    try:
        rezultate = evalueaza_fisier_reguli("conditii_generale", stare)
        rezumat = {r.regula_id: r.rezultat for r in rezultate}
        return ToolResult(
            tool="evalueaza_conditii_generale",
            gasit=True,
            date={"rezultate": rezumat},
            sursa="rules/conditii_generale.yaml",
        )
    except Exception as exc:
        logger.exception("Eroare la evaluarea condițiilor generale: %s", exc)
        return ToolResult(
            tool="evalueaza_conditii_generale",
            gasit=False,
            eroare=str(exc),
            sursa="rules/conditii_generale.yaml",
        )


@tool(
    nume="evalueaza_categoria",
    descriere="Evaluează toate regulile din rules/<categorie>.yaml pentru categoria proiectului.",
    model_intrare=EvalueazaCategoriaInput,
)
def evalueaza_categoria(intrare: EvalueazaCategoriaInput, stare: StareDosar) -> ToolResult:
    """Evaluează regulile specifice categoriei dosarului."""
    cat = intrare.categorie or (stare.extras.categorie and stare.extras.categorie.valoare) or "green_buildings"
    cat_str = str(cat).strip().lower()

    # Normalizări pentru denumiri alternative
    map_cat = {
        "cladiri": "green_buildings",
        "cladiri_verzi": "green_buildings",
        "transport": "clean_transportation",
        "transport_curat": "clean_transportation",
        "regenerabile": "renewable_energy",
        "energie_regenerabila": "renewable_energy",
        "eficienta": "energy_efficiency",
        "eficienta_energetica": "energy_efficiency",
        "poluare": "pollution_prevention",
        "prevenirea_poluarii": "pollution_prevention",
        "circular": "circular_economy",
        "economie_circulara": "circular_economy",
    }
    fisier = map_cat.get(cat_str, cat_str)

    try:
        rezultate = evalueaza_fisier_reguli(fisier, stare)
        rezumat = {r.regula_id: r.rezultat for r in rezultate}
        return ToolResult(
            tool="evalueaza_categoria",
            gasit=True,
            date={"categorie": fisier, "rezultate": rezumat},
            sursa=f"rules/{fisier}.yaml",
        )
    except Exception as exc:
        logger.exception("Eroare la evaluarea categoriei %s: %s", fisier, exc)
        return ToolResult(
            tool="evalueaza_categoria",
            gasit=False,
            eroare=str(exc),
            sursa=f"rules/{fisier}.yaml",
        )


@tool(
    nume="verifica_plauzibilitate",
    descriere="Verifică cifrele de energie și emisii conform reference/plauzibilitate.yaml.",
    model_intrare=VerificaPlauzibilitateInput,
)
def verifica_plauzibilitate(intrare: VerificaPlauzibilitateInput, stare: StareDosar) -> ToolResult:
    """Evaluează regulile de plauzibilitate anti-greenwashing."""
    try:
        rezultate = evalueaza_plauzibilitate(stare)
        rezumat = {r.regula_id: r.rezultat for r in rezultate}
        return ToolResult(
            tool="verifica_plauzibilitate",
            gasit=True,
            date={"verificari": rezumat, "nr_semnale": sum(1 for r in rezultate if r.rezultat == "SEMNAL")},
            sursa="reference/plauzibilitate.yaml",
        )
    except Exception as exc:
        logger.exception("Eroare la verificarea plauzibilității: %s", exc)
        return ToolResult(
            tool="verifica_plauzibilitate",
            gasit=False,
            eroare=str(exc),
            sursa="reference/plauzibilitate.yaml",
        )


@tool(
    nume="calculeaza_impact",
    descriere="Calculează impactul de mediu (CO2 evitat, energie) pe categoria dosarului conform metodologiei RBI.",
    model_intrare=CalculeazaImpactInput,
)
def calculeaza_impact(intrare: CalculeazaImpactInput, stare: StareDosar) -> ToolResult:
    """Calculează impactul pe categoria specificată."""
    cat = intrare.categorie or (stare.extras.categorie and stare.extras.categorie.valoare) or "green_buildings"
    cat_str = str(cat).strip().lower()

    map_cat = {
        "cladiri": "green_buildings",
        "cladiri_verzi": "green_buildings",
        "transport": "clean_transportation",
        "regenerabile": "renewable_energy",
        "eficienta": "energy_efficiency",
        "poluare": "pollution_prevention",
        "circular": "circular_economy",
    }
    fisier = map_cat.get(cat_str, cat_str)

    try:
        impact_data = calculeaza_impact_categorie(fisier, stare)
        tco2 = impact_data.get("rezultat_tco2_an")
        return ToolResult(
            tool="calculeaza_impact",
            gasit=True,
            date=impact_data,
            sursa=impact_data.get("sursa", "reference/metodologie_impact.yaml"),
        )
    except Exception as exc:
        logger.exception("Eroare la calculul impactului: %s", exc)
        return ToolResult(
            tool="calculeaza_impact",
            gasit=False,
            eroare=str(exc),
            sursa="reference/metodologie_impact.yaml",
        )


# ---------------------------------------------------------------------------
# Tools compatibile legacy (evalueaza_cale, verifica_chiriasi)
# ---------------------------------------------------------------------------

@tool(
    nume="evalueaza_cale",
    descriere="Evaluează o cale specifică de eligibilitate din green_buildings.yaml.",
    model_intrare=EvalueazaCaleInput,
)
def evalueaza_cale(intrare: EvalueazaCaleInput, stare: StareDosar) -> ToolResult:
    """Evaluează o cale specifică (GB-01, GB-02, GB-03, GB-04, GB-R1 etc.)."""
    cale_id = intrare.cale_id.strip()
    data_gb = incarca_reguli_yaml("green_buildings")

    def cauta_regula(obj: Any) -> Optional[dict]:
        if isinstance(obj, dict):
            if obj.get("id") == cale_id:
                return obj
            for v in obj.values():
                gasit = cauta_regula(v)
                if gasit:
                    return gasit
        elif isinstance(obj, list):
            for elem in obj:
                gasit = cauta_regula(elem)
                if gasit:
                    return gasit
        return None

    def_regula = cauta_regula(data_gb)
    if not def_regula:
        res = RezultatRegula(
            regula_id=cale_id,
            rezultat="NEEVALUABIL",
            dovada=f"Calea {cale_id} nu a fost găsită în green_buildings.yaml",
            sursa_framework="rules/green_buildings.yaml",
        )
        stare.reguli[cale_id] = res
        return ToolResult(tool="evalueaza_cale", gasit=False, eroare=f"Calea {cale_id} negăsită")

    res = evalueaza_regula(def_regula, stare)
    if res:
        stare.reguli[cale_id] = res
        return ToolResult(
            tool="evalueaza_cale",
            gasit=True,
            date={"cale_id": cale_id, "rezultat": res.rezultat, "dovada": res.dovada},
            sursa=res.sursa_framework,
        )

    return ToolResult(tool="evalueaza_cale", gasit=False, eroare="Regula nu s-a aplicat")


@tool(
    nume="verifica_chiriasi",
    descriere="Verifică activitățile chiriașilor împotriva criteriilor de excludere (GB-X1).",
    model_intrare=VerificaChiriasiInput,
)
def verifica_chiriasi(intrare: VerificaChiriasiInput, stare: StareDosar) -> ToolResult:
    """Verifică codurile CAEN ale chiriașilor."""
    data_gb = incarca_reguli_yaml("green_buildings")
    excl = next((x for x in data_gb.get("excluderi", []) if x.get("id") == "GB-X1"), None)
    if excl:
        res = evalueaza_regula(excl, stare)
        if res:
            stare.reguli["GB-X1"] = res
            return ToolResult(
                tool="verifica_chiriasi",
                gasit=True,
                date={"rezultat": res.rezultat, "dovada": res.dovada},
                sursa=res.sursa_framework,
            )

    return ToolResult(tool="verifica_chiriasi", gasit=True, date={"rezultat": "OK"})
