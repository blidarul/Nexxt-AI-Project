"""Interfața publică a modulului de extracție: transformă PDF-urile unui dosar în DosarExtras."""

from __future__ import annotations

import json
from pathlib import Path

from contracts import DosarExtras


def extrage(folder_dosar: str | Path, force_reload: bool = False) -> DosarExtras:
    """Transformă PDF-urile unui dosar într-un obiect DosarExtras validat.

    Dacă fișierul `_extras/dosar_extras.json` există deja și nu se cere reîncărcare forțată,
    îl încarcă direct pentru eficiență. Altfel, rulează pipeline-ul de extracție structurată.
    """
    cale = Path(folder_dosar)
    extras_file = cale / "_extras" / "dosar_extras.json"

    if not force_reload and extras_file.exists():
        try:
            with open(extras_file, "r", encoding="utf-8") as f:
                date = json.load(f)
            return DosarExtras(**date)
        except Exception:
            pass

    from extraction.extrage_structurat import proceseaza_dosar_structurat

    dosar_extras, _ = proceseaza_dosar_structurat(cale)
    return dosar_extras
