"""Tool verifica_firma: extrage date despre firma din ANAF."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Union

from pydantic import BaseModel, Field

from contracts import StareDosar, ToolResult
from registry import tool

logger = logging.getLogger(__name__)


class VerificaFirmaInput(BaseModel):
    cui: Union[str, int] = Field(..., description="Codul Unic de Înregistrare (CUI)")


@tool(
    nume="verifica_firma",
    descriere="Verifică starea firmei și codul CAEN în registrul ANAF.",
    model_intrare=VerificaFirmaInput,
)
def verifica_firma(intrare: VerificaFirmaInput, stare: StareDosar) -> ToolResult:
    """Interoghează ANAF (offline din 05_raspuns_anaf.json)."""
    cale = Path(stare.dosar_folder) / "05_raspuns_anaf.json"
    if not cale.exists():
        return ToolResult(
            tool="verifica_firma",
            gasit=False,
            eroare=f"Fișierul {cale} nu există.",
            sursa="ANAF API v9 (cache offline)",
        )

    try:
        with open(cale, "r", encoding="utf-8") as f:
            date = json.load(f)

        found = date.get("found", [])
        if found:
            date_generale = found[0].get("date_generale", {})
            stare_inactiv = found[0].get("stare_inactiv", {})
            return ToolResult(
                tool="verifica_firma",
                gasit=True,
                date={"date_generale": date_generale, "stare_inactiv": stare_inactiv},
                sursa="ANAF API v9 (cache offline)",
            )
        else:
            return ToolResult(
                tool="verifica_firma",
                gasit=False,
                eroare=f"CUI-ul {intrare.cui} nu a fost găsit în răspunsul ANAF.",
                sursa="ANAF API v9 (cache offline)",
            )
    except Exception as exc:
        return ToolResult(
            tool="verifica_firma",
            gasit=False,
            eroare=f"Eroare la citirea datelor ANAF: {exc}",
            sursa="ANAF API v9 (cache offline)",
        )
