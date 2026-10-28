"""Țările din Anexa B: lista din rules/conditii_generale.yaml, corespondența RO/EN/ISO3 din tools/data/tari.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from tools._comun import FOLDER_DATE, normalizeaza_cheie

CALE_REGULI = Path(__file__).resolve().parent.parent / "rules" / "conditii_generale.yaml"
ID_REGULA_TARA = "G-01"


@lru_cache(maxsize=None)
def tari_anexa_b() -> list[str]:
    """Numele țărilor eligibile, exact cum apar în regula G-01."""
    with open(CALE_REGULI, encoding="utf-8") as f:
        reguli = yaml.safe_load(f)
    for regula in reguli.get("conditii_generale") or []:
        if regula.get("id") == ID_REGULA_TARA:
            return [str(t) for t in regula.get("in_lista") or []]
    raise ValueError(f"Regula {ID_REGULA_TARA} (lista de țări) lipsește din {CALE_REGULI.name}")


@lru_cache(maxsize=None)
def corespondenta_tari() -> dict[str, dict[str, Any]]:
    with open(FOLDER_DATE / "tari.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["tari"]


@lru_cache(maxsize=None)
def _index_nume() -> dict[str, str]:
    """Orice denumire acceptată (normalizată) -> numele RO din reguli."""
    index: dict[str, str] = {}
    for nume_ro, info in corespondenta_tari().items():
        for denumire in [nume_ro, info["en"], info["iso3"], *(info.get("alias") or [])]:
            index[normalizeaza_cheie(denumire)] = nume_ro
    return index


def gaseste_tara(text: Any) -> Optional[dict[str, Any]]:
    """„România” / „Romania” / „ROU” -> {"nume_ro", "en", "iso3", "anexa_b"}; None dacă nu e cunoscută."""
    nume_ro = _index_nume().get(normalizeaza_cheie(text))
    if nume_ro is None:
        return None
    info = corespondenta_tari()[nume_ro]
    return {"nume_ro": nume_ro, "en": info["en"], "iso3": info["iso3"], "anexa_b": nume_ro in tari_anexa_b()}
