"""Citirea regulilor: categorii permise, documente și câmpuri cerute, tipuri de documente.

Sursa de adevăr: rules/*.yaml, rules/cerinte_dosar.yaml, extraction/tipuri_documente.yaml,
extraction/categorii.yaml. Nicio listă de categorii, câmpuri sau documente nu e scrisă aici.
"""

from functools import lru_cache
from pathlib import Path
import re
from typing import Any, Optional

import yaml

RADACINA = Path(__file__).resolve().parent.parent
FOLDER_RULES = RADACINA / "rules"
FOLDER_EXTRACTION = Path(__file__).resolve().parent


def _citeste_yaml(cale: Path) -> Any:
    with open(cale, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def incarca_cerinte() -> dict[str, Any]:
    return _citeste_yaml(FOLDER_RULES / "cerinte_dosar.yaml")


@lru_cache(maxsize=None)
def incarca_config_categorii() -> dict[str, Any]:
    return _citeste_yaml(FOLDER_EXTRACTION / "categorii.yaml")


@lru_cache(maxsize=None)
def incarca_tipuri_documente() -> dict[str, dict[str, Any]]:
    return _citeste_yaml(FOLDER_EXTRACTION / "tipuri_documente.yaml")["tipuri"]


def _ca_lista(valoare: Any) -> list:
    if valoare is None:
        return []
    return list(valoare) if isinstance(valoare, (list, tuple, set)) else [valoare]


def _colecteaza_aplica_daca(nod: Any, rezultat: list[dict[str, Any]]) -> None:
    if isinstance(nod, dict):
        if isinstance(nod.get("aplica_daca"), dict):
            rezultat.append(nod["aplica_daca"])
        for v in nod.values():
            _colecteaza_aplica_daca(v, rezultat)
    elif isinstance(nod, list):
        for x in nod:
            _colecteaza_aplica_daca(x, rezultat)


@lru_cache(maxsize=None)
def incarca_categorii() -> dict[str, dict[str, Any]]:
    """Categoriile din rules/*.yaml, cu valorile permise.

    Ieșire: {categorie: {"subcategorii": [...], "camp_subcategorie": "tip" | None,
                         "nivel_3": {subcategorie: {"camp": "tip_masura", "valori": [...]}}}}
    """
    config = incarca_config_categorii()
    ignorate = set(config.get("fisiere_ignorate", []))
    categorii: dict[str, dict[str, Any]] = {}

    for cale in sorted(FOLDER_RULES.glob("*.yaml")):
        if cale.name in ignorate:
            continue
        date = _citeste_yaml(cale) or {}
        nume = date.get("categorie")
        if not nume:
            continue

        subcategorii: list[str] = []
        for cheie in config["chei_subcategorii"]:
            if cheie in date:
                subcategorii = [str(s) for s in date[cheie]]
                break

        # Câmpul care poartă subcategoria: cheia aplica_daca ale cărei valori sunt toate subcategorii
        conditii: list[dict[str, Any]] = []
        _colecteaza_aplica_daca(date, conditii)
        frecventa: dict[str, int] = {}
        for cond in conditii:
            for k, v in cond.items():
                valori = _ca_lista(v)
                if valori and all(str(x) in subcategorii for x in valori):
                    frecventa[k] = frecventa.get(k, 0) + 1
        camp_subcategorie = max(frecventa, key=frecventa.get) if frecventa else None

        # Al treilea nivel: blocuri de subcategorie cu `camp_tip`
        nivel_3: dict[str, dict[str, Any]] = {}
        for sub in subcategorii:
            bloc = date.get(sub)
            if isinstance(bloc, dict) and bloc.get("camp_tip"):
                camp_tip = bloc["camp_tip"]
                conditii_bloc: list[dict[str, Any]] = []
                _colecteaza_aplica_daca(bloc, conditii_bloc)
                valori: list[str] = []
                for cond in conditii_bloc:
                    for x in _ca_lista(cond.get(camp_tip)):
                        if str(x) not in valori:
                            valori.append(str(x))
                nivel_3[sub] = {"camp": camp_tip, "valori": valori}

        categorii[nume] = {
            "subcategorii": subcategorii,
            "camp_subcategorie": camp_subcategorie,
            "nivel_3": nivel_3,
        }

    return categorii


def _bloc_categorie(categorie: str, subcategorie: Optional[str]) -> list[dict[str, Any]]:
    """Blocurile din cerinte_dosar.yaml (cu documente/campuri) aplicabile categoriei."""
    cerinte = incarca_cerinte()
    blocuri = [cerinte.get("comun", {})]
    nod = cerinte.get(categorie)
    if not isinstance(nod, dict):
        return blocuri
    if "campuri" in nod or "documente" in nod:
        blocuri.append(nod)
    elif subcategorie and isinstance(nod.get(subcategorie), dict):
        blocuri.append(nod[subcategorie])
    return blocuri


def _se_aplica(intrare: dict[str, Any], valori_active: set[str]) -> bool:
    doar = _ca_lista(intrare.get("doar_pentru"))
    return not doar or any(str(d) in valori_active for d in doar)


def documente_cerute(categorie: Optional[str], subcategorie: Optional[str]) -> list[dict[str, Any]]:
    """Documentele (cu ID) cerute pentru categorie/subcategorie, inclusiv cele comune."""
    rezultat = []
    for bloc in _bloc_categorie(categorie or "", subcategorie):
        rezultat.extend(bloc.get("documente", []) or [])
    return rezultat


def campuri_cerute(
    categorie: Optional[str],
    subcategorie: Optional[str],
    tip_nivel_3: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Câmpurile cerute (intrările din cerinte_dosar.yaml), filtrate după doar_pentru.

    Un câmp cu doar_pentru se păstrează doar dacă subcategoria sau tipul de nivel 3 se potrivesc.
    Același câmp care apare de două ori (ex. în comun și în categorie) apare o singură dată,
    cu documentele reunite.
    """
    active = {v for v in (subcategorie, tip_nivel_3) if v}
    vazute: dict[str, dict[str, Any]] = {}
    for bloc in _bloc_categorie(categorie or "", subcategorie):
        for intrare in bloc.get("campuri", []) or []:
            if not _se_aplica(intrare, active):
                continue
            nume = intrare["camp"]
            if nume in vazute:
                for d in _ca_lista(intrare.get("document")):
                    if d not in vazute[nume]["document"]:
                        vazute[nume]["document"].append(d)
                continue
            copie = dict(intrare)
            copie["document"] = list(_ca_lista(intrare.get("document")))
            vazute[nume] = copie
    return list(vazute.values())


def este_obligatoriu(intrare: dict[str, Any]) -> bool:
    """În cerinte_dosar.yaml, un câmp/document e obligatoriu dacă nu are obligatoriu: false."""
    return intrare.get("obligatoriu", True) is not False


def tipuri_pentru_id(id_document: str) -> list[str]:
    """Tipurile de document care pot acoperi un ID din cerinte_dosar.yaml."""
    rezultat = []
    for tip, info in incarca_tipuri_documente().items():
        if id_document in (info.get("id_cerinte") or []):
            rezultat.append(tip)
    return rezultat


def id_pentru_document(
    tip_document: str,
    rol: Optional[str],
    id_permise: set[str],
) -> list[str]:
    """ID-urile din cerinte acoperite de un document clasificat, restrânse la categoria dosarului."""
    info = incarca_tipuri_documente().get(tip_document, {})
    ids = [i for i in (info.get("id_cerinte") or []) if i in id_permise]
    roluri = info.get("roluri") or {}
    if roluri and len(ids) > 1:
        ids_cu_rol = set()
        for lista in roluri.values():
            ids_cu_rol.update(lista)
        if rol in roluri:
            # păstrează ID-urile rolului detectat + cele care nu țin de vreun rol
            ids = [i for i in ids if i in roluri[rol] or i not in ids_cu_rol]
        else:
            # fără rol detectat: ID-urile fără rol (ex. EPC simplu -> GB-D2)
            fara_rol = [i for i in ids if i not in ids_cu_rol]
            ids = fara_rol or ids
    return ids


def interpreteaza_obligativitate(
    valoare: Any,
    subcategorie: Optional[str],
    tip_nivel_3: Optional[str],
) -> dict[str, Any]:
    """Interpretează câmpul `obligatoriu` al unui document din cerinte_dosar.yaml.

    Forme: true / false / "una_din: [A, B]" / "doar <valori>" / alt text (ex. "pentru impact").
    Ieșire: {"fel": "obligatoriu" | "una_din" | "conditionat" | "recomandat" | "optional",
             "grup": [...] (una_din), "conditie": text, "se_aplica": bool}
    "doar <valori>" se aplică dacă vreun cuvânt din condiție apare în subcategorie sau tipul de nivel 3.
    """
    if valoare is True or valoare is None:
        return {"fel": "obligatoriu", "se_aplica": True}
    if valoare is False:
        return {"fel": "optional", "se_aplica": False}
    text = str(valoare).strip()
    m = re.match(r"una_din:\s*\[(.*)\]", text)
    if m:
        grup = [x.strip() for x in m.group(1).split(",") if x.strip()]
        return {"fel": "una_din", "grup": grup, "conditie": text, "se_aplica": True}
    if text.lower().startswith("doar "):
        cuvinte = [c for c in re.split(r"[,\s]+", text[5:].lower()) if len(c) >= 3]
        tinte = " ".join(v for v in (subcategorie, tip_nivel_3) if v).lower()
        return {"fel": "conditionat", "conditie": text, "se_aplica": any(c in tinte for c in cuvinte)}
    return {"fel": "recomandat", "conditie": text, "se_aplica": False}


def evalueaza_documente(
    categorie: Optional[str],
    subcategorie: Optional[str],
    tip_nivel_3: Optional[str],
    documente_clasificate: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Documentele găsite (pe ID) și cele lipsă pentru categoria dată.

    Folosește `id_cerinte` stabilit pe fiecare document clasificat.
    """
    fisiere_pe_id: dict[str, list[str]] = {}
    for doc in documente_clasificate:
        for i in doc.get("id_cerinte") or []:
            fisiere_pe_id.setdefault(i, []).append(doc.get("fisier"))

    cerute = documente_cerute(categorie, subcategorie)
    gasite, lipsa, recomandate_lipsa = [], [], []
    grupuri_verificate: set[tuple[str, ...]] = set()
    for d in cerute:
        if d["id"] in fisiere_pe_id:
            gasite.append({"id": d["id"], "nume": d.get("nume"), "fisiere": fisiere_pe_id[d["id"]]})
            continue
        regula = interpreteaza_obligativitate(d.get("obligatoriu"), subcategorie, tip_nivel_3)
        intrare = {"id": d["id"], "nume": d.get("nume"), "obligatoriu": d.get("obligatoriu", True)}
        if regula["fel"] == "obligatoriu":
            lipsa.append(intrare)
        elif regula["fel"] == "una_din":
            cheie = tuple(regula["grup"])
            if cheie in grupuri_verificate:
                continue
            grupuri_verificate.add(cheie)
            if not any(i in fisiere_pe_id for i in regula["grup"]):
                lipsa.append({**intrare, "id": " sau ".join(regula["grup"]), "motiv": "niciunul din grup"})
        elif regula["fel"] == "conditionat" and regula["se_aplica"]:
            lipsa.append({**intrare, "conditie": regula["conditie"]})
        elif regula["fel"] in ("recomandat", "conditionat"):
            recomandate_lipsa.append({**intrare, "conditie": regula.get("conditie")})
    return {"documente_gasite": gasite, "documente_lipsa": lipsa, "documente_recomandate_lipsa": recomandate_lipsa}


def toate_id_documentele() -> set[str]:
    """Toate ID-urile de documente din cerinte_dosar.yaml."""
    ids: set[str] = set()

    def _viziteaza(nod: Any) -> None:
        if isinstance(nod, dict):
            if "documente" in nod:
                for d in nod["documente"] or []:
                    ids.add(d["id"])
            for v in nod.values():
                _viziteaza(v)
        elif isinstance(nod, list):
            for x in nod:
                _viziteaza(x)

    _viziteaza(incarca_cerinte())
    return ids
