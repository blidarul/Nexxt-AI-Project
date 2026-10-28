"""Descarcă datele EEA „CO2 emissions from new passenger cars” și scrie tools/data/emisii_vehicule.csv.

Păstrează marca (Mk), denumirea comercială (Cn), combustibilul (Ft) și emisiile WLTP (Ewltp (g/km)),
agregă pe (marcă, model, combustibil) cu mediana emisiilor (ponderată cu numărul de înmatriculări) și păstrează
cele mai înmatriculate modele (--top). Rândurile SINTETICE existente (fixture-urile) rămân în fișier.

Surse:
    implicit       API-ul SQL Discodata al EEA (tabelul din --tabel)
    --din-fisier   CSV-ul descărcat manual de pe EEA Datahub („Monitoring of CO2 emissions from passenger cars”)

Rulare:
    python -m tools.data.descarca_eea
    python -m tools.data.descarca_eea --din-fisier C:/descarcari/data.zip            # arhiva, fără dezarhivare
    python -m tools.data.descarca_eea --din-fisier data.zip --tara RO                # doar înmatriculările din România
    python -m tools.data.descarca_eea --din-fisier data.zip --max-randuri 200000     # probă rapidă

Fișierul EEA are zeci de milioane de rânduri (câțiva GB): se citește în flux, doar coloanele necesare,
cu memorie constantă (pe model se numără valorile distincte de emisii, nu fiecare mașină).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

from tools._comun import fara_marca, normalizeaza_cheie

URL_DISCODATA = "https://discodata.eea.europa.eu/sql"
TABEL_IMPLICIT = "[CO2Emission].[latest].[co2cars_2025Pv31]"
CALE_IESIRE = Path(__file__).resolve().parent / "emisii_vehicule.csv"
COLOANE = ["marca", "model", "combustibil", "emisii_wltp_gco2_km", "an_date", "nr_inmatriculari", "sursa", "alias_marca"]
PREFIX_SINTETIC = "SINTETIC"
PAGINA = 10000

# Numele coloanelor din datele EEA (CSV-ul de pe Datahub și tabelul Discodata)
ALIAS_COLOANE = {
    "marca": ["mk"],
    "model": ["cn"],
    "combustibil": ["ft"],
    "emisii": ["ewltp (g/km)", "ewltp"],
    "an": ["year"],
    # EEA pune hibridele simple și plug-in la același Ft („petrol/electric”) și la același Fm (P);
    # plug-in-ul se recunoaște după autonomia electrică / consumul electric completate
    "autonomie_electrica": ["electric range (km)"],
    "consum_electric": ["z (wh/km)"],
}
COLOANE_OPTIONALE = {"an", "autonomie_electrica", "consum_electric"}


EXPR_PLUG_IN = "CASE WHEN [Electric range (km)] IS NOT NULL OR [z (Wh/km)] IS NOT NULL THEN 1 ELSE 0 END"


def _interogare_agregata(tabel: str) -> str:
    return (
        f"SELECT Mk, Cn, Ft, {EXPR_PLUG_IN} AS PlugIn, [Ewltp (g/km)] AS Ewltp, MAX(Year) AS Year, COUNT(*) AS Nr "
        f"FROM {tabel} WHERE [Ewltp (g/km)] IS NOT NULL AND Cn IS NOT NULL AND Mk IS NOT NULL "
        f"GROUP BY Mk, Cn, Ft, {EXPR_PLUG_IN}, [Ewltp (g/km)]"
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
                   "plug_in": bool(rand.get("PlugIn")), "emisii": rand.get("Ewltp"), "an": rand.get("Year"),
                   "nr": rand.get("Nr") or 1}
        if len(rezultate) < PAGINA:
            return
        pagina += 1


@contextmanager
def _deschide_text(cale: Path) -> Iterator[io.TextIOBase]:
    """CSV simplu sau arhiva .zip descărcată de pe EEA Datahub (citită în flux, fără dezarhivare)."""
    if cale.suffix.lower() != ".zip":
        with open(cale, encoding="utf-8-sig", errors="replace", newline="") as f:
            yield f
        return
    with zipfile.ZipFile(cale) as arhiva:
        csv_uri = sorted((i for i in arhiva.infolist() if i.filename.lower().endswith((".csv", ".txt"))),
                         key=lambda i: -i.file_size)
        if not csv_uri:
            raise SystemExit(f"EROARE: arhiva {cale.name} nu conține niciun fișier .csv / .txt.")
        with arhiva.open(csv_uri[0]) as brut:
            yield io.TextIOWrapper(brut, encoding="utf-8-sig", errors="replace", newline="")


def citeste_fisier(cale: Path, tara: Optional[str] = None, max_randuri: Optional[int] = None,
                   raport_la: int = 1_000_000) -> Iterator[dict]:
    """Rândurile CSV-ului EEA (un rând = o mașină înmatriculată), citite în flux.

    Fișierul poate avea zeci de milioane de rânduri: se citesc doar coloanele necesare, rând cu rând,
    direct din .zip. Opțional, doar înmatriculările dintr-o țară (coloana Ms, ex. RO).
    """
    if not cale.exists():
        raise SystemExit(f"EROARE: fișierul {cale} nu există.")
    with _deschide_text(cale) as f:
        mostra = f.readline()
        try:
            separator = csv.Sniffer().sniff(mostra, delimiters=",	;").delimiter
        except csv.Error:
            separator = ","
        antet = next(csv.reader([mostra], delimiter=separator))
        pozitii = {c.strip().lower(): i for i, c in enumerate(antet)}
        coloane = {cheie: next((pozitii[a] for a in aliasuri if a in pozitii), None)
                   for cheie, aliasuri in ALIAS_COLOANE.items()}
        lipsa = [k for k, v in coloane.items() if v is None and k not in COLOANE_OPTIONALE]
        if lipsa:
            raise SystemExit(f"EROARE: în {cale.name} lipsesc coloanele EEA pentru {lipsa} (antet: {antet}).")
        col_tara = pozitii.get("ms", pozitii.get("country"))  # Discodata: Ms; CSV-ul de pe Datahub: Country
        if tara and col_tara is None:
            raise SystemExit(f"EROARE: filtrul --tara cere coloana Ms sau Country, care lipsește din {cale.name}.")
        tara = tara.strip().upper() if tara else None
        maxim = max(coloane[k] for k in coloane if coloane[k] is not None)

        for nr, rand in enumerate(csv.reader(f, delimiter=separator), start=1):
            if max_randuri and nr > max_randuri:
                break
            if raport_la and nr % raport_la == 0:
                print(f"  ... {nr:,} rânduri citite", file=sys.stderr, flush=True)
            if len(rand) <= maxim or (tara and rand[col_tara].strip().upper() != tara):
                continue
            yield {k: (rand[i] if i is not None else None) for k, i in coloane.items()} | {"nr": 1}


def _mediana_ponderata(valori: Iterable[tuple[float, int]]) -> float:
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


def este_plug_in(rand: dict) -> bool:
    """Hibrid cu autonomie electrică sau consum electric declarat = plug-in (OVC-HEV)."""
    if "plug_in" in rand:
        return bool(rand["plug_in"])
    hibrid = "/electric" in str(rand.get("combustibil") or "").lower()
    return hibrid and bool(str(rand.get("autonomie_electrica") or "").strip() or str(rand.get("consum_electric") or "").strip())


def eticheta_combustibil(ft: object, plug_in: bool = False) -> str:
    """„petrol/electric” plug-in -> „petrol/electric (plug-in)”; altfel combustibilul EEA, cu litere mici."""
    eticheta = " ".join(str(ft or "").split()).lower()
    if plug_in and "/electric" in eticheta:
        eticheta = f"{eticheta} (plug-in)"
    return eticheta


def agrega(randuri: Iterable[dict], top: int, sursa: str) -> list[dict]:
    """Agregă pe (marcă, model, combustibil): mediana emisiilor WLTP și ultimul an.

    - mărcile scrise diferit („MERCEDES-BENZ” / „MERCEDES - BENZ”) intră în același grup;
    - marca se scoate din numele modelului („TOYOTA COROLLA” -> „COROLLA”), iar o marcă dată ca listă
      („VOLKSWAGEN, VW”) devine prima denumire;
    - versiunile cu combustibili diferiți rămân separate: mediana unui model care are și plug-in
      (≈25 g/km) și diesel (≈170 g/km) nu ar descrie niciuna dintre versiuni.
    Memorie constantă: pentru fiecare grup se numără valorile distincte de emisii, nu fiecare mașină.
    """
    grupuri: dict[tuple[str, str, str], dict] = defaultdict(
        lambda: {"emisii": Counter(), "model": Counter(), "an": None, "nr": 0})
    grafii_marca: dict[str, Counter] = defaultdict(Counter)  # aceeași grafie a mărcii pentru toate modelele ei
    alias_marca: dict[str, set[str]] = defaultdict(set)      # celelalte denumiri din sursă („VW” pentru VOLKSWAGEN)
    for rand in randuri:
        # unele mărci vin ca listă de denumiri („VOLKSWAGEN, VW”): prima e marca, toate se scot din model
        denumiri = [" ".join(x.split()).upper() for x in str(rand.get("marca") or "").split(",") if x.strip()]
        marca = denumiri[0] if denumiri else ""
        model = " ".join(str(rand.get("model") or "").split()).upper()
        for denumire in denumiri:
            model = fara_marca(model, denumire)
        try:
            emisii = float(str(rand.get("emisii")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if not marca or not model:
            continue
        combustibil = eticheta_combustibil(rand.get("combustibil"), este_plug_in(rand))
        nr = int(rand.get("nr") or 1)
        g = grupuri[(normalizeaza_cheie(marca), normalizeaza_cheie(model), combustibil)]
        g["emisii"][emisii] += nr
        grafii_marca[normalizeaza_cheie(marca)][marca] += nr
        alias_marca[normalizeaza_cheie(marca)].update(denumiri[1:])
        g["model"][model] += nr
        g["nr"] += nr
        try:
            an = int(float(rand["an"])) if rand.get("an") not in (None, "") else None
        except (TypeError, ValueError):
            an = None
        if an and (g["an"] is None or an > g["an"]):
            g["an"] = an

    rezultat = []
    for (cheie_marca, _, combustibil), g in sorted(grupuri.items(), key=lambda x: -x[1]["nr"])[:top]:
        rezultat.append({
            "marca": grafii_marca[cheie_marca].most_common(1)[0][0], "model": g["model"].most_common(1)[0][0],
            "combustibil": combustibil,
            "emisii_wltp_gco2_km": round(_mediana_ponderata(g["emisii"].items()), 1), "an_date": g["an"],
            "nr_inmatriculari": g["nr"], "sursa": sursa, "alias_marca": ";".join(sorted(alias_marca[cheie_marca])),
        })
    return sorted(rezultat, key=lambda r: (r["marca"], r["model"], r["combustibil"]))


def randuri_sintetice() -> list[dict]:
    if not CALE_IESIRE.exists():
        return []
    with open(CALE_IESIRE, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if str(r.get("sursa", "")).startswith(PREFIX_SINTETIC)]


def scrie(randuri_reale: list[dict]) -> None:
    sintetice = randuri_sintetice()  # citite înainte ca fișierul să fie deschis (și golit) pentru scriere
    with open(CALE_IESIRE, "w", encoding="utf-8", newline="") as f:
        scriitor = csv.DictWriter(f, fieldnames=COLOANE)
        scriitor.writeheader()
        scriitor.writerows(sintetice)
        scriitor.writerows(randuri_reale)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--din-fisier", type=Path, help="CSV-ul EEA descărcat manual")
    parser.add_argument("--tabel", default=TABEL_IMPLICIT, help="tabelul Discodata (implicit: %(default)s)")
    parser.add_argument("--top", type=int, default=300, help="câte modele (cele mai înmatriculate) se păstrează")
    parser.add_argument("--tara", help="doar înmatriculările dintr-o țară (coloana Ms, ex. RO); doar cu --din-fisier")
    parser.add_argument("--max-randuri", type=int, help="citește doar primele N rânduri (probă rapidă)")
    args = parser.parse_args(argv)

    if args.din_fisier:
        sursa = f"EEA CO2 passenger cars ({args.din_fisier.name}{', ' + args.tara.upper() if args.tara else ''})"
        randuri = citeste_fisier(args.din_fisier, tara=args.tara, max_randuri=args.max_randuri)
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
