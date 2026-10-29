"""Serverul Green Proof: un API subțire peste funcțiile existente, plus pagina din ui/static.

Aici nu se decide eligibilitatea. Verdictul vine din agent.orchestrator.proceseaza_dosar,
datele extrase din dosare/<id>/_extras, legătura câmp -> regulă din rules/cerinte_dosar.yaml.
Serverul doar le pune laolaltă, păstrează ultimul rezultat (pentru demo fără agent) și
înregistrează decizia analistului în ui/data/decizii.json.

Fișierele se servesc doar din folderul dosarului cerut, din dosare/ (fără ieșiri prin ../).
"""

from __future__ import annotations

import csv
import json
import os
import re
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import yaml
from pydantic import BaseModel

from contracts import Verdict

RADACINA = Path(__file__).resolve().parent.parent
FOLDER_DOSARE = RADACINA / "dosare"
FOLDER_DATE = Path(__file__).resolve().parent / "data"
FOLDER_STATIC = Path(__file__).resolve().parent / "static"
NUME_PRODUS = "Green Proof"

# Verdictul agentului -> decizia pe care o recomandă analistului
RECOMANDARE_PENTRU_VERDICT = {
    "ELIGIBIL": "aprobat",
    "ELIGIBIL_CU_MONITORIZARE": "aprobat",
    "NEELIGIBIL": "respins",
    "EXCEPTIE_ESCALADARE_COMITET": "interventie",
}
Decizie = Literal["aprobat", "respins", "interventie"]
DECIZII_CU_COMENTARIU = {"respins", "interventie"}

TIPURI_PREVIZUALIZARE = {".pdf": "application/pdf", ".json": "application/json"}
# Fișierele de evaluare (răspunsul așteptat, extrasul de test) nu fac parte din dosarul clientului
FISIERE_ASCUNSE = {"expected.json", "extras_mock.json"}
_ID_DOSAR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")
_SURSA = re.compile(r"^(?P<fisier>.+?)(?:,\s*p\.?\s*(?P<pagina>\d+))?\s*$")


class CerereDecizie(BaseModel):
    decizie: Decizie
    comentariu: str = ""
    # True după ce analistul a confirmat că decide altfel decât agentul
    confirmat: bool = False


def _acum() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _citeste_json(cale: Path) -> Any:
    try:
        with open(cale, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _scrie_json(cale: Path, date: Any) -> None:
    """Scriere atomică: fișierul nu rămâne pe jumătate scris dacă procesul se oprește."""
    cale.parent.mkdir(parents=True, exist_ok=True)
    temporar = cale.with_suffix(cale.suffix + ".tmp")
    with open(temporar, "w", encoding="utf-8") as f:
        json.dump(date, f, ensure_ascii=False, indent=2)
    os.replace(temporar, cale)


def imparte_sursa(sursa: str) -> tuple[Optional[str], Optional[int]]:
    """„01_cerere_finantare.pdf, p.3” -> ("01_cerere_finantare.pdf", 3)."""
    potrivire = _SURSA.match(sursa or "")
    if not potrivire or not potrivire.group("fisier").strip():
        return None, None
    pagina = potrivire.group("pagina")
    return potrivire.group("fisier").strip(), int(pagina) if pagina else None


def cale_sigura(folder: Path, cale_relativa: str) -> Optional[Path]:
    """Fișierul cerut, doar dacă rămâne în folder și poate fi previzualizat; altfel None."""
    if not cale_relativa or "\x00" in cale_relativa:
        return None
    radacina = folder.resolve()
    try:
        tinta = (radacina / cale_relativa).resolve()
    except (OSError, ValueError):
        return None
    if not tinta.is_relative_to(radacina) or not tinta.is_file():
        return None
    if tinta.name in FISIERE_ASCUNSE or tinta.suffix.lower() not in TIPURI_PREVIZUALIZARE:
        return None
    return tinta


def _evaluare_implicita(folder: str) -> Verdict:
    from agent.orchestrator import proceseaza_dosar

    return proceseaza_dosar(folder)


def _moduri() -> dict[str, str]:
    import config

    return {
        "mod_extractie": config.MOD_EXTRACTIE, "mod_tools": config.MOD_TOOLS, "mod_agent": config.MOD_AGENT,
        "data_alocare": config.DATA_ALOCARE,
    }


@lru_cache(maxsize=1)
def nume_reguli() -> dict[str, str]:
    """ID regulă -> denumirea ei, din rules/*.yaml (pentru afișare lângă cod)."""
    rezultat: dict[str, str] = {}

    def parcurge(nod: Any) -> None:
        if isinstance(nod, dict):
            if isinstance(nod.get("id"), str) and isinstance(nod.get("nume"), str):
                rezultat.setdefault(nod["id"], nod["nume"])
            for valoare in nod.values():
                parcurge(valoare)
        elif isinstance(nod, list):
            for valoare in nod:
                parcurge(valoare)

    for cale in sorted((RADACINA / "rules").glob("*.yaml")):
        with open(cale, encoding="utf-8") as f:
            parcurge(yaml.safe_load(f))
    return rezultat


def _campuri_pe_reguli(categorie: Optional[str], subcategorie: Optional[str]) -> dict[str, list[str]]:
    """Regula -> câmpurile care o susțin (din rules/cerinte_dosar.yaml)."""
    from extraction.cerinte import campuri_cerute

    rezultat: dict[str, list[str]] = {}
    for intrare in campuri_cerute(categorie, subcategorie):
        for regula in intrare.get("pentru") or []:
            rezultat.setdefault(str(regula), []).append(intrare["camp"])
    return rezultat


def creeaza_app(
    folder_dosare: Path = FOLDER_DOSARE,
    folder_date: Path = FOLDER_DATE,
    evalueaza: Optional[Callable[[str], Verdict]] = None,
    moduri: Callable[[], dict[str, str]] = _moduri,
) -> FastAPI:
    evalueaza = evalueaza or _evaluare_implicita
    fisier_decizii = folder_date / "decizii.json"
    folder_rezultate = folder_date / "rezultate"
    blocare = threading.Lock()
    app = FastAPI(title=NUME_PRODUS, docs_url=None, redoc_url=None)

    # ---------------------------------------------------------------- date

    def ids_dosare() -> list[str]:
        if not folder_dosare.is_dir():
            return []
        return sorted(
            p.name for p in folder_dosare.iterdir()
            if p.is_dir() and _ID_DOSAR.match(p.name) and not p.name.startswith("_")
        )

    def folder_dosar(dosar_id: str) -> Path:
        # Doar numele listate: un id ca „..” sau „a/b” nu ajunge niciodată la sistemul de fișiere
        if dosar_id not in ids_dosare():
            raise HTTPException(404, f"Dosarul „{dosar_id}” nu există.")
        return folder_dosare / dosar_id

    def descrieri() -> dict[str, str]:
        cale = folder_dosare / "index.csv"
        if not cale.is_file():
            return {}
        with open(cale, encoding="utf-8", newline="") as f:
            return {r["dosar"]: r.get("descriere") or "" for r in csv.DictReader(f) if r.get("dosar")}

    def raport(folder: Path) -> dict[str, Any]:
        return _citeste_json(folder / "_extras" / "raport_extractie.json") or {}

    def extras(folder: Path) -> dict[str, Any]:
        return _citeste_json(folder / "_extras" / "dosar_extras.json") or {}

    def decizii() -> list[dict[str, Any]]:
        date = _citeste_json(fisier_decizii)
        return date if isinstance(date, list) else []

    def decizie_curenta(dosar_id: str) -> Optional[dict[str, Any]]:
        ale_dosarului = [d for d in decizii() if d.get("dosar") == dosar_id]
        return ale_dosarului[-1] if ale_dosarului else None

    def rezultat_salvat(dosar_id: str) -> Optional[dict[str, Any]]:
        date = _citeste_json(folder_rezultate / f"{dosar_id}.json")
        return date if isinstance(date, dict) and "verdict" in date else None

    def url_fisier(dosar_id: str, fisier: str) -> str:
        from urllib.parse import quote

        return f"/api/dosare/{quote(dosar_id)}/fisiere/{quote(fisier)}"

    def camp_public(dosar_id: str, folder: Path, nume: str, camp: dict[str, Any]) -> dict[str, Any]:
        fisier, pagina = imparte_sursa(str(camp.get("sursa") or ""))
        exista = bool(fisier) and cale_sigura(folder, fisier) is not None
        return {
            "camp": nume,
            "valoare": camp.get("valoare"),
            "sursa": camp.get("sursa") or "",
            "fisier": fisier if exista else None,
            "pagina": pagina,
            "url": url_fisier(dosar_id, fisier) if exista else None,
            "incredere": camp.get("incredere"),
            "citat": camp.get("citat"),
            "citat_verificat": camp.get("citat_verificat"),
        }

    def rezultat_public(dosar_id: str, folder: Path, salvat: dict[str, Any]) -> dict[str, Any]:
        verdict = salvat["verdict"]
        campuri = raport(folder).get("campuri_extrase") or {}
        date_extrase = extras(folder)
        categorie = (date_extrase.get("categorie") or {}).get("valoare")
        subcategorie = (date_extrase.get("subcategorie") or {}).get("valoare")
        pe_reguli = _campuri_pe_reguli(categorie, subcategorie)
        dovezi = {
            r["regula_id"]: [
                camp_public(dosar_id, folder, nume, campuri[nume])
                for nume in pe_reguli.get(r["regula_id"], []) if nume in campuri and campuri[nume].get("sursa")
            ]
            for r in verdict.get("reguli") or []
        }
        return {
            "dosar": dosar_id,
            "salvat_la": salvat.get("salvat_la"),
            "verdict": verdict,
            "recomandare": RECOMANDARE_PENTRU_VERDICT.get(verdict.get("verdict")),
            "dovezi": dovezi,
            "nume_reguli": {r["regula_id"]: nume_reguli().get(r["regula_id"]) for r in verdict.get("reguli") or []},
        }

    def status(dosar_id: str) -> str:
        decizie = decizie_curenta(dosar_id)
        return decizie["decizie"] if decizie else "in_asteptare"

    # ---------------------------------------------------------------- API

    @app.get("/api/stare")
    def stare() -> dict[str, Any]:
        return {"produs": NUME_PRODUS, **moduri()}

    @app.get("/api/dosare")
    def lista_dosare() -> list[dict[str, Any]]:
        texte = descrieri()
        rezultat = []
        for dosar_id in ids_dosare():
            folder = folder_dosare / dosar_id
            date_raport, date_extrase = raport(folder), extras(folder)
            campuri = date_raport.get("campuri_extrase") or {}
            salvat = rezultat_salvat(dosar_id)
            verdict = salvat["verdict"]["verdict"] if salvat else None
            rezultat.append({
                "id": dosar_id,
                "descriere": texte.get(dosar_id, ""),
                "proiect": (campuri.get("descriere_proiect") or {}).get("valoare"),
                "categorie": (date_extrase.get("categorie") or {}).get("valoare"),
                "suma_eur": (date_extrase.get("suma_eur") or {}).get("valoare"),
                "adresa": (date_extrase.get("adresa_cladire") or {}).get("valoare"),
                "nr_documente": len(date_raport.get("documente_clasificate") or []),
                "nr_documente_lipsa": len(date_raport.get("documente_lipsa") or []),
                "verdict_salvat": verdict,
                "recomandare": RECOMANDARE_PENTRU_VERDICT.get(verdict) if verdict else None,
                "status": status(dosar_id),
            })
        return rezultat

    @app.get("/api/dosare/{dosar_id}")
    def detalii_dosar(dosar_id: str) -> dict[str, Any]:
        folder = folder_dosar(dosar_id)
        date_raport, date_extrase = raport(folder), extras(folder)
        clasificate = {d.get("fisier"): d for d in date_raport.get("documente_clasificate") or []}
        documente = []
        for cale in sorted(folder.rglob("*")):
            relativ = cale.relative_to(folder).as_posix()
            if relativ.startswith("_") or cale_sigura(folder, relativ) is None:
                continue
            clasificare = clasificate.get(relativ) or {}
            documente.append({
                "fisier": relativ,
                "url": url_fisier(dosar_id, relativ),
                "format": cale.suffix.lower().lstrip("."),
                "octeti": cale.stat().st_size,
                # PDF-urile vin de la client; JSON-urile sunt răspunsurile registrelor (BREEAM, ANAF)
                "provenienta": "client" if cale.suffix.lower() == ".pdf" else "registru",
                "tip_detectat": clasificare.get("tip_detectat"),
                "incredere": clasificare.get("incredere"),
                "cerinte": clasificare.get("id_cerinte") or [],
                "nume_contrazice_continut": bool(clasificare.get("nume_contrazice_continut")),
            })
        campuri = date_raport.get("campuri_extrase") or {}
        salvat = rezultat_salvat(dosar_id)
        return {
            "id": dosar_id,
            "descriere": descrieri().get(dosar_id, ""),
            "proiect": (campuri.get("descriere_proiect") or {}).get("valoare"),
            "categorie": (date_extrase.get("categorie") or {}).get("valoare"),
            "subcategorie": (date_extrase.get("subcategorie") or {}).get("valoare"),
            "documente": documente,
            "documente_lipsa": date_raport.get("documente_lipsa") or [],
            "documente_recomandate_lipsa": date_raport.get("documente_recomandate_lipsa") or [],
            "campuri": [camp_public(dosar_id, folder, nume, camp) for nume, camp in campuri.items()],
            "campuri_lipsa": date_raport.get("campuri_lipsa") or [],
            "conflicte": date_raport.get("conflicte") or [],
            "chiriasi": date_extrase.get("chiriasi") or [],
            "afirmatii_client": date_extrase.get("afirmatii_client") or [],
            "rezultat": rezultat_public(dosar_id, folder, salvat) if salvat else None,
            "decizie": decizie_curenta(dosar_id),
            "status": status(dosar_id),
        }

    @app.post("/api/dosare/{dosar_id}/evaluare")
    def evaluare(dosar_id: str) -> dict[str, Any]:
        """Rulează agentul. Dacă agentul nu poate rula, întoarce ultimul rezultat salvat."""
        folder = folder_dosar(dosar_id)
        try:
            with blocare:
                verdict = evalueaza(str(folder))
            salvat = {"salvat_la": _acum(), "verdict": Verdict.model_validate(verdict).model_dump(mode="json")}
            _scrie_json(folder_rezultate / f"{dosar_id}.json", salvat)
            return {**rezultat_public(dosar_id, folder, salvat), "din_salvare": False, "eroare": None}
        except Exception as exc:
            salvat = rezultat_salvat(dosar_id)
            if salvat is None:
                raise HTTPException(
                    503, f"Agentul nu a putut evalua dosarul ({type(exc).__name__}: {exc}) și nu există un rezultat salvat."
                ) from exc
            return {**rezultat_public(dosar_id, folder, salvat), "din_salvare": True, "eroare": f"{type(exc).__name__}: {exc}"}

    @app.get("/api/dosare/{dosar_id}/rezultat")
    def rezultat(dosar_id: str) -> dict[str, Any]:
        folder = folder_dosar(dosar_id)
        salvat = rezultat_salvat(dosar_id)
        if salvat is None:
            raise HTTPException(404, "Nu există un rezultat salvat pentru acest dosar.")
        return {**rezultat_public(dosar_id, folder, salvat), "din_salvare": True, "eroare": None}

    @app.get("/api/dosare/{dosar_id}/fisiere/{cale:path}")
    def fisier(dosar_id: str, cale: str) -> FileResponse:
        tinta = cale_sigura(folder_dosar(dosar_id), cale)
        if tinta is None:
            raise HTTPException(404, "Fișierul nu există sau nu poate fi previzualizat.")
        return FileResponse(
            tinta, media_type=TIPURI_PREVIZUALIZARE[tinta.suffix.lower()],
            filename=tinta.name, content_disposition_type="inline",
        )

    @app.get("/api/decizii")
    def lista_decizii() -> list[dict[str, Any]]:
        return decizii()

    @app.post("/api/dosare/{dosar_id}/decizie")
    def decide(dosar_id: str, cerere: CerereDecizie) -> dict[str, Any]:
        folder_dosar(dosar_id)
        salvat = rezultat_salvat(dosar_id)
        if salvat is None:
            raise HTTPException(409, "Deschide soluția agentului înainte de a decide.")
        comentariu = cerere.comentariu.strip()
        if cerere.decizie in DECIZII_CU_COMENTARIU and not comentariu:
            raise HTTPException(422, "Pentru „Respinge” și „Intervenție umană” comentariul este obligatoriu.")
        verdict_agent = salvat["verdict"].get("verdict")
        recomandare = RECOMANDARE_PENTRU_VERDICT.get(verdict_agent)
        difera = recomandare is not None and cerere.decizie != recomandare
        if difera and not cerere.confirmat:
            raise HTTPException(409, {
                "mesaj": "Decizia diferă de recomandarea agentului. Confirmă pentru a o înregistra.",
                "necesita_confirmare": True,
                "recomandare_agent": recomandare,
            })
        inregistrare = {
            "dosar": dosar_id,
            "decizie": cerere.decizie,
            "comentariu": comentariu,
            "recomandare_agent": recomandare,
            "verdict_agent": verdict_agent,
            "difera_de_agent": difera,
            "data": _acum(),
        }
        with blocare:
            _scrie_json(fisier_decizii, [*decizii(), inregistrare])
        return inregistrare

    @app.delete("/api/decizii")
    def reseteaza_decizii() -> dict[str, Any]:
        with blocare:
            _scrie_json(fisier_decizii, [])
        return {"sterse": True}

    # ---------------------------------------------------------------- pagina

    @app.get("/", include_in_schema=False)
    def pagina() -> FileResponse:
        index = FOLDER_STATIC / "index.html"
        if not index.is_file():
            raise HTTPException(404, "Pagina nu a fost construită încă (ui/static/index.html).")
        return FileResponse(index, media_type="text/html")

    if FOLDER_STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=FOLDER_STATIC), name="static")

    return app


app = creeaza_app()
