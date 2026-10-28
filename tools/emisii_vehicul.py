"""Tool cauta_emisii_vehicul: emisiile WLTP (gCO2/km) ale unui model, din datele EEA.

Offline: tools/data/emisii_vehicule.csv (modele sintetice din fixture-uri + eșantion EEA scris de descarca_eea.py).
Online: API-ul SQL Discodata al EEA (cu cache în tools/cache/), cu rezervă pe fișierul offline.
Potrivirea numelui e tolerantă (majuscule, spații, cratime); mai multe potriviri -> date["candidati"].
"""

from __future__ import annotations

import csv
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from contracts import StareDosar, ToolResult
from registry import tool
from tools._comun import (
    FOLDER_DATE,
    TIMEOUT_RETEA_S,
    citeste_cache,
    eroare,
    mereu_toolresult,
    mod_online,
    normalizeaza_cheie,
    nume_fisier_sigur,
    scrie_cache,
)

logger = logging.getLogger(__name__)

NUME = "cauta_emisii_vehicul"
CALE_CSV = FOLDER_DATE / "emisii_vehicule.csv"
SURSA_OFFLINE = f"EEA CO2 passenger cars (fișier offline {CALE_CSV.name})"
PREFIX_SINTETIC = "SINTETIC"


class CautaEmisiiVehiculInput(BaseModel):
    marca: str = Field(..., min_length=1, description="Marca vehiculului (ex. Dacia)")
    model: str = Field(..., min_length=1, description="Modelul / denumirea comercială (ex. Spring)")


def _citeste_offline() -> list[dict[str, Any]]:
    with open(CALE_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _citeste_online(marca: str, model: str) -> list[dict[str, Any]]:
    """Rândurile EEA ale mărcii (agregate cu aceeași logică ca descarca_eea.py)."""
    import requests

    from tools.data.descarca_eea import TABEL_IMPLICIT, URL_DISCODATA, agrega

    marca_sql = marca.replace("'", "''")
    interogare = (
        "SELECT Mk, Cn, Ft, [Ewltp (g/km)] AS Ewltp, MAX(Year) AS Year, COUNT(*) AS Nr "
        f"FROM {TABEL_IMPLICIT} WHERE UPPER(Mk) = UPPER('{marca_sql}') AND [Ewltp (g/km)] IS NOT NULL "
        "GROUP BY Mk, Cn, Ft, [Ewltp (g/km)]"
    )
    raspuns = requests.get(URL_DISCODATA, params={"query": interogare, "p": 1, "nrOfHits": 10000},
                           timeout=TIMEOUT_RETEA_S)
    raspuns.raise_for_status()
    randuri = [{"marca": r.get("Mk"), "model": r.get("Cn"), "combustibil": r.get("Ft"), "emisii": r.get("Ewltp"),
                "an": r.get("Year"), "nr": r.get("Nr")} for r in raspuns.json().get("results") or []]
    return agrega(randuri, top=10_000, sursa=f"EEA CO2 passenger cars (Discodata {TABEL_IMPLICIT})")


def _ca_numar(valoare: Any) -> Optional[float]:
    try:
        return float(valoare)
    except (TypeError, ValueError):
        return None


def _ca_intreg(valoare: Any) -> Optional[int]:
    try:
        return int(float(valoare))
    except (TypeError, ValueError):
        return None


def _format(rand: dict[str, Any]) -> dict[str, Any]:
    sursa = str(rand.get("sursa") or "")
    return {
        "marca": rand.get("marca"),
        "model": rand.get("model"),
        "emisii_wltp_gco2_km": _ca_numar(rand.get("emisii_wltp_gco2_km")),
        "combustibil": rand.get("combustibil") or None,
        "an_date": _ca_intreg(rand.get("an_date")),
        "nr_inmatriculari": _ca_intreg(rand.get("nr_inmatriculari")),
        "sintetic": sursa.startswith(PREFIX_SINTETIC),
        "sursa_rand": sursa,
    }


def potriveste(randuri: list[dict[str, Any]], marca: str, model: str) -> tuple[list[dict[str, Any]], int]:
    """(potriviri, câte modele are marca). Întâi potrivirea exactă (tolerantă), apoi cea parțială."""
    cheie_marca, cheie_model = normalizeaza_cheie(marca), normalizeaza_cheie(model)
    ale_marcii = [r for r in randuri if normalizeaza_cheie(r.get("marca")) == cheie_marca]
    exacte = [r for r in ale_marcii if normalizeaza_cheie(r.get("model")) == cheie_model]
    if exacte:
        return exacte, len(ale_marcii)
    partiale = [
        r for r in ale_marcii
        if cheie_model and (cheie_model in normalizeaza_cheie(r.get("model")) or normalizeaza_cheie(r.get("model")) in cheie_model)
        and normalizeaza_cheie(r.get("model"))
    ]
    return partiale, len(ale_marcii)


def _rezultat(randuri: list[dict[str, Any]], marca: str, model: str, sursa: str) -> ToolResult:
    potriviri, nr_marca = potriveste(randuri, marca, model)
    if not potriviri:
        detaliu = (f"marca are {nr_marca} modele în date" if nr_marca else "marca nu există în date")
        return eroare(NUME, f"Modelul {marca} {model} nu a fost găsit în datele EEA ({detaliu}).", sursa)

    candidati = [_format(r) for r in potriviri]
    if len(candidati) == 1:
        c = candidati[0]
        return ToolResult(tool=NUME, gasit=True, sursa=sursa, date={
            "emisii_wltp_gco2_km": c["emisii_wltp_gco2_km"], "combustibil": c["combustibil"], "an_date": c["an_date"],
            "marca": c["marca"], "model": c["model"], "sintetic": c["sintetic"], "candidati": candidati,
        })
    # Mai multe modele se potrivesc: agentul alege (ex. după combustibil) sau cere precizări
    return ToolResult(tool=NUME, gasit=True, sursa=sursa, date={
        "emisii_wltp_gco2_km": None, "combustibil": None, "an_date": None,
        "ambiguu": True, "candidati": candidati,
    })


@tool(
    nume=NUME,
    descriere=(
        "Emisiile WLTP (gCO2/km) ale unui model de autoturism, din datele EEA. "
        "Dacă se potrivesc mai multe modele, le întoarce în date['candidati']."
    ),
    model_intrare=CautaEmisiiVehiculInput,
)
@mereu_toolresult(NUME, CautaEmisiiVehiculInput)
def cauta_emisii_vehicul(intrare: CautaEmisiiVehiculInput, stare: StareDosar) -> ToolResult:
    """{"emisii_wltp_gco2_km", "combustibil", "an_date"} pentru (marca, model)."""
    marca, model = intrare.marca.strip(), intrare.model.strip()
    if not marca or not model:
        return eroare(NUME, "Marca și modelul sunt obligatorii.")

    if not mod_online():
        return _rezultat(_citeste_offline(), marca, model, SURSA_OFFLINE)

    cheie_cache = f"eea_{nume_fisier_sigur(normalizeaza_cheie(marca))}.json"
    try:
        randuri = _citeste_online(marca, model)
        scrie_cache(cheie_cache, randuri)
        sursa = randuri[0]["sursa"] if randuri else "EEA CO2 passenger cars (Discodata)"
        rezultat = _rezultat(randuri, marca, model, sursa)
        if rezultat.gasit:
            return rezultat
    except Exception as exc:
        logger.warning("EEA Discodata indisponibil (%s); se folosește cache-ul sau fișierul offline.", exc)
        din_cache = citeste_cache(cheie_cache)
        if din_cache:
            return _rezultat(din_cache, marca, model, "EEA CO2 passenger cars (cache local, sursa online indisponibilă)")
        rezultat = _rezultat(_citeste_offline(), marca, model, SURSA_OFFLINE)
        rezultat.sursa = f"{rezultat.sursa}; sursa online indisponibilă ({type(exc).__name__})"
        return rezultat
    # Online fără rezultat (ex. modelele sintetice nu sunt în EEA): se încearcă și fișierul offline
    return _rezultat(_citeste_offline(), marca, model, SURSA_OFFLINE)
