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


def extrage_toate_campurile_din_reguli(folder_rules: Optional[Path] = None) -> set[str]:
    """Extrage toate numele de câmpuri menționate în fișierele rules/*.yaml."""
    if folder_rules is None:
        folder_rules = Path(__file__).resolve().parent.parent / "rules"

    campuri = set()
    for fisier_yaml in folder_rules.glob("*.yaml"):
        if fisier_yaml.name == "cerinte_dosar.yaml":
            continue
        try:
            with open(fisier_yaml, "r", encoding="utf-8") as f:
                date = yaml.safe_load(f)
        except Exception:
            continue

        def _viziteaza(nod):
            if isinstance(nod, dict):
                if "camp" in nod:
                    campuri.add(str(nod["camp"]))
                for v in nod.values():
                    _viziteaza(v)
            elif isinstance(nod, list):
                for item in nod:
                    _viziteaza(item)

        _viziteaza(date)

    return campuri


def verifica_sincronizare_catalog(
    cale_cerinte: Optional[Path] = None,
    cale_catalog: Optional[Path] = None,
) -> tuple[list[str], list[str], list[str]]:
    """Verifică sincronizarea catalogului cu cerințele de dosar și regulile.

    Returnează:
        (campuri_lipsa_din_catalog, campuri_cu_flag_gresit, campuri_informative_reguli)
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

    # 1. Câmpurile cerute trebuie să existe în catalog
    lipsa = sorted(campuri_cerinte - campuri_catalog)

    # 2. Câmpurile din cerințe trebuie să aibă extras_din_document: True
    flag_gresit = []
    for c in sorted(campuri_cerinte & campuri_catalog):
        info = date_catalog.get(c, {})
        if not info.get("extras_din_document", True):
            flag_gresit.append(c)

    # 3. Câmpuri din reguli care nu sunt în cerințe (doar informativ)
    campuri_reguli = extrage_toate_campurile_din_reguli(radacina / "rules")
    campuri_informative = sorted(campuri_reguli - campuri_cerinte)

    return lipsa, flag_gresit, campuri_informative


def main() -> None:
    """Punct de intrare CLI pentru verificarea catalogului."""
    lipsa, flag_gresit, informative = verifica_sincronizare_catalog()

    if informative:
        print(f"[INFO] Câmpuri prezente în reguli dar calculate/externe ({len(informative)}):")
        for c in informative:
            print(f"  * {c}")

    if lipsa:
        print(f"\n[EROARE] Câmpuri din cerinte_dosar.yaml lipsă din campuri.yaml ({len(lipsa)}):")
        for c in lipsa:
            print(f"  - {c}")

    if flag_gresit:
        print(f"\n[EROARE] Câmpuri din cerinte_dosar.yaml marcate greșit ca extras_din_document=False ({len(flag_gresit)}):")
        for c in flag_gresit:
            print(f"  - {c}")

    if lipsa or flag_gresit:
        sys.exit(1)

    print(f"\n[OK] Toate cele 70 de câmpuri din cerinte_dosar.yaml sunt prezente și marcate corect în catalog.")
    sys.exit(0)


if __name__ == "__main__":
    main()
