"""Șterge din extraction/.cache/ intrările produse de simulatorul offline.

O intrare e considerată simulată dacă simulatorul, rulat pe aceleași mesaje,
produce exact același răspuns. Rulare: python -m extraction.curata_cache [--dry-run]
"""

import json
from pathlib import Path
import sys
from typing import Optional

from extraction.llm_client import LLMClient

# Blocul <think> cu care simulatorul își începe răspunsurile de extragere.
MARKER_SIMULATOR = "<think>\nAnalizăm documentul și extragem câmpurile solicitate."


def gaseste_intrari_simulate(cache_dir: Optional[Path] = None) -> list[Path]:
    """Întoarce fișierele de cache al căror răspuns coincide cu cel al simulatorului."""
    client = LLMClient(cache_dir=cache_dir)
    simulate = []
    for fisier in sorted(client.cache_dir.glob("*.json")):
        try:
            with open(fisier, "r", encoding="utf-8") as f:
                intrare = json.load(f)
        except Exception:
            continue
        raspuns = str(intrare.get("raspuns") or "")
        if raspuns.startswith(MARKER_SIMULATOR):
            simulate.append(fisier)  # scris de o versiune mai veche a simulatorului
            continue
        mesaje = intrare.get("mesaje") or []
        if not mesaje or any(not isinstance(m.get("content"), str) for m in mesaje):
            continue  # vision / format necunoscut: simulatorul nu le produce
        if client._genereaza_raspuns_offline(mesaje, intrare.get("model", "")) == intrare.get("raspuns"):
            simulate.append(fisier)
    return simulate


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    simulate = gaseste_intrari_simulate()
    for f in simulate:
        print(f"{'[dry-run] ' if dry_run else ''}șterg {f.name}")
        if not dry_run:
            f.unlink()
    print(f"Intrări simulate: {len(simulate)}")


if __name__ == "__main__":
    main()
