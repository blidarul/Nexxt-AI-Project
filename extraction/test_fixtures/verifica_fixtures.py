"""Compară _extras/dosar_extras.json al fiecărui fixture cu expected_campuri.json.

Rulare: python -m extraction.test_fixtures.verifica_fixtures [fx_nume ...]
"""

import json
from pathlib import Path
import sys
from typing import Any

from extraction.compara import normalizeaza_text_comparare, sunt_egale_valori

FOLDER = Path(__file__).resolve().parent


def _valoare(date: dict[str, Any], cale: str) -> Any:
    nod: Any = date
    for parte in cale.split("."):
        if not isinstance(nod, dict):
            return None
        nod = nod.get(parte)
    if isinstance(nod, dict) and "valoare" in nod:
        return nod["valoare"]
    return nod


def _egal(asteptat: Any, extras: Any) -> bool:
    if isinstance(asteptat, bool) or isinstance(extras, bool):
        return asteptat is extras
    return sunt_egale_valori(asteptat, extras)


def verifica_fixture(folder: Path) -> list[dict[str, Any]]:
    with open(folder / "expected_campuri.json", encoding="utf-8") as f:
        asteptat = json.load(f)
    cale_extras = folder / "_extras" / "dosar_extras.json"
    if not cale_extras.exists():
        return [{"camp": "(dosar)", "asteptat": "-", "extras": "lipsește _extras", "ok": False}]
    with open(cale_extras, encoding="utf-8") as f:
        extras = json.load(f)

    rezultate = []
    for camp in ("categorie", "subcategorie"):
        val = _valoare(extras, camp)
        rezultate.append({"camp": camp, "asteptat": asteptat[camp], "extras": val, "ok": _egal(asteptat[camp], val)})
    for camp, val_asteptata in asteptat.get("campuri", {}).items():
        val = _valoare(extras, camp)
        rezultate.append({"camp": camp, "asteptat": val_asteptata, "extras": val, "ok": _egal(val_asteptata, val)})
    for camp, spec in asteptat.get("liste", {}).items():
        lista = _valoare(extras, camp) or []
        chei = spec["cheie"]
        for rand_asteptat in spec["randuri"]:
            identitate = " ".join(str(rand_asteptat[k]) for k in chei)
            rand = next((r for r in lista if all(
                normalizeaza_text_comparare(rand_asteptat[k]) == normalizeaza_text_comparare(r.get(k)) for k in chei
            )), None)
            for k, v in rand_asteptat.items():
                if k in chei:
                    continue
                val = rand.get(k) if rand else None
                rezultate.append({"camp": f"{camp}[{identitate}].{k}", "asteptat": v, "extras": val, "ok": _egal(v, val)})
        rezultate.append({"camp": f"{camp} (nr. modele)", "asteptat": len(spec["randuri"]), "extras": len(lista),
                          "ok": len(lista) == len(spec["randuri"])})
    return rezultate


def main() -> None:
    nume = sys.argv[1:] or sorted(p.name for p in FOLDER.iterdir() if (p / "expected_campuri.json").exists())
    total_ok = total = 0
    for n in nume:
        rezultate = verifica_fixture(FOLDER / n)
        ok = sum(r["ok"] for r in rezultate)
        total_ok += ok
        total += len(rezultate)
        print(f"== {n}: {ok}/{len(rezultate)} corecte")
        for r in rezultate:
            print(f"  {'OK ' if r['ok'] else 'GREȘIT'} {r['camp']:<55} așteptat={r['asteptat']!r:<28} extras={r['extras']!r}")
    print(f"TOTAL: {total_ok}/{total}")


if __name__ == "__main__":
    main()
