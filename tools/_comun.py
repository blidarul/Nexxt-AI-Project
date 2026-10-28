"""Utilitare comune pentru tools: modul offline/online, cache local, garanția că se întoarce mereu ToolResult."""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Optional, Type

from pydantic import BaseModel, ValidationError

from contracts import ToolResult

logger = logging.getLogger(__name__)

FOLDER_TOOLS = Path(__file__).resolve().parent
FOLDER_DATE = FOLDER_TOOLS / "data"
FOLDER_CACHE = FOLDER_TOOLS / "cache"

TIMEOUT_RETEA_S = 20


def mod_online() -> bool:
    """MOD_TOOLS se citește la fiecare apel (config.py îl încarcă din .env), ca testele să-l poată schimba."""
    return os.getenv("MOD_TOOLS", "offline").strip().lower() == "online"


def normalizeaza_cheie(text: Any) -> str:
    """Pentru potriviri tolerante: fără diacritice, litere mici, fără spații, cratime, puncte sau underscore."""
    nfkd = unicodedata.normalize("NFKD", str(text or ""))
    fara = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return re.sub(r"[\s\-_.]+", "", fara)


def citeste_cache(nume: str) -> Optional[Any]:
    cale = FOLDER_CACHE / nume
    if not cale.exists():
        return None
    try:
        return json.loads(cale.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Cache ilizibil %s: %s", cale, exc)
        return None


def scrie_cache(nume: str, date: Any) -> None:
    try:
        FOLDER_CACHE.mkdir(parents=True, exist_ok=True)
        (FOLDER_CACHE / nume).write_text(json.dumps(date, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Nu s-a putut scrie cache-ul %s: %s", nume, exc)


def nume_fisier_sigur(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text))[:120]


def eroare(tool: str, mesaj: str, sursa: str = "", date: Optional[dict] = None) -> ToolResult:
    return ToolResult(tool=tool, gasit=False, eroare=mesaj, sursa=sursa, date=date or {})


def mereu_toolresult(nume: str, model_intrare: Optional[Type[BaseModel]] = None) -> Callable:
    """Un tool nu aruncă niciodată excepții către agent (contracts.ToolResult).

    Acceptă intrarea ca model sau ca dict (validat aici); orice argument greșit sau excepție
    devine un ToolResult cu gasit=False și eroare explicită, chiar la apel direct, fără registry.
    """

    def decorator(fn: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        @functools.wraps(fn)
        def invelis(intrare: Any, stare: Any = None) -> ToolResult:
            if model_intrare is not None and not isinstance(intrare, model_intrare):
                try:
                    intrare = model_intrare.model_validate(intrare if isinstance(intrare, dict) else dict(intrare))
                except (ValidationError, TypeError, ValueError) as exc:
                    return eroare(nume, f"Argumente invalide pentru '{nume}': {exc}")
            try:
                rezultat = fn(intrare, stare)
            except Exception as exc:  # noqa: BLE001 - contractul cere ToolResult, nu excepții
                logger.exception("Eroare în tool-ul %s", nume)
                return eroare(nume, f"Eroare internă în '{nume}': {type(exc).__name__}: {exc}")
            if not isinstance(rezultat, ToolResult):
                return eroare(nume, f"'{nume}' a întors {type(rezultat).__name__} în loc de ToolResult")
            return rezultat

        return invelis

    return decorator


def document_din_dosar(stare: Any, tip: str, nume_rezerva: str) -> Optional[Path]:
    """PDF-ul de un anumit tip din dosar: întâi după clasificarea din conținut (raport_extractie),
    apoi, ca rezervă, după numele de fișier obișnuit."""
    folder = Path(getattr(stare, "dosar_folder", "") or ".")
    raport = getattr(stare, "raport_extractie", None) or {}
    if not raport:
        cale_raport = folder / "_extras" / "raport_extractie.json"
        if cale_raport.exists():
            try:
                raport = json.loads(cale_raport.read_text(encoding="utf-8"))
            except Exception:
                raport = {}
    for doc in raport.get("documente_clasificate") or []:
        tip_doc = doc.get("tip_din_continut") or doc.get("tip_detectat")
        if tip_doc == tip and (folder / doc.get("fisier", "")).is_file():
            return folder / doc["fisier"]
    cale = folder / nume_rezerva
    return cale if cale.is_file() else None
