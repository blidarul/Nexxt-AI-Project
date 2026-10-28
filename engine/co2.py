"""Calculul economiei de CO2 conform metodologiei RBI."""

from __future__ import annotations

import logging
from pydantic import BaseModel

from contracts import StareDosar, ToolResult
from registry import tool

logger = logging.getLogger(__name__)

BASELINE_KWH_M2 = 297
FACTOR_EMISIE_KGCO2_KWH = 0.25


class CalculeazaCO2Input(BaseModel):
    pass


@tool(
    nume="calculeaza_co2",
    descriere="Calculează economia de emisii CO2 (tCO2/an) conform formulei RBI.",
    model_intrare=CalculeazaCO2Input,
)
def calculeaza_co2(intrare: CalculeazaCO2Input, stare: StareDosar) -> ToolResult:
    """Calculează CO2 evitat pentru clădiri finalizate cu date energetice."""
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
        energie_finala = float(stare.extras.epc_energie_finala.valoare)
        suprafata = float(stare.extras.suprafata_m2.valoare or 0)
        cota_banca = float(stare.extras.cota_banca.valoare or 1.0)

        dif_consum = BASELINE_KWH_M2 - energie_finala
        kwh_total = dif_consum * suprafata
        kwh_banca = kwh_total * cota_banca
        kg_co2 = kwh_banca * FACTOR_EMISIE_KGCO2_KWH
        tco2_an = round(kg_co2 / 1000.0, 1)

        def f_num(val: float) -> str:
            return f"{int(val):,}".replace(",", ".")

        pasi = [
            f"1. Diferenta consum: {BASELINE_KWH_M2} - {int(energie_finala)} = {int(dif_consum)} kWh/m2/an",
            f"2. x suprafata: {int(dif_consum)} x {int(suprafata)} = {f_num(kwh_total)} kWh/an",
            f"3. x cota banca: {f_num(kwh_total)} x {cota_banca} = {f_num(kwh_banca)} kWh/an",
            f"4. x factor emisie: {f_num(kwh_banca)} x {FACTOR_EMISIE_KGCO2_KWH} = {f_num(kg_co2)} kgCO2/an",
        ]

        impact_data = {
            "formula": "(baseline - energie_finala) x suprafata x cota_banca x factor_emisie",
            "sursa": "Allocation & Impact Report 2025, p. 22",
            "pasi": pasi,
            "rezultat_tco2_an": tco2_an,
            "atentie": "Factorul de emisie e valoare EXEMPLU (vezi reference/factori_referinta.yaml).",
        }

        stare.impact = impact_data
        logger.info("Impact CO2 calculat: %.1f tCO2/an", tco2_an)

        return ToolResult(
            tool="calculeaza_co2",
            gasit=True,
            date=impact_data,
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
