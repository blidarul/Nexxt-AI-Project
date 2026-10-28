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
    if isinstance(asteptat, list) or isinstance(extras, list):
        if not isinstance(asteptat, list) or not isinstance(extras, list) or len(asteptat) != len(extras):
            return False
        return all(_egal(a, e) for a, e in zip(asteptat, extras))
    return sunt_egale_valori(asteptat, extras)


def verifica_fixture(folder: Path) -> list[dict[str, Any]]:
    with open(folder / "expected_campuri.json", encoding="utf-8") as f:
        asteptat = json.load(f)
    cale_extras = folder / "_extras" / "dosar_extras.json"
    if not cale_extras.exists():
        return [{"camp": "(dosar)", "asteptat": "-", "extras": "lipsește _extras", "ok": False}]
    with open(cale_extras, encoding="utf-8") as f:
        extras = json.load(f)

    raport: dict[str, Any] = {}
    if (folder / "_extras" / "raport_extractie.json").exists():
        with open(folder / "_extras" / "raport_extractie.json", encoding="utf-8") as f:
            raport = json.load(f)

    rezultate = []
    for camp in ("categorie", "subcategorie"):
        if camp not in asteptat:
            continue
        val = _valoare(extras, camp)
        rezultate.append({"camp": camp, "asteptat": asteptat[camp], "extras": val, "ok": _egal(asteptat[camp], val)})
    if "categorie_ambigua" in asteptat:
        val = raport.get("categorie_ambigua")
        rezultate.append({"camp": "(raport) categorie_ambigua", "asteptat": asteptat["categorie_ambigua"], "extras": val,
                          "ok": val is asteptat["categorie_ambigua"]})
    if "categorie_candidati" in asteptat:
        candidati = raport.get("categorie_candidati") or []
        val = sorted(c["categorie"] for c in candidati)
        rezultate.append({"camp": "(raport) categorie_candidati", "asteptat": sorted(asteptat["categorie_candidati"]),
                          "extras": val, "ok": val == sorted(asteptat["categorie_candidati"])})
        increderi = [c["incredere"] for c in candidati]
        rezultate.append({"camp": "(raport) încredere candidați < 0.7", "asteptat": True, "extras": increderi,
                          "ok": bool(increderi) and all(i < 0.7 for i in increderi)})
    if "documente_lipsa_contine" in asteptat:
        ids = {d["id"] for d in raport.get("documente_lipsa") or []}
        for i in asteptat["documente_lipsa_contine"]:
            rezultate.append({"camp": f"(raport) documente_lipsa ∋ {i}", "asteptat": True, "extras": i in ids, "ok": i in ids})
    if "conversii_contin" in asteptat:
        unitati = {c.get("unitate_originala") for c in raport.get("conversii_unitati") or []}
        for u in asteptat["conversii_contin"]:
            rezultate.append({"camp": f"(raport) conversie din {u}", "asteptat": True, "extras": u in unitati, "ok": u in unitati})
    if "pagini_ocr_minim" in asteptat:
        nr_ocr = 0
        for cale in (folder / "_brut").glob("*.json"):
            if cale.name == "index.json":
                continue
            with open(cale, encoding="utf-8") as f:
                nr_ocr += sum(1 for p in json.load(f).get("pagini", []) if p.get("ocr") and p.get("text"))
        rezultate.append({"camp": "(brut) pagini transcrise prin OCR", "asteptat": f">= {asteptat['pagini_ocr_minim']}",
                          "extras": nr_ocr, "ok": nr_ocr >= asteptat["pagini_ocr_minim"]})
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
