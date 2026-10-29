"""Tool factor_emisie_tara: intensitatea carbon a electricității pentru o țară (kgCO2e/kWh), ca PROXY.

RBI folosește Enerdata (plătit). Aici: Ember prin Our World in Data.
Offline: tools/data/intensitate_carbon.csv (scris de tools/data/descarca_ember.py).
Online: CSV-ul OWID proaspăt (păstrat în tools/cache/), cu rezervă pe fișierul offline.
"""

from __future__ import annotations

import csv
import logging
from typing import Optional

from pydantic import BaseModel, Field

from contracts import StareDosar, ToolResult
from registry import tool
from tools._comun import FOLDER_DATE, citeste_cache, eroare, mereu_toolresult, mod_online, scrie_cache
from tools.tari import corespondenta_tari, gaseste_tara, tari_anexa_b

logger = logging.getLogger(__name__)

NUME = "factor_emisie_tara"
CALE_CSV = FOLDER_DATE / "intensitate_carbon.csv"
CHEIE_CACHE = "intensitate_carbon_owid.json"
TIP = "proxy"


class FactorEmisieTaraInput(BaseModel):
    tara: str = Field(..., min_length=1, description="Țara, în română sau engleză (ex. România / Romania) sau cod ISO3")
    an: Optional[int] = Field(None, ge=1990, le=2100, description="Anul; fără an se folosește ultimul an disponibil")


def _serie_offline(iso3: str) -> tuple[dict[int, float], str]:
    serie, sursa = {}, ""
    with open(CALE_CSV, encoding="utf-8", newline="") as f:
        for rand in csv.DictReader(f):
            if rand["iso3"] == iso3:
                serie[int(rand["an"])] = float(rand["gco2e_kwh"])
                sursa = rand["sursa"]
    return serie, f"{sursa} (fișier offline {CALE_CSV.name})"


def _serie_online(iso3: str) -> tuple[dict[int, float], str]:
    from tools.data.descarca_ember import SURSA, descarca, filtreaza

    try:
        coduri = {info["iso3"]: info["en"] for info in corespondenta_tari().values()}
        randuri = filtreaza(descarca(), coduri)
        scrie_cache(CHEIE_CACHE, randuri)
        sursa = SURSA
    except (SystemExit, Exception) as exc:  # descarca() semnalează rețeaua cu SystemExit
        logger.warning("OWID indisponibil (%s); se folosește cache-ul sau fișierul offline.", exc)
        randuri = citeste_cache(CHEIE_CACHE)
        if randuri is None:
            serie, sursa = _serie_offline(iso3)
            return serie, f"{sursa}; sursa online indisponibilă"
        sursa = f"{SURSA} (cache local, sursa online indisponibilă)"
    return {int(r["an"]): float(r["gco2e_kwh"]) for r in randuri if r["iso3"] == iso3}, sursa


@tool(
    nume=NUME,
    descriere=(
        "Factorul de emisie al rețelei electrice pentru o țară (kgCO2e/kWh), pentru calculul impactului. "
        "Valoare PROXY (Ember / Our World in Data), nu Enerdata. Fără an: ultimul an disponibil."
    ),
    model_intrare=FactorEmisieTaraInput,
)
@mereu_toolresult(NUME, FactorEmisieTaraInput)
def factor_emisie_tara(intrare: FactorEmisieTaraInput, stare: StareDosar) -> ToolResult:
    """Intensitatea carbon a electricității: {"kgco2_kwh", "an", "tip": "proxy"}."""
    tara = gaseste_tara(intrare.tara)
    if tara is None:
        return eroare(NUME, f"Țară necunoscută: {intrare.tara!r}. Țări acceptate (Anexa B): {', '.join(tari_anexa_b())}.", tehnica=True)

    serie, sursa = _serie_online(tara["iso3"]) if mod_online() else _serie_offline(tara["iso3"])
    if not serie:
        return eroare(NUME, f"Nu există date de intensitate carbon pentru {tara['en']}.", sursa)

    ani = sorted(serie)
    if intrare.an is None:
        an = ani[-1]
    else:
        # anul cerut sau, dacă nu e încă publicat, cel mai recent an anterior
        anteriori = [a for a in ani if a <= intrare.an]
        if not anteriori:
            return eroare(NUME, f"Nu există date pentru {tara['en']} în {intrare.an} sau înainte "
                                f"(disponibil: {ani[0]}-{ani[-1]}).", sursa, {"ani_disponibili": [ani[0], ani[-1]]})
        an = anteriori[-1]

    gco2e = serie[an]
    return ToolResult(
        tool=NUME,
        gasit=True,
        date={
            "kgco2_kwh": round(gco2e / 1000, 6),
            "an": an,
            "tip": TIP,
            "gco2e_kwh": gco2e,
            "an_cerut": intrare.an,
            "tara": tara["nume_ro"],
            "iso3": tara["iso3"],
            "in_anexa_b": tara["anexa_b"],
            "nota": "Proxy public (Ember via Our World in Data); RBI folosește Enerdata.",
        },
        sursa=sursa,
    )
