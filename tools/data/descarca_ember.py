"""Descarcă intensitatea carbon a electricității (Ember, prin Our World in Data) pentru țările din Anexa B.

Scrie tools/data/intensitate_carbon.csv: tara, iso3, an, gco2e_kwh, sursa.
RBI folosește Enerdata (plătit); valorile de aici sunt un PROXY public.

Rulare:
    python -m tools.data.descarca_ember
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

URL_OWID = "https://ourworldindata.org/grapher/carbon-intensity-electricity.csv"
COLOANA_VALOARE = "Carbon intensity"
SURSA = "Ember via Our World in Data (carbon-intensity-electricity)"
CALE_IESIRE = Path(__file__).resolve().parent / "intensitate_carbon.csv"
COLOANE = ["tara", "iso3", "an", "gco2e_kwh", "sursa"]


def descarca(url: str = URL_OWID, timeout: int = 60) -> str:
    import requests

    try:
        raspuns = requests.get(url, timeout=timeout)
        raspuns.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(f"EROARE: nu s-a putut descărca {url}: {exc}\n"
                         f"Verifică conexiunea la internet. Fișierul existent {CALE_IESIRE.name} nu a fost modificat.")
    return raspuns.text


def filtreaza(text_csv: str, coduri_iso3: dict[str, str]) -> list[dict[str, object]]:
    """Rândurile țărilor cerute (după codul ISO3 din coloana Code), cu valoarea numerică."""
    cititor = csv.DictReader(io.StringIO(text_csv))
    lipsa = {"Code", "Year", COLOANA_VALOARE} - set(cititor.fieldnames or [])
    if lipsa:
        raise SystemExit(f"EROARE: formatul CSV s-a schimbat, lipsesc coloanele {sorted(lipsa)} "
                         f"(găsite: {cititor.fieldnames}).")
    randuri = []
    for rand in cititor:
        cod = rand["Code"]
        if cod not in coduri_iso3 or not rand[COLOANA_VALOARE]:
            continue
        randuri.append({"tara": coduri_iso3[cod], "iso3": cod, "an": int(rand["Year"]),
                        "gco2e_kwh": float(rand[COLOANA_VALOARE]), "sursa": SURSA})
    return sorted(randuri, key=lambda r: (r["tara"], r["an"]))


def main() -> None:
    from tools.tari import corespondenta_tari, tari_anexa_b

    tari = corespondenta_tari()
    necunoscute = [t for t in tari_anexa_b() if t not in tari]
    if necunoscute:
        raise SystemExit(f"EROARE: țări din Anexa B fără corespondență în tools/data/tari.yaml: {necunoscute}")
    coduri = {tari[t]["iso3"]: tari[t]["en"] for t in tari_anexa_b()}

    randuri = filtreaza(descarca(), coduri)
    fara_date = sorted(set(coduri.values()) - {r["tara"] for r in randuri})
    with open(CALE_IESIRE, "w", encoding="utf-8", newline="") as f:
        scriitor = csv.DictWriter(f, fieldnames=COLOANE)
        scriitor.writeheader()
        scriitor.writerows(randuri)
    print(f"Scris {CALE_IESIRE.name}: {len(randuri)} rânduri, {len(coduri) - len(fara_date)} țări.")
    if fara_date:
        print(f"Atenție, fără date în sursă: {fara_date}", file=sys.stderr)


if __name__ == "__main__":
    main()
