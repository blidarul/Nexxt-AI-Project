"""Tool cauta_certificat: caută certificatul în registrul public BREEAM."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from contracts import StareDosar, ToolResult
from registry import tool

logger = logging.getLogger(__name__)


class CautaCertificatInput(BaseModel):
    nr_certificat: str = Field(..., description="Numărul certificatului BREEAM")


@tool(
    nume="cauta_certificat",
    descriere="Caută certificatul în registrul BREEAM.",
    model_intrare=CautaCertificatInput,
)
def cauta_certificat(intrare: CautaCertificatInput, stare: StareDosar) -> ToolResult:
    """Caută certificatul în registrul BREEAM (offline din 02_registru_breeam.json)."""
    cale = Path(stare.dosar_folder) / "02_registru_breeam.json"
    if not cale.exists():
        return ToolResult(
            tool="cauta_certificat",
            gasit=False,
            eroare=f"Fișierul {cale} nu există.",
            sursa="Registru BREEAM (cache offline)",
        )

    try:
        with open(cale, "r", encoding="utf-8") as f:
            date = json.load(f)

        return ToolResult(
            tool="cauta_certificat",
            gasit=True,
            date=date,
            sursa="Registru BREEAM (cache offline)",
        )
    except Exception as exc:
        return ToolResult(
            tool="cauta_certificat",
            gasit=False,
            eroare=f"Eroare la citirea registrului BREEAM: {exc}",
            sursa="Registru BREEAM (cache offline)",
        )
