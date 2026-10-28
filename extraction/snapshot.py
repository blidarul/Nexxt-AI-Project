"""Snapshot de non-regresie: dosar_extras.json al celor 4 dosare, produs cu LLM-ul real.

Referința de corectitudine rămâne extras_mock.json (python -m extraction.compara). Snapshot-ul prinde
orice altă schimbare (indicatori, categorie, surse, încredere) între rulări.

Rulare:
    python -m extraction.snapshot salveaza   # după o rulare verificată cu compara (4/4)
    python -m extraction.snapshot verifica   # diferențele față de snapshot
"""

import json
from pathlib import Path
import shutil
import sys
from typing import Any

RADACINA = Path(__file__).resolve().parent.parent
FOLDER_DOSARE = RADACINA / "dosare"
FOLDER_SNAPSHOT = Path(__file__).resolve().parent / "snapshot_nonregresie"


def _dosare() -> list[Path]:
    return sorted(p for p in FOLDER_DOSARE.iterdir() if (p / "extras_mock.json").exists())


def _diferente(a: Any, b: Any, cale: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        rez = []
        for k in sorted(set(a) | set(b)):
            rez.extend(_diferente(a.get(k), b.get(k), f"{cale}.{k}" if cale else k))
        return rez
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        rez = []
        for i, (x, y) in enumerate(zip(a, b)):
            rez.extend(_diferente(x, y, f"{cale}[{i}]"))
        return rez
    return [] if a == b else [f"{cale}: snapshot={a!r} acum={b!r}"]


def salveaza() -> None:
    FOLDER_SNAPSHOT.mkdir(exist_ok=True)
    for d in _dosare():
        shutil.copyfile(d / "_extras" / "dosar_extras.json", FOLDER_SNAPSHOT / f"{d.name}.json")
        print(f"Salvat: {d.name}")


def verifica() -> int:
    total = 0
    for d in _dosare():
        with open(FOLDER_SNAPSHOT / f"{d.name}.json", encoding="utf-8") as f:
            vechi = json.load(f)
        with open(d / "_extras" / "dosar_extras.json", encoding="utf-8") as f:
            nou = json.load(f)
        dif = _diferente(vechi, nou)
        total += len(dif)
        print(f"{d.name}: {'identic' if not dif else f'{len(dif)} diferențe'}")
        for linie in dif:
            print(f"  {linie}")
    return total


def main() -> None:
    actiune = sys.argv[1] if len(sys.argv) > 1 else "verifica"
    if actiune == "salveaza":
        salveaza()
    else:
        sys.exit(1 if verifica() else 0)


if __name__ == "__main__":
    main()
