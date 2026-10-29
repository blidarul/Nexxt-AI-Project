"""Interfața publică a modulului de extracție: transformă documentele unui dosar în DosarExtras."""

from __future__ import annotations

from pathlib import Path

from contracts import DosarExtras


def extrage(folder_dosar: str | Path, force_reload: bool = False) -> DosarExtras:
    """Transformă documentele unui dosar într-un obiect DosarExtras validat.

    Nu refolosește niciodată fișierele din _extras sau _brut generate anterior;
    rulează întotdeauna pipeline-ul complet de extracție proaspăt din fișierele sursă.
    """
    cale = Path(folder_dosar)
    from extraction.extrage_structurat import proceseaza_dosar_structurat

    dosar_extras, _ = proceseaza_dosar_structurat(cale)
    return dosar_extras
