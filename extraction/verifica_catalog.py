"""Modul pentru verificarea sincronizării dintre cerinte_dosar.yaml și campuri.yaml."""

from pathlib import Path
import sys
from typing import Optional
import yaml


def extrage_campuri_din_cerinte(date_cerinte: dict) -> set[str]:
    """Extrage recursiv toate câmpurile specificate în cerinte_dosar.yaml."""
    campuri = set()

    def _viziteaza(nod):
        if isinstance(nod, dict):
            if "camp" in nod:
                campuri.add(str(nod["camp"]))
            for v in nod.values():
                _viziteaza(v)
        elif isinstance(nod, list):
            for item in nod:
                _viziteaza(item)

    _viziteaza(date_cerinte)
    return campuri


def verifica_sincronizare_catalog(
    cale_cerinte: Optional[Path] = None,
    cale_catalog: Optional[Path] = None,
) -> list[str]:
    """Verifică că toate câmpurile din cerinte_dosar.yaml există în campuri.yaml.

    Returnează lista câmpurilor lipsă (goală dacă totul este sincronizat).
    """
    radacina = Path(__file__).resolve().parent.parent

    if cale_cerinte is None:
        cale_cerinte = radacina / "rules" / "cerinte_dosar.yaml"
    if cale_catalog is None:
        cale_catalog = radacina / "extraction" / "campuri.yaml"

    with open(cale_cerinte, "r", encoding="utf-8") as f:
        date_cerinte = yaml.safe_load(f)

    with open(cale_catalog, "r", encoding="utf-8") as f:
        date_catalog = yaml.safe_load(f) or {}

    campuri_cerinte = extrage_campuri_din_cerinte(date_cerinte)
    campuri_catalog = set(date_catalog.keys())

    lipsa = sorted(campuri_cerinte - campuri_catalog)
    return lipsa


def main() -> None:
    """Punct de intrare CLI pentru verificarea catalogului."""
    lipsa = verifica_sincronizare_catalog()
    if lipsa:
        print(f"[EROARE] Câmpuri din cerinte_dosar.yaml lipsă din campuri.yaml ({len(lipsa)}):")
        for c in lipsa:
            print(f"  - {c}")
        sys.exit(1)
    else:
        print("[OK] Toate câmpurile din cerinte_dosar.yaml sunt prezente în campuri.yaml.")
        sys.exit(0)


if __name__ == "__main__":
    main()
