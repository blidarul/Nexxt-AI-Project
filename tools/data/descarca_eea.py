"""Descarcă datele EEA „CO2 emissions from new passenger cars” și scrie tools/data/emisii_vehicule.csv.

Păstrează marca (Mk), denumirea comercială (Cn), combustibilul (Ft) și emisiile WLTP (Ewltp (g/km)),
agregă pe (marcă, model) cu mediana emisiilor (ponderată cu numărul de înmatriculări) și păstrează
cele mai înmatriculate modele (--top). Rândurile SINTETICE existente (fixture-urile) rămân în fișier.

Surse:
    implicit       API-ul SQL Discodata al EEA (tabelul din --tabel)
    --din-fisier   CSV-ul descărcat manual de pe EEA Datahub („Monitoring of CO2 emissions from passenger cars”)

Rulare:
    python -m tools.data.descarca_eea
    python -m tools.data.descarca_eea --din-fisier C:/descarcari/data.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Iterator

URL_DISCODATA = "https://discodata.eea.europa.eu/sql"
TABEL_IMPLICIT = "[CO2Emission].[latest].[co2cars_2025Pv31]"
CALE_IESIRE = Path(__file__).resolve().parent / "emisii_vehicule.csv"
COLOANE = ["marca", "model", "combustibil", "emisii_wltp_gco2_km", "an_date", "nr_inmatriculari", "sursa"]
PREFIX_SINTETIC = "SINTETIC"
PAGINA = 10000

# Numele coloanelor din datele EEA (CSV-ul de pe Datahub și tabelul Discodata)
ALIAS_COLOANE = {
    "marca": ["mk"],
    "model": ["cn"],
    "combustibil": ["ft"],
    "emisii": ["ewltp (g/km)", "ewltp"],
    "an": ["year"],
}


def _interogare_agregata(tabel: str) -> str:
    return (
        "SELECT Mk, Cn, Ft, [Ewltp (g/km)] AS Ewltp, MAX(Year) AS Year, COUNT(*) AS Nr "
        f"FROM {tabel} WHERE [Ewltp (g/km)] IS NOT NULL AND Cn IS NOT NULL AND Mk IS NOT NULL "
        "GROUP BY Mk, Cn, Ft, [Ewltp (g/km)]"
    )


def citeste_discodata(tabel: str, timeout: int = 120) -> Iterator[dict]:
    """Rânduri pre-agregate (marcă, model, combustibil, emisii, nr. înmatriculări), pagină cu pagină."""
    import requests

    pagina = 1
    while True:
        try:
            raspuns = requests.get(URL_DISCODATA, params={"query": _interogare_agregata(tabel), "p": pagina,
                                                          "nrOfHits": PAGINA}, timeout=timeout)
            raspuns.raise_for_status()
            rezultate = raspuns.json().get("results") or []
        except requests.RequestException as exc:
            raise SystemExit(
                f"EROARE: descărcarea din EEA Discodata a eșuat ({exc}).\n"
                "Alternativă: descarcă manual CSV-ul „Monitoring of CO2 emissions from passenger cars” de pe "
                "https://www.eea.europa.eu/en/datahub și rulează cu --din-fisier <cale>.\n"
                f"Fișierul {CALE_IESIRE.name} nu a fost modificat."
            )
        except ValueError as exc:
            raise SystemExit(f"EROARE: EEA Discodata nu a întors JSON valid ({exc}). {CALE_IESIRE.name} nu a fost modificat.")
        for rand in rezultate:
            yield {"marca": rand.get("Mk"), "model": rand.get("Cn"), "combustibil": rand.get("Ft"),
                   "emisii": rand.get("Ewltp"), "an": rand.get("Year"), "nr": rand.get("Nr") or 1}
        if len(rezultate) < PAGINA:
            return
        pagina += 1


def citeste_fisier(cale: Path) -> Iterator[dict]:
    """Rândurile CSV-ului EEA (un rând = o mașină înmatriculată). Separatorul se detectează."""
    if not cale.exists():
        raise SystemExit(f"EROARE: fișierul {cale} nu există.")
    with open(cale, encoding="utf-8-sig", newline="") as f:
        mostra = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(mostra, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        cititor = csv.DictReader(f, dialect=dialect)
        antet = {c.strip().lower(): c for c in cititor.fieldnames or []}
        coloane = {}
        for cheie, aliasuri in ALIAS_COLOANE.items():
            coloane[cheie] = next((antet[a] for a in aliasuri if a in antet), None)
        lipsa = [k for k, v in coloane.items() if v is None and k != "an"]
        if lipsa:
            raise SystemExit(f"EROARE: în {cale.name} lipsesc coloanele EEA pentru {lipsa} (antet: {cititor.fieldnames}).")
        for rand in cititor:
            yield {k: (rand.get(v) if v else None) for k, v in coloane.items()} | {"nr": 1}


def _mediana_ponderata(valori: list[tuple[float, int]]) -> float:
    valori = sorted(valori)
    total = sum(n for _, n in valori)
    acumulat = 0
    for i, (valoare, n) in enumerate(valori):
        acumulat += n
        if acumulat * 2 > total:
            return valoare
        if acumulat * 2 == total:
            return (valoare + valori[i + 1][0]) / 2
    return valori[-1][0]


def agrega(randuri: Iterable[dict], top: int, sursa: str) -> list[dict]:
    """Agregă pe (marcă, model): mediana emisiilor WLTP, combustibilul cel mai frecvent, ultimul an."""
    grupuri: dict[tuple[str, str], dict] = defaultdict(lambda: {"emisii": [], "comb": Counter(), "an": None, "nr": 0})
    for rand in randuri:
        marca, model = (str(rand.get("marca") or "").strip(), str(rand.get("model") or "").strip())
        try:
            emisii = float(str(rand.get("emisii")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if not marca or not model:
            continue
        nr = int(rand.get("nr") or 1)
        g = grupuri[(marca.upper(), model.upper())]
        g["emisii"].append((emisii, nr))
        g["comb"][str(rand.get("combustibil") or "").strip().lower()] += nr
        g["nr"] += nr
        try:
            an = int(float(rand["an"])) if rand.get("an") not in (None, "") else None
        except (TypeError, ValueError):
            an = None
        if an and (g["an"] is None or an > g["an"]):
            g["an"] = an

    rezultat = []
    for (marca, model), g in sorted(grupuri.items(), key=lambda x: -x[1]["nr"])[:top]:
        rezultat.append({
            "marca": marca, "model": model, "combustibil": g["comb"].most_common(1)[0][0],
            "emisii_wltp_gco2_km": round(_mediana_ponderata(g["emisii"]), 1), "an_date": g["an"],
            "nr_inmatriculari": g["nr"], "sursa": sursa,
        })
    return sorted(rezultat, key=lambda r: (r["marca"], r["model"]))


def randuri_sintetice() -> list[dict]:
    if not CALE_IESIRE.exists():
        return []
    with open(CALE_IESIRE, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if str(r.get("sursa", "")).startswith(PREFIX_SINTETIC)]


def scrie(randuri_reale: list[dict]) -> None:
    with open(CALE_IESIRE, "w", encoding="utf-8", newline="") as f:
        scriitor = csv.DictWriter(f, fieldnames=COLOANE)
        scriitor.writeheader()
        scriitor.writerows(randuri_sintetice())
        scriitor.writerows(randuri_reale)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--din-fisier", type=Path, help="CSV-ul EEA descărcat manual")
    parser.add_argument("--tabel", default=TABEL_IMPLICIT, help="tabelul Discodata (implicit: %(default)s)")
    parser.add_argument("--top", type=int, default=300, help="câte modele (cele mai înmatriculate) se păstrează")
    args = parser.parse_args(argv)

    if args.din_fisier:
        sursa = f"EEA CO2 passenger cars ({args.din_fisier.name})"
        randuri = citeste_fisier(args.din_fisier)
    else:
        sursa = f"EEA CO2 passenger cars (Discodata {args.tabel})"
        randuri = citeste_discodata(args.tabel)

    reale = agrega(randuri, args.top, sursa)
    if not reale:
        raise SystemExit(f"EROARE: sursa nu a întors niciun rând utilizabil. {CALE_IESIRE.name} nu a fost modificat.")
    scrie(reale)
    print(f"Scris {CALE_IESIRE.name}: {len(reale)} modele reale + rândurile sintetice păstrate.")
    print(json.dumps(reale[:3], ensure_ascii=False, indent=1), file=sys.stderr)


if __name__ == "__main__":
    main()
