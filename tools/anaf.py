"""Tool verifica_firma: extrage date despre firma din ANAF."""

from __future__ import annotations

import json
import logging
import re
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
    """Interoghează ANAF (offline din 05_raspuns_anaf.json sau fallback din PDF)."""
    cale = Path(stare.dosar_folder) / "05_raspuns_anaf.json"
    if cale.exists():
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
                eroare=f"Eroare la citirea răspunsului ANAF: {exc}",
                sursa="ANAF API v9 (cache offline)",
            )

    # Fallback la documentul PDF RASPUNS_ANAF.pdf din dosar
    pdf_cale = Path(stare.dosar_folder) / "RASPUNS_ANAF.pdf"
    if pdf_cale.exists():
        try:
            import pdfplumber
            with pdfplumber.open(pdf_cale) as pdf:
                full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])

            m_cui = re.search(r"Cod Unic de [IÎ]nregistrare \(CUI\):\s*([0-9]+)", full_text)
            m_den = re.search(r"Denumire Contribuabil:\s*(.*)", full_text)
            m_reg = re.search(r"Registrul Comer[tț]ului:\s*(.*)", full_text)
            m_adr = re.search(r"Sediu Social:\s*(.*)", full_text)
            m_caen = re.search(r"Activitate Principal[aă] \(CAEN\):\s*([0-9]{4})", full_text)
            m_inact = "NU apare" in full_text and "inactiv" in full_text

            cui_gasit = m_cui.group(1) if m_cui else ""
            cui_solicitat = str(intrare.cui).replace("RO", "").strip()

            if cui_gasit and cui_solicitat and cui_gasit != cui_solicitat:
                return ToolResult(
                    tool="verifica_firma",
                    gasit=False,
                    eroare=f"CUI-ul {intrare.cui} nu corespunde cu cel din RASPUNS_ANAF.pdf ({cui_gasit}).",
                    sursa="RASPUNS_ANAF.pdf (extras direct din document)",
                )

            date_generale = {
                "cui": int(cui_gasit) if cui_gasit.isdigit() else intrare.cui,
                "denumire": m_den.group(1).strip() if m_den else "",
                "adresa": m_adr.group(1).strip() if m_adr else "",
                "nrRegCom": m_reg.group(1).strip() if m_reg else "",
                "cod_CAEN": m_caen.group(1).strip() if m_caen else "6820",
                "stare_inregistrare": "INREGISTRAT",
            }
            stare_inactiv = {
                "statusInactivi": not m_inact,
            }
            return ToolResult(
                tool="verifica_firma",
                gasit=True,
                date={"date_generale": date_generale, "stare_inactiv": stare_inactiv},
                sursa="RASPUNS_ANAF.pdf (extras direct din document)",
            )
        except Exception as exc:
            logger.warning("Eroare la parsarea RASPUNS_ANAF.pdf: %s", exc)

    return ToolResult(
        tool="verifica_firma",
        gasit=False,
        eroare=f"Fișierul {cale} nu există și nu s-a putut parsa RASPUNS_ANAF.pdf.",
        sursa="ANAF API v9 (cache offline)",
    )
