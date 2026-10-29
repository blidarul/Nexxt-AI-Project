"""Calculul economiei de CO2 conform metodologiei RBI."""

from __future__ import annotations

import logging
from pydantic import BaseModel

from contracts import StareDosar, ToolResult
from engine.impact import calculeaza_impact_categorie
from registry import tool

logger = logging.getLogger(__name__)


class CalculeazaCO2Input(BaseModel):
    pass


@tool(
    nume="calculeaza_co2",
    descriere="Calculează economia de emisii CO2 (tCO2/an) conform formulei RBI.",
    model_intrare=CalculeazaCO2Input,
)
def calculeaza_co2(intrare: CalculeazaCO2Input, stare: StareDosar) -> ToolResult:
    """Calculează CO2 evitat pentru clădiri finalizate delegând către motorul de impact."""
    stadiu = str(stare.extras.stadiu_cladire.valoare or "").lower()
    if "construc" in stadiu:
        return ToolResult(
            tool="calculeaza_co2",
            gasit=False,
            eroare="Nu se calculează impactul pentru clădiri în construcție (Impact Report p. 18).",
            sursa="Allocation & Impact Report 2025, p. 18",
        )

    if not stare.extras.epc_energie_finala or stare.extras.epc_energie_finala.valoare is None:
        return ToolResult(
            tool="calculeaza_co2",
            gasit=False,
            eroare="Lipsă valoare consum energie finală (EPC).",
            sursa="Allocation & Impact Report 2025, p. 22",
        )

    try:
        impact_data = calculeaza_impact_categorie("green_buildings", stare)
        rezultat = impact_data.get("rezultat_tco2_an")
        if rezultat is not None:
            logger.info("Impact CO2 calculat: %.1f tCO2/an", rezultat)
            return ToolResult(
                tool="calculeaza_co2",
                gasit=True,
                date=impact_data,
                sursa="Allocation & Impact Report 2025, p. 22",
            )

        pasi_err = "; ".join(impact_data.get("pasi", [])) or "Nu s-a putut calcula impactul."
        return ToolResult(
            tool="calculeaza_co2",
            gasit=False,
            eroare=pasi_err,
            sursa="Allocation & Impact Report 2025, p. 22",
        )
    except Exception as exc:
        err_msg = f"Eroare la calculul CO2: {exc}"
        logger.exception(err_msg)
        return ToolResult(
            tool="calculeaza_co2",
            gasit=False,
            eroare=err_msg,
            sursa="Allocation & Impact Report 2025, p. 22",
        )
