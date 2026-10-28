"""Unelte de acțiune pentru agent (comunicare cu clientul, escaladare)."""

from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from contracts import StareDosar, ToolResult
from registry import tool

logger = logging.getLogger(__name__)


class CereDateClientInput(BaseModel):
    ce_lipseste: str = Field(..., description="Descrierea datelor sau documentelor lipsă")
    motiv: str = Field(default="", description="Motivul pentru care datele sunt necesare")


class EscaladeazaInput(BaseModel):
    motiv: str = Field(..., description="Motivul escaladării către comitet")


@tool(
    nume="cere_date_client",
    descriere="Solicită date sau clarificări suplimentare de la client.",
    model_intrare=CereDateClientInput,
)
def cere_date_client(intrare: CereDateClientInput, stare: StareDosar) -> ToolResult:
    """Adaugă o solicitare de informații către client în starea dosarului."""
    if intrare.motiv:
        text_actiune = f"{intrare.ce_lipseste} (motiv: {intrare.motiv})"
    else:
        text_actiune = intrare.ce_lipseste

    stare.actiuni.append(text_actiune)
    logger.info("Acțiune adăugată: %s", text_actiune)

    return ToolResult(
        tool="cere_date_client",
        gasit=True,
        date={"ce_lipseste": intrare.ce_lipseste, "motiv": intrare.motiv},
        sursa="agent.actiuni",
    )


@tool(
    nume="escaladeaza",
    descriere="Escaladează dosarul către Sustainability Bond Committee.",
    model_intrare=EscaladeazaInput,
)
def escaladeaza(intrare: EscaladeazaInput, stare: StareDosar) -> ToolResult:
    """Marchează dosarul ca escaladat și adaugă motivul în acțiunile dosarului."""
    stare.escaladat = True
    stare.actiuni.append(intrare.motiv)
    logger.warning("Dosar escaladat: %s", intrare.motiv)

    return ToolResult(
        tool="escaladeaza",
        gasit=True,
        date={"escaladat": True, "motiv": intrare.motiv},
        sursa="agent.actiuni",
    )
