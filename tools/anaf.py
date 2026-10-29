"""Tool verifica_firma: starea firmei și codul CAEN din registrul ANAF.

Online: API-ul public ANAF PlatitorTvaRest v9 (răspunsul se păstrează în tools/cache/).
Offline: 05_raspuns_anaf.json din dosar (același format ca API-ul), apoi fișa ANAF în PDF din dosar.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

from contracts import StareDosar, ToolResult
from registry import tool
from tools._comun import (
    TIMEOUT_RETEA_S,
    citeste_cache,
    document_din_dosar,
    eroare,
    mereu_toolresult,
    mod_online,
    scrie_cache,
)

logger = logging.getLogger(__name__)

NUME = "verifica_firma"
URL_ANAF = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"
SURSA_API = "ANAF API PlatitorTvaRest v9"
SURSA_OFFLINE = "ANAF API v9 (cache offline)"
SURSA_PDF = "RASPUNS_ANAF.pdf (extras direct din document, nu din registru)"


class VerificaFirmaInput(BaseModel):
    cui: Union[str, int] = Field(..., description="Codul Unic de Înregistrare (CUI), cu sau fără prefixul RO")


def normalizeaza_cui(cui: Any) -> Optional[str]:
    """„RO 9900000030” / 9900000030 -> „9900000030”; None dacă nu e un CUI (2-10 cifre)."""
    text = re.sub(r"^\s*RO\s*", "", str(cui), flags=re.IGNORECASE)
    if not re.fullmatch(r"\d{2,10}", text.strip()):
        return None
    return text.strip()


def _din_raspuns_anaf(raspuns: dict, cui: str, sursa: str) -> ToolResult:
    """Caută CUI-ul cerut în răspunsul ANAF (found / notFound)."""
    for firma in raspuns.get("found") or []:
        date_generale = (firma or {}).get("date_generale") or {}
        if str(date_generale.get("cui", "")).strip() == cui:
            return ToolResult(
                tool=NUME,
                gasit=True,
                date={"date_generale": date_generale, "stare_inactiv": firma.get("stare_inactiv") or {}},
                sursa=sursa,
            )
    gasite = [str((f or {}).get("date_generale", {}).get("cui")) for f in raspuns.get("found") or []]
    detaliu = f" (răspunsul conține: {', '.join(gasite)})" if gasite else ""
    return eroare(NUME, f"CUI-ul {cui} nu a fost găsit în registrul ANAF{detaliu}.", sursa)


def _interogheaza_anaf(cui: str) -> dict:
    import requests

    corp = [{"cui": int(cui), "data": dt.date.today().isoformat()}]
    raspuns = requests.post(URL_ANAF, json=corp, timeout=TIMEOUT_RETEA_S)
    # Pentru un CUI inexistent, ANAF răspunde 404 cu {"found": [], "notFound": [cui]}: e un răspuns, nu o eroare
    if raspuns.status_code == 404:
        try:
            date = raspuns.json()
        except ValueError:
            date = None
        if isinstance(date, dict) and "notFound" in date:
            return date
    raspuns.raise_for_status()
    return raspuns.json()


def _din_pdf(cale_pdf: Path, cui: str) -> ToolResult:
    """Fișa ANAF atașată la dosar. Doar ce scrie în document: nicio valoare implicită."""
    import pdfplumber

    with pdfplumber.open(cale_pdf) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    def cauta(tipar: str) -> Optional[str]:
        m = re.search(tipar, text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else None

    cui_doc = cauta(r"Cod Unic de [IÎ]nregistrare \(CUI\):\s*(?:RO\s*)?([0-9]+)")
    if cui_doc and cui_doc != cui:
        return eroare(NUME, f"CUI-ul {cui} nu corespunde cu cel din {cale_pdf.name} ({cui_doc}).", SURSA_PDF)

    stare_fiscala = cauta(r"Stare [IÎ]nregistrare Fiscal[aă]:\s*([^\n(]+)")
    inactiv_text = cauta(r"Status Inactivitate Fiscal[aă]:\s*([^\n]+)")
    status_inactiv = None
    if inactiv_text:
        status_inactiv = not inactiv_text.upper().startswith("NU")

    date_generale = {
        "cui": int(cui_doc) if cui_doc else int(cui),
        "denumire": cauta(r"Denumire Contribuabil:\s*(.*)"),
        "adresa": cauta(r"Sediu Social:\s*(.*)"),
        "nrRegCom": cauta(r"Registrul Comer[tț]ului:\s*(.*)"),
        "cod_CAEN": cauta(r"Activitate Principal[aă] \(CAEN\):\s*([0-9]{4})"),
        "stare_inregistrare": stare_fiscala,
    }
    return ToolResult(
        tool=NUME,
        gasit=True,
        date={
            "date_generale": date_generale,
            "stare_inactiv": {"statusInactivi": status_inactiv},
            "verificat_in_registru": False,
        },
        sursa=f"{cale_pdf.name} (extras direct din document, nu din registru)",
    )


def _offline(cui: str, stare: Optional[StareDosar]) -> ToolResult:
    folder = Path(getattr(stare, "dosar_folder", "") or ".")
    cale = folder / "05_raspuns_anaf.json"
    if cale.exists():
        with open(cale, "r", encoding="utf-8") as f:
            return _din_raspuns_anaf(json.load(f), cui, SURSA_OFFLINE)

    cale_pdf = document_din_dosar(stare, "raspuns_anaf", "RASPUNS_ANAF.pdf")
    if cale_pdf:
        return _din_pdf(cale_pdf, cui)

    return eroare(NUME, f"Mod offline: dosarul nu are nici {cale.name}, nici fișa ANAF în PDF.", SURSA_OFFLINE, tehnica=True)


@tool(
    nume=NUME,
    descriere="Verifică starea firmei (activă / inactivă) și codul CAEN principal în registrul ANAF.",
    model_intrare=VerificaFirmaInput,
)
@mereu_toolresult(NUME, VerificaFirmaInput)
def verifica_firma(intrare: VerificaFirmaInput, stare: StareDosar) -> ToolResult:
    """Interoghează ANAF. Online: API v9 (cu cache); offline: datele din dosar."""
    cui = normalizeaza_cui(intrare.cui)
    if cui is None:
        return eroare(NUME, f"CUI invalid: {intrare.cui!r} (se așteaptă 2-10 cifre, opțional cu prefixul RO).", tehnica=True)

    if not mod_online():
        return _offline(cui, stare)

    cheie_cache = f"anaf_{cui}.json"
    try:
        raspuns = _interogheaza_anaf(cui)
        scrie_cache(cheie_cache, raspuns)
        return _din_raspuns_anaf(raspuns, cui, SURSA_API)
    except Exception as exc:
        logger.warning("ANAF indisponibil (%s); se folosește cache-ul sau datele offline.", exc)
        din_cache = citeste_cache(cheie_cache)
        if din_cache is not None:
            return _din_raspuns_anaf(din_cache, cui, f"{SURSA_API} (cache local, API indisponibil)")
        rezultat = _offline(cui, stare)
        rezultat.sursa = f"{rezultat.sursa} (API ANAF indisponibil: {type(exc).__name__})"
        return rezultat
