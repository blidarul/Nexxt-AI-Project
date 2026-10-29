"""Tool cauta_certificat: caută certificatul în registrul public BREEAM.

Online: căutare după numărul certificatului pe tools.breeam.com (o cerere per certificat, cu cache în tools/cache/).
Offline: 02_registru_breeam.json din dosar, apoi certificatul în PDF din dosar (marcat ca neverificat în registru).
"""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

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
    normalizeaza_cheie,
    nume_fisier_sigur,
    scrie_cache,
)

logger = logging.getLogger(__name__)

NUME = "cauta_certificat"
URL_CAUTARE = "https://tools.breeam.com/projects/explore/buildings.jsp"
SURSA_ONLINE = "Registru BREEAM (tools.breeam.com)"
SURSA_OFFLINE = "Registru BREEAM (cache offline)"

# Coloanele tabelului de rezultate de pe tools.breeam.com, în ordine
COLOANE_REGISTRU = ["building_name", "client_developer", "scheme", "rating_score", "stage",
                    "certificate_no", "assessor", "town_postcode", "country"]


class CautaCertificatInput(BaseModel):
    nr_certificat: str = Field(..., min_length=1, description="Numărul certificatului BREEAM")


def _acelasi_certificat(a: Any, b: Any) -> bool:
    return bool(a) and normalizeaza_cheie(a) == normalizeaza_cheie(b)


def _text_celula(celula: str) -> list[str]:
    """Bucățile de text dintr-o celulă HTML (separate de <br>)."""
    bucati = re.split(r"<br\s*/?>", celula, flags=re.IGNORECASE)
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", b))).strip() for b in bucati]


def parseaza_rezultate(pagina_html: str) -> list[dict[str, Any]]:
    """Rândurile tabelului de rezultate, în formatul fișierelor offline (02_registru_breeam.json)."""
    rezultate = []
    for rand in re.findall(r"<tr>\s*<td>(.*?)</tr>", pagina_html, flags=re.S | re.IGNORECASE):
        celule = re.findall(r"(.*?)</td>\s*(?:<td>|$)", rand, flags=re.S)
        if len(celule) < len(COLOANE_REGISTRU):
            continue
        val = dict(zip(COLOANE_REGISTRU, (_text_celula(c) for c in celule)))
        rating_score = [x for x in val["rating_score"] if x]
        town = [x for x in val["town_postcode"] if x]
        scor = re.search(r"([\d.]+)\s*%", " ".join(rating_score))
        rezultate.append({
            "building_name": " ".join(val["building_name"]).strip(),
            "client_developer": " ".join(val["client_developer"]).strip(),
            "scheme": " ".join(val["scheme"]).strip(),
            "rating": rating_score[0] if rating_score else None,
            "score_pct": float(scor.group(1)) if scor else None,
            "stage": " ".join(val["stage"]).strip() or None,
            "certificate_no": " ".join(val["certificate_no"]).strip(),
            "assessor": " ".join(val["assessor"]).strip(),
            "town": town[0] if town else None,
            "postcode": town[1] if len(town) > 1 else None,
            "country": " ".join(val["country"]).strip() or None,
        })
    return rezultate


def _cauta_online(nr: str) -> list[dict[str, Any]]:
    import requests

    parametri = {"sectionid": 0, "certNo": nr, "countryID": 0, "partid": 10023, "Submit": "Search"}
    raspuns = requests.get(URL_CAUTARE, params=parametri, timeout=TIMEOUT_RETEA_S)
    raspuns.raise_for_status()
    return parseaza_rezultate(raspuns.text)


def _alege(intrari: list[dict[str, Any]], nr: str, sursa: str) -> ToolResult:
    for intrare in intrari:
        if _acelasi_certificat(intrare.get("certificate_no"), nr):
            return ToolResult(tool=NUME, gasit=True, date=intrare, sursa=sursa)
    return eroare(NUME, f"Certificatul {nr} nu există în registrul BREEAM.", sursa)


def _din_pdf(cale_pdf: Path, nr: str) -> ToolResult:
    """Certificatul atașat de client. Doar ce scrie în document: nicio valoare implicită."""
    import pdfplumber

    with pdfplumber.open(cale_pdf) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    def cauta(tipar: str) -> Optional[str]:
        m = re.search(tipar, text)
        return m.group(1).strip() if m else None

    nr_doc = cauta(r"Nr\.\s*Certificat:\s*(.*)")
    if nr_doc and not _acelasi_certificat(nr_doc, nr):
        return eroare(NUME, f"Certificatul {nr} nu corespunde cu cel din {cale_pdf.name} ({nr_doc}).")
    etapa = cauta(r"Etapa Evalu[aă]rii:\s*(.*)")
    scor = cauta(r"Punctaj Ob[tț]inut:\s*([0-9.]+)%")
    rating = cauta(r"Nivel Certificare \(Rating\):\s*(.*)")
    return ToolResult(
        tool=NUME,
        gasit=True,
        date={
            "building_name": cauta(r"Denumire Cl[aă]dire:\s*(.*)"),
            "client_developer": cauta(r"Client\s*/\s*Dezvoltator:\s*(.*)"),
            "scheme": cauta(r"Schema BREEAM:\s*(.*)"),
            "rating": rating.capitalize() if rating else None,
            "score_pct": float(scor) if scor else None,
            "stage": etapa,
            "certificate_no": nr_doc,
            "assessor": cauta(r"Auditat de:\s*(.*)"),
            "town": cauta(r"Ora[sș]\s*/\s*Cod Po[sș]tal:\s*([^,]+)"),
            "verificat_in_registru": False,
        },
        sursa=f"{cale_pdf.name} (extras direct din document, nu din registrul BREEAM)",
    )


def _offline(nr: str, stare: Optional[StareDosar]) -> ToolResult:
    folder = Path(getattr(stare, "dosar_folder", "") or ".")
    cale = folder / "02_registru_breeam.json"
    if cale.exists():
        with open(cale, "r", encoding="utf-8") as f:
            date = json.load(f)
        intrari = date if isinstance(date, list) else [date]
        return _alege(intrari, nr, SURSA_OFFLINE)

    cale_pdf = document_din_dosar(stare, "certificat_sustenabilitate", "BREEAM.pdf")
    if cale_pdf:
        return _din_pdf(cale_pdf, nr)

    return eroare(NUME, f"Mod offline: dosarul nu are nici {cale.name}, nici certificatul în PDF.", SURSA_OFFLINE, tehnica=True)


@tool(
    nume=NUME,
    descriere="Caută certificatul după număr în registrul public BREEAM (rating, etapă, clădire).",
    model_intrare=CautaCertificatInput,
)
@mereu_toolresult(NUME, CautaCertificatInput)
def cauta_certificat(intrare: CautaCertificatInput, stare: StareDosar) -> ToolResult:
    """Caută certificatul în registrul BREEAM. Online: tools.breeam.com (cu cache); offline: datele din dosar."""
    nr = intrare.nr_certificat.strip()
    if not nr:
        return eroare(NUME, "Numărul certificatului e gol.", tehnica=True)

    if not mod_online():
        return _offline(nr, stare)

    cheie_cache = f"breeam_{nume_fisier_sigur(nr)}.json"
    try:
        intrari = _cauta_online(nr)
        scrie_cache(cheie_cache, intrari)
        return _alege(intrari, nr, SURSA_ONLINE)
    except Exception as exc:
        logger.warning("Registrul BREEAM indisponibil (%s); se folosește cache-ul sau datele offline.", exc)
        din_cache = citeste_cache(cheie_cache)
        if din_cache is not None:
            return _alege(din_cache, nr, f"{SURSA_ONLINE} (cache local, site indisponibil)")
        rezultat = _offline(nr, stare)
        rezultat.sursa = f"{rezultat.sursa} (registrul online indisponibil: {type(exc).__name__})"
        return rezultat
