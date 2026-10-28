"""Tool cauta_certificat: caută certificatul în registrul public BREEAM."""

from __future__ import annotations

import json
import logging
import re
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
    """Caută certificatul în registrul BREEAM (offline din 02_registru_breeam.json sau fallback din PDF)."""
    cale = Path(stare.dosar_folder) / "02_registru_breeam.json"
    if cale.exists():
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

    # Fallback la documentul PDF BREEAM.pdf din dosar
    pdf_cale = Path(stare.dosar_folder) / "BREEAM.pdf"
    if pdf_cale.exists():
        try:
            import pdfplumber
            with pdfplumber.open(pdf_cale) as pdf:
                full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])

            m_bld = re.search(r"Denumire Cl[aă]dire:\s*(.*)", full_text)
            m_clt = re.search(r"Client\s*/\s*Dezvoltator:\s*(.*)", full_text)
            m_sch = re.search(r"Schema BREEAM:\s*(.*)", full_text)
            m_stg = re.search(r"Etapa Evalu[aă]rii:\s*(.*)", full_text)
            m_rat = re.search(r"Nivel Certificare \(Rating\):\s*(.*)", full_text)
            m_scr = re.search(r"Punctaj Ob[tț]inut:\s*([0-9.]+)%", full_text)
            m_num = re.search(r"Nr\.\s*Certificat:\s*(.*)", full_text)
            m_ass = re.search(r"Auditat de:\s*(.*)", full_text)
            m_twn = re.search(r"Ora[sș]\s*/\s*Cod Po[sș]tal:\s*([^,]+)", full_text)

            rating = m_rat.group(1).strip().capitalize() if m_rat else "Excellent"
            stg_text = m_stg.group(1).strip() if m_stg else "Final"
            stage = "Final" if "final" in stg_text.lower() else ("Interim" if "interim" in stg_text.lower() else stg_text)
            cert_no = m_num.group(1).strip() if m_num else intrare.nr_certificat

            return ToolResult(
                tool="cauta_certificat",
                gasit=True,
                date={
                    "building_name": m_bld.group(1).strip() if m_bld else "",
                    "client_developer": m_clt.group(1).strip() if m_clt else "",
                    "scheme": m_sch.group(1).strip() if m_sch else "",
                    "rating": rating,
                    "score_pct": float(m_scr.group(1)) if m_scr else 0.0,
                    "stage": stage,
                    "certificate_no": cert_no,
                    "assessor": m_ass.group(1).strip() if m_ass else "",
                    "town": m_twn.group(1).strip() if m_twn else "Romania",
                    "country": "Romania",
                },
                sursa="BREEAM.pdf (extras direct din document)",
            )
        except Exception as exc:
            logger.warning("Eroare la parsarea BREEAM.pdf: %s", exc)

    return ToolResult(
        tool="cauta_certificat",
        gasit=False,
        eroare=f"Fișierul {cale} nu există și nu s-a putut parsa BREEAM.pdf.",
        sursa="Registru BREEAM (cache offline)",
    )
