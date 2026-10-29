"""Raportul de la pasul 2, construit determinist din rezultatul agentului (Verdict) și din rules/*.yaml.

Nu recalculează verdictul și nu adaugă afirmații proprii: fiecare rând vine dintr-un rezultat de regulă,
dintr-o acțiune a agentului, din impactul calculat de agent sau dintr-un document lipsă din extracție.
Din rules/*.yaml (și reference/plauzibilitate.yaml) se iau doar numele lizibil al regulii, pagina din
Framework și grupul ei (condiții generale, criteriile categoriei, excluderi, plauzibilitate).
"""

from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

RADACINA = Path(__file__).resolve().parent.parent

GRUPURI = {
    "conditii_generale": "Condiții generale",
    "categorie": "Criteriile categoriei",
    "excluderi": "Excluderi",
    "plauzibilitate": "Verificări de plauzibilitate",
}
ORDINE_GRUPURI = list(GRUPURI)

# Numele categoriilor, ca în Framework
CATEGORII = {
    "green_buildings": "Green Buildings",
    "renewable_energy": "Renewable Energy",
    "energy_efficiency": "Energy Efficiency",
    "clean_transportation": "Clean Transportation",
    "pollution_prevention": "Pollution Prevention and Control",
    "circular_economy": "Circular Economy",
}

ETICHETA_REZULTAT = {
    "OK": "Îndeplinită",
    "NU": "Neîndeplinită",
    "SEMNAL": "Semnal",
    "NEEVALUABIL": "Neevaluabilă",
    "OK_CONDITIONAT": "Îndeplinită condiționat",
}
INDEPLINITE = {"OK"}
NEINDEPLINITE = {"NU"}
DE_VERIFICAT = {"SEMNAL", "NEEVALUABIL", "OK_CONDITIONAT"}

_ID_REGULA = re.compile(r"\b[A-Z]{1,3}-[A-Z]?\d+[a-z]?\b")


# ------------------------------------------------------------------ regulile din yaml

@lru_cache(maxsize=4)
def reguli_cunoscute(radacina: Path = RADACINA) -> dict[str, dict[str, str]]:
    """ID -> {nume, sursa, grup}, din rules/*.yaml și reference/plauzibilitate.yaml."""
    rezultat: dict[str, dict[str, str]] = {}

    def parcurge(nod: Any, grup: str) -> None:
        if isinstance(nod, dict):
            if isinstance(nod.get("id"), str) and isinstance(nod.get("nume"), str):
                rezultat.setdefault(nod["id"], {"nume": nod["nume"], "sursa": str(nod.get("sursa") or ""), "grup": grup})
            for cheie, valoare in nod.items():
                parcurge(valoare, "excluderi" if cheie == "excluderi" else grup)
        elif isinstance(nod, list):
            for valoare in nod:
                parcurge(valoare, grup)

    for cale in sorted((radacina / "rules").glob("*.yaml")):
        with open(cale, encoding="utf-8") as f:
            date = yaml.safe_load(f)
        parcurge(date, "conditii_generale" if cale.stem == "conditii_generale" else "categorie")
    plauzibilitate = radacina / "reference" / "plauzibilitate.yaml"
    if plauzibilitate.is_file():
        with open(plauzibilitate, encoding="utf-8") as f:
            parcurge(yaml.safe_load(f), "plauzibilitate")
    return rezultat


def grup_regula(regula_id: str, cunoscute: dict[str, dict[str, str]]) -> str:
    if regula_id in cunoscute:
        return cunoscute[regula_id]["grup"]
    # o regulă care nu e în yaml: grupul după forma ID-ului
    if regula_id.startswith("PL-"):
        return "plauzibilitate"
    if re.match(r"^(G|P)-", regula_id):
        return "conditii_generale"
    if re.match(r"^[A-Z]+-X", regula_id):
        return "excluderi"
    return "categorie"


def eticheta_pagina(sursa: str) -> str:
    """„Framework p.7, nota 6” -> „p. 7, nota 6”; „Anexa B, p. 26” rămâne așa."""
    text = re.sub(r"^\s*(RBI Sustainability Bond )?Framework[^,]*?(?=p\.|$)", "", sursa or "").strip(" ,")
    text = re.sub(r"\bp\.\s*(\d)", r"p. \1", text)
    return text or (sursa or "").strip()


# ------------------------------------------------------------------ raportul

def _element_regula(regula: dict[str, Any], cunoscute: dict[str, dict[str, str]]) -> dict[str, Any]:
    regula_id = regula.get("regula_id", "")
    meta = cunoscute.get(regula_id, {})
    pagina = eticheta_pagina(regula.get("sursa_framework") or meta.get("sursa", ""))
    return {
        "tip": "regula",
        "id": regula_id,
        "nume": meta.get("nume") or regula_id,
        "rezultat": regula.get("rezultat"),
        "eticheta_rezultat": ETICHETA_REZULTAT.get(regula.get("rezultat"), regula.get("rezultat")),
        "dovada": regula.get("dovada") or "",
        "pagina": pagina,
        "grup": grup_regula(regula_id, cunoscute),
    }


def _grupeaza(elemente: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grupuri = []
    for cheie in ORDINE_GRUPURI:
        din_grup = [e for e in elemente if e["grup"] == cheie]
        if din_grup:
            grupuri.append({"cheie": cheie, "titlu": GRUPURI[cheie], "elemente": din_grup})
    return grupuri


def _lista_nume(elemente: list[dict[str, Any]]) -> str:
    parti = [f"{e['id']} „{e['nume']}” ({e['pagina']})" if e["pagina"] else f"{e['id']} „{e['nume']}”" for e in elemente]
    if len(parti) <= 1:
        return "".join(parti)
    return ", ".join(parti[:-1]) + " și " + parti[-1]


def _format_numar(valoare: float, zecimale: int = 1) -> str:
    text = f"{valoare:,.{zecimale}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def _concluzie(verdict: dict[str, Any], elemente: list[dict[str, Any]], categorie: str) -> list[str]:
    tip = verdict.get("verdict")
    pe_id = {e["id"]: e for e in elemente}
    cat = [e for e in elemente if e["grup"] == "categorie"]
    excluderi = [e for e in elemente if e["grup"] == "excluderi"]

    # calea: ID-ul numit de agent în cale_eligibilitate, altfel prima regulă a categoriei îndeplinită
    cale_text = verdict.get("cale_eligibilitate") or ""
    id_cale = next((m for m in _ID_REGULA.findall(cale_text) if m in pe_id), None)
    if id_cale is None:
        id_cale = next((e["id"] for e in cat if e["rezultat"] in ("OK", "OK_CONDITIONAT")), None)
    cale = pe_id.get(id_cale) if id_cale else None
    detaliu = re.search(r"\(([^)]*)\)", cale_text)
    descriere_cale = ""
    if cale:
        descriere_cale = f"{cale['id']} „{cale['nume']}”" + (f" ({cale['pagina']})" if cale["pagina"] else "")
        if detaliu:
            descriere_cale += f": {detaliu.group(1)}"

    propozitii: list[str] = []
    if tip == "ELIGIBIL":
        propozitii.append(f"Dosarul îndeplinește criteriile categoriei {categorie}"
                          + (f" pe calea {descriere_cale}." if cale else "."))
    elif tip == "ELIGIBIL_CU_MONITORIZARE":
        conditionate = [e for e in elemente if e["rezultat"] == "OK_CONDITIONAT"]
        if conditionate:
            propozitii.append(f"Dosarul poate fi inclus în categoria {categorie}, cu monitorizare: {_lista_nume(conditionate)}.")
        else:
            propozitii.append(f"Dosarul poate fi inclus în categoria {categorie}, cu monitorizare"
                              + (f", pe calea {descriere_cale}." if cale else "."))
    elif tip == "NEELIGIBIL":
        # întâi condițiile obligatorii care nu trec; criteriile categoriei doar dacă nicio cale nu a trecut
        obligatorii = [e for e in elemente if e["rezultat"] == "NU" and e["grup"] in ("conditii_generale", "excluderi")]
        cauze = obligatorii or [e for e in cat if e["rezultat"] == "NU"]
        if cauze:
            detalii = "; ".join(f"{e['id']} „{e['nume']}” nu e îndeplinită ({e['dovada']})"
                                + (f", {e['pagina']}" if e["pagina"] else "") for e in cauze)
            propozitii.append(f"Dosarul nu poate fi inclus: {detalii}.")
        else:
            propozitii.append("Dosarul nu poate fi inclus.")
    elif tip == "EXCEPTIE_ESCALADARE_COMITET":
        semnale = [e for e in elemente if e["rezultat"] == "SEMNAL"]
        if semnale:
            verb = "a ridicat" if len(semnale) == 1 else "au ridicat"
            propozitii.append(f"Dosarul nu poate fi decis automat: {_lista_nume(semnale)} {verb} un semnal "
                              "care cere evaluarea comitetului.")
        else:
            propozitii.append("Dosarul nu poate fi decis automat și cere evaluarea comitetului.")
        if cale and cale["rezultat"] in ("OK", "OK_CONDITIONAT"):
            propozitii.append(f"Criteriile categoriei {categorie} sunt îndeplinite pe calea "
                              f"{cale['id']}" + (f" ({cale['pagina']})." if cale["pagina"] else "."))

    if tip in ("ELIGIBIL", "ELIGIBIL_CU_MONITORIZARE") and excluderi:
        if all(e["rezultat"] == "OK" for e in excluderi):
            propozitii.append("Nu s-au găsit excluderi.")
    impact = verdict.get("impact_tco2_an")
    if isinstance(impact, (int, float)):
        propozitii.append(f"Impact estimat: {_format_numar(impact)} tCO₂/an.")
    return propozitii


def _impact(verdict: dict[str, Any]) -> Optional[dict[str, Any]]:
    valoare = verdict.get("impact_tco2_an")
    if not isinstance(valoare, (int, float)):
        return None
    detalii = verdict.get("impact_detalii") or {}
    mwh = next((detalii[k] for k in ("mwh_an", "energie_mwh_an", "rezultat_mwh_an") if isinstance(detalii.get(k), (int, float))), None)
    return {
        "tco2_an": valoare,
        "mwh_an": mwh,
        "formula": detalii.get("formula") or "",
        "sursa": detalii.get("sursa") or "",
        "pasi": list(detalii.get("pasi") or []),
        # agentul marchează factorii de exemplu în „atentie”
        "proxy": bool(detalii.get("atentie")),
        "atentie": detalii.get("atentie") or "",
    }


def construieste_raport(
    verdict: dict[str, Any],
    categorie: Optional[str] = None,
    documente_lipsa: Optional[list[dict[str, Any]]] = None,
    radacina: Path = RADACINA,
) -> dict[str, Any]:
    """Raportul structurat: concluzie, secțiuni (fără cele goale), impact, referințe."""
    cunoscute = reguli_cunoscute(radacina)
    elemente = [_element_regula(r, cunoscute) for r in verdict.get("reguli") or []]
    nume_categorie = CATEGORII.get(categorie or "", categorie or "categoriei")

    sectiuni = []
    for cheie, titlu, semn, rezultate in (
        ("indeplinite", "Ce îndeplinește", "✓", INDEPLINITE),
        ("neindeplinite", "Ce nu îndeplinește", "✗", NEINDEPLINITE),
        ("de_verificat", "De verificat", "!", DE_VERIFICAT),
    ):
        grupuri = _grupeaza([e for e in elemente if e["rezultat"] in rezultate])
        if cheie == "de_verificat":
            actiuni = [{"tip": "actiune", "text": a} for a in verdict.get("actiuni") or []]
            if actiuni:
                grupuri.append({"cheie": "actiuni", "titlu": "Acțiuni propuse de agent", "elemente": actiuni})
            lipsa = [{"tip": "document", "id": d.get("id", ""), "nume": d.get("nume", ""),
                      "obligatoriu": bool(d.get("obligatoriu", True)), "actiune": "de solicitat clientului"}
                     for d in documente_lipsa or []]
            if lipsa:
                grupuri.append({"cheie": "documente_lipsa", "titlu": f"Documente lipsă ({len(lipsa)})", "elemente": lipsa})
        if grupuri:
            sectiuni.append({"cheie": cheie, "titlu": titlu, "semn": semn, "grupuri": grupuri})

    impact = _impact(verdict)
    referinte: list[str] = []
    for e in elemente:
        if e["pagina"] and e["pagina"] not in referinte:
            referinte.append(e["pagina"])
    if impact and impact["sursa"] and impact["sursa"] not in referinte:
        referinte.append(impact["sursa"])

    return {
        "dosar": verdict.get("dosar_id"),
        "verdict": verdict.get("verdict"),
        "categorie": nume_categorie,
        "concluzie": _concluzie(verdict, elemente, nume_categorie),
        "sectiuni": sectiuni,
        "impact": impact,
        "referinte": referinte,
    }


# ------------------------------------------------------------------ varianta printabilă

def ca_html(raport: dict[str, Any], titlu: str, salvat_la: str = "") -> str:
    """Aceeași structură ca în pagină, ca document HTML de printat (sau salvat ca PDF din print)."""
    e = html.escape

    def element(x: dict[str, Any]) -> str:
        if x["tip"] == "regula":
            return (f"<li><span class='id'>{e(x['id'])}</span> <b>{e(x['nume'])}</b> · {e(x['eticheta_rezultat'])}"
                    f"<br><span>{e(x['dovada'])}</span>" + (f" <span class='p'>{e(x['pagina'])}</span>" if x["pagina"] else "") + "</li>")
        if x["tip"] == "document":
            return f"<li><span class='id'>{e(x['id'])}</span> {e(x['nume'])} · <span class='p'>{e(x['actiune'])}</span></li>"
        return f"<li>{e(x['text'])}</li>"

    parti = [f"<h2>Concluzie</h2>" + "".join(f"<p>{e(p)}</p>" for p in raport["concluzie"])]
    for s in raport["sectiuni"]:
        corp = "".join(f"<h3>{e(g['titlu'])}</h3><ul>{''.join(element(x) for x in g['elemente'])}</ul>" for g in s["grupuri"])
        parti.append(f"<h2>{e(s['semn'])} {e(s['titlu'])}</h2>{corp}")
    if raport["impact"]:
        i = raport["impact"]
        rand = f"<p><b>{_format_numar(i['tco2_an'])} tCO₂/an</b>"
        if i["mwh_an"] is not None:
            rand += f" · {_format_numar(i['mwh_an'])} MWh/an"
        rand += "</p>"
        metoda = " · ".join(x for x in (f"formula RBI: {i['formula']}" if i["formula"] else "", i["sursa"]) if x)
        parti.append("<h2>Impact</h2>" + rand + (f"<p>{e(metoda)}</p>" if metoda else "")
                     + (f"<ol>{''.join(f'<li>{e(p)}</li>' for p in i['pasi'])}</ol>" if i["pasi"] else "")
                     + ("<p class='p'>Valori de referință aproximative (proxy).</p>" if i["proxy"] else ""))
    if raport["referinte"]:
        parti.append("<h2>Referințe Framework</h2><p>" + " · ".join(e(r) for r in raport["referinte"]) + "</p>")
    stampila = f" · rezultat din {e(salvat_la)}" if salvat_la else ""
    return f"""<!doctype html>
<html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raport · {e(titlu)}</title>
<style>
  body {{ max-width: 760px; margin: 40px auto; padding: 0 24px; font: 14px/1.5 system-ui, sans-serif; color: #0a0a0a; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }} h2 {{ font-size: 15px; margin: 28px 0 8px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  h3 {{ font-size: 13px; color: #5c5b58; margin: 12px 0 4px; font-weight: 500; }}
  ul, ol {{ margin: 0; padding-left: 20px; }} li {{ margin: 4px 0; }} .id {{ font-family: ui-monospace, monospace; }}
  .p, .meta {{ color: #5c5b58; }} .tiparire {{ margin-top: 32px; }}
  @media print {{ .tiparire {{ display: none; }} body {{ margin: 0; }} }}
</style></head>
<body>
<h1>{e(titlu)}</h1>
<p class="meta">Green Proof · raport generat din rezultatul agentului{stampila}</p>
{''.join(parti)}
<p class="tiparire"><button onclick="print()">Printează / salvează ca PDF</button></p>
</body></html>"""
