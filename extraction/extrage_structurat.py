"""Scriptul principal al Etapei 2/3: Extracție structurată (JSON brut -> DosarExtras).

Orchestrează:
- Asigurarea existenței _brut/
- Clasificarea conținutului documentelor (tip + rol înainte/după)
- Stabilirea categoriei și subcategoriei (din rules/*.yaml)
- Selecția câmpurilor: comun + categoria, filtrate după doar_pentru (rules/cerinte_dosar.yaml)
- Căutarea în trepte, în documentele țintă ale fiecărui câmp (ID din cerințe -> tip de document)
- Extragerea câmpurilor cu LLM și a listelor din tabele (determinist)
- Verificarea anti-halucinație a citatelor și a negațiilor (da/nu)
- Normalizarea valorilor (cu conversii de unități) și rezolvarea conflictelor
- Salvarea în _extras/dosar_extras.json și _extras/raport_extractie.json
"""

import json
from pathlib import Path
import re
import sys
from typing import Any, Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from contracts import Camp, Chirias, DosarExtras
from extraction.cautare import (
    gaseste_pagini_treapta_1,
    gaseste_pagini_treapta_2,
    grupeaza_campuri_pe_documente,
    incarca_catalog_campuri,
    normalizeaza_text_cautare,
)
from extraction.categorie import stabileste_categoria
from extraction.cerinte import (
    campuri_cerute,
    documente_cerute,
    este_obligatoriu,
    evalueaza_documente,
    id_pentru_document,
    incarca_tipuri_documente,
)
from extraction.clasificare import clasifica_document
from extraction.extrage_brut import determina_tip_din_nume, proceseaza_dosar as ruleaza_etapa_1
from extraction.extragere_campuri import (
    extrage_afirmatii_determinist,
    extrage_campuri_document_llm,
    extrage_chiriasi_determinist,
)
from extraction.llm_client import get_llm_client
from extraction.normalizare import (
    detecteaza_si_normalizeaza_unitate,
    normalizeaza_camp,
    normalizeaza_da_nu,
    normalizeaza_numar,
    valideaza_valoare,
)
from extraction.tabele import (
    UNITATI_CONVERTITE,
    aplica_document_autoritate,
    extrage_din_document_autoritate,
    extrage_lista_din_tabele,
    extrage_lista_llm,
)
from extraction.verificare import (
    calculeaza_incredere_finala,
    rezolva_conflicte_camp,
    verifica_citat,
    verifica_da_nu,
)

# Câmpurile de nivel superior din DosarExtras (Etapa 2); restul merg în DosarExtras.indicatori
CAMPURI_TOP_LEVEL = {
    "cui", "suma_eur", "cota_banca", "data_aprobare", "tara",
    "adresa_cladire", "suprafata_m2", "stadiu_cladire", "nr_certificat_declarat",
    "epc_clasa", "epc_energie_finala", "epc_suprafata_m2", "afirmatii_client",
}

# Mapare de compatibilitate pentru numele vechi întoarse de LLM
ALIASURI_ETAPA2 = {
    "epc_energie_finala": "energie_finala_kwh_m2",
    "epc_suprafata_m2": "suprafata_m2",
}

TIPURI_LISTA = {"lista", "lista_chiriasi"}

# Valoarea cu citat reconstituit determinist (LLM-ul nu a dat citat) are încrederea redusă
FACTOR_CITAT_RECONSTITUIT = 0.8

# campuri.yaml: metoda pentru câmpurile extrase determinist, fără LLM
METODA_AFIRMATII = "determinist_afirmatii"

# raport_extractie.campuri_lipsa: chiriaș găsit, dar fără cod CAEN în document
MOTIV_CAEN_LIPSA_CHIRIAS = "caen_lipsa_chirias"


def incarca_documente_brute(folder_dosar: Path) -> list[dict[str, Any]]:
    """Încarcă toate fișierele JSON brute generate în Etapa 1."""
    folder_brut = folder_dosar / "_brut"
    if not folder_brut.exists():
        ruleaza_etapa_1(folder_dosar)

    documente = []
    for p in sorted(folder_brut.glob("*.json")):
        if p.name == "index.json":
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
                documente.append(doc)
        except Exception as e:
            print(f"[AVERTISMENT] Nu s-a putut citi {p}: {e}", file=sys.stderr)

    return documente


def selecteaza_campuri(candidati_categorie: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Câmpurile cerute pentru toți candidații de categorie (reunite) și ID-urile de documente permise."""
    selectate: dict[str, dict[str, Any]] = {}
    id_permise: set[str] = set()
    candidati = candidati_categorie or [{"categorie": None, "subcategorie": None, "tip_nivel_3": None}]
    for cand in candidati:
        for intrare in campuri_cerute(cand["categorie"], cand["subcategorie"], cand.get("tip_nivel_3")):
            nume = intrare["camp"]
            if nume in selectate:
                for d in intrare["document"]:
                    if d not in selectate[nume]["document"]:
                        selectate[nume]["document"].append(d)
            else:
                selectate[nume] = intrare
        id_permise.update(d["id"] for d in documente_cerute(cand["categorie"], cand["subcategorie"]))
    return selectate, id_permise


def documente_tinta(
    intrare_cerinte: dict[str, Any],
    info_catalog: dict[str, Any],
    documente: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Documentele în care se caută un câmp: după ID (cerințe + catalog) sau după tip (catalog vechi)."""
    tipuri_cunoscute = incarca_tipuri_documente()
    ids = set(intrare_cerinte.get("document") or [])
    tipuri: set[str] = set()
    for x in info_catalog.get("documente_probabile") or []:
        (tipuri if x in tipuri_cunoscute else ids).add(x)
    return [
        d for d in documente
        if d.get("tip_document") in tipuri or ids.intersection(d.get("id_cerinte") or [])
    ]


def reconstituie_citat(valoare_bruta: Any, cuvinte_cheie: list[str], doc: dict[str, Any]) -> Optional[str]:
    """Când LLM-ul dă o valoare fără citat: linia unică din document care conține valoarea
    și un cuvânt-cheie al câmpului. Dacă nu există exact o astfel de linie, nu se reconstituie nimic.
    """
    valoare = normalizeaza_text_cautare(str(valoare_bruta)).strip()
    if not valoare or isinstance(valoare_bruta, (list, dict)):
        return None
    chei = [normalizeaza_text_cautare(k) for k in cuvinte_cheie if k]
    potriviri = []
    for pag in doc.get("pagini", []):
        for linie in (pag.get("text") or "").splitlines():
            linie_norm = normalizeaza_text_cautare(linie)
            if valoare in linie_norm and any(k in linie_norm for k in chei):
                potriviri.append(linie.strip())
    return potriviri[0] if len(set(potriviri)) == 1 else None


def citat_contine_cuvant_cheie(citat: str, cuvinte_cheie: list[str]) -> bool:
    """Pentru câmpurile cu sens precis (citat_cu_cuvant_cheie în campuri.yaml): citatul trebuie
    să conțină una din expresiile câmpului (fără diacritice, fără diferențe de majuscule)."""
    citat_norm = normalizeaza_text_cautare(citat)
    return any(k and normalizeaza_text_cautare(k) in citat_norm for k in cuvinte_cheie)


def aliniaza_valoare_cu_citatul(camp: str, valoare_bruta: Any, citat: str) -> Any:
    """Dacă numărul dat de LLM nu apare în citat (LLM-ul a convertit singur, ex. „4,8” din „4.800 kW”),
    caută în citat un număr cu unitate care, normalizat, dă aceeași valoare și îl folosește ca valoare brută.
    Așa conversia se face (și se raportează) în cod. Dacă nu există o astfel de potrivire, nu schimbă nimic.
    """
    text = str(valoare_bruta).strip()
    if not citat or re.sub(r"\s+", "", text) in re.sub(r"\s+", "", citat):
        return valoare_bruta
    tinta, _ = detecteaza_si_normalizeaza_unitate(camp, text)
    if not isinstance(tinta, (int, float)) or isinstance(tinta, bool):
        return valoare_bruta
    for m in re.finditer(r"\d[\d.,]*\s*[^\d\s|;,()]{0,12}", citat):
        val, _ = detecteaza_si_normalizeaza_unitate(camp, m.group(0))
        if isinstance(val, (int, float)) and not isinstance(val, bool) and abs(val - tinta) <= 1e-6 * max(1.0, abs(tinta)):
            numar = re.match(r"[\d.,]+", m.group(0)).group(0).rstrip(".,")
            # același număr, alt format (ex. 1.38 / 1,38): fără conversie, se păstrează doar numărul
            return numar if normalizeaza_numar(numar) == tinta else m.group(0).strip()
    return valoare_bruta


def normalizeaza_valoare(
    camp: str,
    info_catalog: dict[str, Any],
    valoare_bruta: Any,
    citat: str,
) -> tuple[Any, Optional[str], Optional[str]]:
    """Normalizează valoarea unui câmp. Întoarce (valoare, motiv_respingere, unitate_convertita).

    Câmpurile din Etapa 2 trec prin normalizeaza_camp, neschimbat. Câmpurile noi numerice trec prin
    conversia de unități, iar cele da/nu prin verificarea negațiilor din citat.
    """
    tip = info_catalog.get("tip")
    validare = info_catalog.get("validare")

    if tip == "da_nu":
        val = normalizeaza_da_nu(valoare_bruta)
        if val is None:
            return None, f"valoare da/nu nerecunoscută: '{valoare_bruta}'", None
        val, motiv = verifica_da_nu(val, citat)
        return val, motiv, None

    if camp not in CAMPURI_TOP_LEVEL and tip in ("numar", "procent"):
        val, unitate = detecteaza_si_normalizeaza_unitate(camp, str(valoare_bruta))
        if not isinstance(val, (int, float)) or isinstance(val, bool) or val is None:
            return None, f"Nu s-a putut normaliza valoarea brută: '{valoare_bruta}' pentru tipul '{tip}'", None
        valid, motiv = valideaza_valoare(val, validare)
        if not valid:
            return None, motiv, None
        return val, None, (unitate if unitate in UNITATI_CONVERTITE else None)

    val, motiv = normalizeaza_camp(camp_nume=camp, valoare_bruta=valoare_bruta, tip_camp=tip, reguli_validare=validare)
    return val, motiv, None


def _adauga_candidati_llm(
    extrase_llm: dict[str, Any],
    date_grup: dict[str, Any],
    treapta: int,
    candidati_per_camp: dict[str, list[dict[str, Any]]],
    treapta_gasire: dict[str, int],
) -> None:
    fisier = date_grup["fisier"]
    for camp_raw, val_info in extrase_llm.items():
        camp = ALIASURI_ETAPA2.get(camp_raw, camp_raw)
        if camp not in candidati_per_camp:
            continue
        if camp == "afirmatii_client" and isinstance(val_info, list):
            candidati_per_camp[camp].append({
                "fisier": fisier,
                "tip_document": date_grup["tip_document"],
                "valoare_bruta": val_info,
                "citat": "Declarații ale solicitantului privind sustenabilitatea",
                "pagina": 1,
                "incredere_llm": 0.95,
                "treapta": treapta,
                "doc_complet": date_grup["doc"],
            })
            treapta_gasire[camp] = treapta
            continue
        if not isinstance(val_info, dict):
            continue
        val_text = val_info.get("valoare_text")
        if val_text is None or str(val_text).strip().lower() in ("null", "none", ""):
            continue
        try:
            pagina = int(val_info.get("pagina", 1))
        except (TypeError, ValueError):
            pagina = 1
        try:
            incredere = float(val_info.get("incredere", 0.9 if treapta == 1 else 0.85))
        except (TypeError, ValueError):
            incredere = 0.85
        candidati_per_camp[camp].append({
            "fisier": fisier,
            "tip_document": date_grup["tip_document"],
            "valoare_bruta": val_text,
            "citat": val_info.get("citat", ""),
            "pagina": pagina,
            "incredere_llm": incredere,
            "treapta": treapta,
            "doc_complet": date_grup["doc"],
        })
        treapta_gasire[camp] = treapta


def extrage_lista(
    camp: str,
    info_catalog: dict[str, Any],
    docs_tinta: list[dict[str, Any]],
    documente_clasificate: list[dict[str, Any]],
    llm_client: Any,
) -> Optional[dict[str, Any]]:
    """Lista dintr-un câmp de tip 'lista': tabel determinist, apoi documentele de autoritate (ex. CoC).

    LLM-ul se folosește pentru listă doar dacă nu există tabel recognoscibil.
    """
    tip_autoritate = info_catalog.get("document_autoritate")
    surse_lista = [d for d in docs_tinta if d.get("tip_document") != tip_autoritate] or docs_tinta
    rezultat = extrage_lista_din_tabele(camp, info_catalog, surse_lista)
    if rezultat is None:
        for doc in surse_lista:
            rezultat = extrage_lista_llm(camp, info_catalog, doc, llm_client)
            if rezultat:
                break
    if rezultat is None:
        return None

    if tip_autoritate:
        autoritate = []
        for doc in documente_clasificate:
            if doc.get("tip_document") == tip_autoritate:
                date_auto = extrage_din_document_autoritate(camp, info_catalog, doc, llm_client)
                if date_auto:
                    autoritate.append(date_auto)
                    rezultat["conversii"].extend(date_auto["conversii"])
        rezultat["conflicte"].extend(aplica_document_autoritate(rezultat["valoare"], autoritate, info_catalog))
        surse_auto = sorted({a["sursa"] for a in autoritate})
        if surse_auto:
            rezultat["sursa"] += "; " + ", ".join(surse_auto)
        for rand in rezultat["valoare"]:
            rand.pop("_surse_autoritate", None)
    return rezultat


def proceseaza_dosar_structurat(folder_dosar: Path) -> tuple[DosarExtras, dict[str, Any]]:
    """Execută întregul flux de extracție structurată pentru un dosar."""
    dosar_id = folder_dosar.name
    llm_client = get_llm_client()
    catalog_campuri = incarca_catalog_campuri()
    statistici_start = llm_client.get_statistici()
    index_apeluri_start = len(llm_client.apeluri_reale_detalii)

    # 1. Încarcă documentele din Etapa 1
    documente_brute = incarca_documente_brute(folder_dosar)

    # 2. Clasificarea documentelor pe baza conținutului
    documente_clasificate = []
    raport_documente = []

    for doc in documente_brute:
        clasif = clasifica_document(doc, llm_client=llm_client)
        doc_clasif = dict(doc)
        doc_clasif["tip_document"] = clasif["tip_document"]
        doc_clasif["rol"] = clasif.get("rol")
        doc_clasif["incredere_clasificare"] = clasif["incredere"]
        documente_clasificate.append(doc_clasif)

        # Numele fișierului e doar indiciu (raportat); tipul folosit e cel din conținut
        tip_din_nume = determina_tip_din_nume(doc.get("fisier") or "")
        raport_documente.append({
            "fisier": doc.get("fisier"),
            "tip_detectat": clasif["tip_document"],
            "tip_din_continut": clasif["tip_document"],
            "tip_din_nume": tip_din_nume,
            "nume_contrazice_continut": tip_din_nume is not None and tip_din_nume != clasif["tip_document"],
            "rol": clasif.get("rol"),
            "incredere": clasif["incredere"],
            "motiv": clasif["motiv"],
        })

    # 3. Categoria proiectului și selecția câmpurilor
    rezultat_categorie = stabileste_categoria(documente_clasificate, llm_client=llm_client)
    candidati_categorie = rezultat_categorie["candidati"]
    selectate, id_permise = selecteaza_campuri(candidati_categorie)

    for doc, rap in zip(documente_clasificate, raport_documente):
        doc["id_cerinte"] = id_pentru_document(doc["tip_document"], doc.get("rol"), id_permise)
        rap["id_cerinte"] = doc["id_cerinte"]

    # Câmpurile stabilite de categorie (nu se extrag separat)
    campuri_din_categorie = {"categorie", "subcategorie"}
    for cand in candidati_categorie:
        campuri_din_categorie.update(c for c in (cand.get("camp_subcategorie"), cand.get("camp_nivel_3")) if c)

    campuri_de_extras = [
        c for c in selectate
        if c not in campuri_din_categorie and catalog_campuri.get(c, {}).get("extras_din_document", True)
    ]
    campuri_lista = [c for c in campuri_de_extras if catalog_campuri.get(c, {}).get("tip") in TIPURI_LISTA]
    campuri_scalare = [c for c in campuri_de_extras if c not in campuri_lista]
    # Câmpurile cu extragere deterministă dedicată nu trec prin LLM
    campuri_deterministe = [c for c in campuri_scalare if catalog_campuri.get(c, {}).get("metoda") == METODA_AFIRMATII]
    campuri_llm = [c for c in campuri_scalare if c not in campuri_deterministe]

    def este_camp_obligatoriu(camp: str) -> bool:
        return este_obligatoriu(selectate[camp]) or bool(catalog_campuri.get(camp, {}).get("obligatoriu", False))

    candidati_per_camp: dict[str, list[dict[str, Any]]] = {c: [] for c in campuri_scalare}
    treapta_gasire: dict[str, int] = {}
    valori_respinse = []
    documente_incercate: dict[str, set[str]] = {}

    # --- TREAPTA 1 (Țintită: documentele cerute pentru câmp) ---
    alocari_t1 = {}
    for camp in campuri_llm:
        info_c = catalog_campuri.get(camp, {})
        tinta = documente_tinta(selectate[camp], info_c, documente_clasificate)
        documente_incercate[camp] = {d.get("fisier") for d in tinta}
        info_tinta = dict(info_c, documente_probabile=sorted({d["tip_document"] for d in tinta}))
        pagini_t1 = gaseste_pagini_treapta_1(camp, info_tinta, tinta)
        if pagini_t1:
            alocari_t1[camp] = pagini_t1

    for fisier, date_grup in grupeaza_campuri_pe_documente(alocari_t1).items():
        extrase_llm = extrage_campuri_document_llm(
            fisier=fisier,
            pagini=date_grup["pagini"],
            campuri=date_grup["campuri"],
            catalog_campuri=catalog_campuri,
            llm_client=llm_client,
        )
        _adauga_candidati_llm(extrase_llm, date_grup, 1, candidati_per_camp, treapta_gasire)

    # --- TREAPTA 2 (Extinsă: câmpuri obligatorii lipsă, în restul documentelor) ---
    # Câmpurile cu cautare_extinsa: false (ex. date cu sens precis) rămân doar în documentele lor.
    campuri_lipsa_t1 = [
        c for c in campuri_llm
        if este_camp_obligatoriu(c) and not candidati_per_camp[c]
        and catalog_campuri.get(c, {}).get("cautare_extinsa", True) is not False
    ]
    if campuri_lipsa_t1:
        alocari_t2 = {}
        for camp in campuri_lipsa_t1:
            pagini_t2 = gaseste_pagini_treapta_2(
                camp, catalog_campuri.get(camp, {}), documente_clasificate,
                documente_deja_incercate=documente_incercate.get(camp, set()),
            )
            if pagini_t2:
                alocari_t2[camp] = pagini_t2

        for fisier, date_grup in grupeaza_campuri_pe_documente(alocari_t2).items():
            extrase_llm = extrage_campuri_document_llm(
                fisier=fisier,
                pagini=date_grup["pagini"],
                campuri=date_grup["campuri"],
                catalog_campuri=catalog_campuri,
                llm_client=llm_client,
            )
            _adauga_candidati_llm(extrase_llm, date_grup, 2, candidati_per_camp, treapta_gasire)

    # --- Verificarea anti-halucinație, normalizarea și calculul încrederii ---
    campuri_finale_valide: dict[str, list[dict[str, Any]]] = {c: [] for c in campuri_scalare}
    conversii_unitati = []
    campuri_ambigue: dict[str, dict[str, Any]] = {}

    for camp, lista_candidati in candidati_per_camp.items():
        info_c = catalog_campuri.get(camp, {})
        doc_probabile = set(info_c.get("documente_probabile") or []) | set(selectate[camp].get("document") or [])

        for cand in lista_candidati:
            if camp == "afirmatii_client" and isinstance(cand["valoare_bruta"], list):
                campuri_finale_valide[camp].append({
                    "valoare_normalizata": cand["valoare_bruta"],
                    "sursa": f"{cand['fisier']}, p.1",
                    "incredere": 1.0,
                    "citat": cand["citat"],
                    "citat_verificat": True,
                    "treapta": cand["treapta"],
                    "fisier": cand["fisier"],
                    "tip_document": cand["tip_document"],
                })
                continue

            citat = cand.get("citat", "") or ""
            citat_reconstituit = False
            if not citat.strip():
                citat = reconstituie_citat(cand["valoare_bruta"], info_c.get("cuvinte_cheie") or [], cand.get("doc_complet", {})) or ""
                citat_reconstituit = bool(citat)
            citat_gasit, pag_reala, sursa_calc = verifica_citat(citat, cand.get("pagina", 1), cand.get("doc_complet", {}))

            if not citat_gasit:
                valori_respinse.append({
                    "camp": camp,
                    "valoare_bruta": cand["valoare_bruta"],
                    "citat": citat,
                    "fisier": cand["fisier"],
                    "motiv": "citat_negasit",
                })
                continue

            if info_c.get("citat_cu_cuvant_cheie") and not citat_contine_cuvant_cheie(citat, info_c.get("cuvinte_cheie") or []):
                valori_respinse.append({
                    "camp": camp,
                    "valoare_bruta": cand["valoare_bruta"],
                    "citat": citat,
                    "fisier": cand["fisier"],
                    "motiv": "citat_fara_cuvant_cheie",
                })
                continue

            if camp not in CAMPURI_TOP_LEVEL and info_c.get("tip") in ("numar", "procent"):
                cand["valoare_bruta"] = aliniaza_valoare_cu_citatul(camp, cand["valoare_bruta"], citat)
            val_norm, motiv_norm, unitate_conv = normalizeaza_valoare(camp, info_c, cand["valoare_bruta"], citat)

            if val_norm is None:
                valori_respinse.append({
                    "camp": camp,
                    "valoare_bruta": cand["valoare_bruta"],
                    "citat": citat,
                    "fisier": cand["fisier"],
                    "motiv": motiv_norm if motiv_norm == "citat ambiguu" else f"normalizare_sau_validare_esuata: {motiv_norm}",
                })
                if motiv_norm == "citat ambiguu":
                    campuri_ambigue[camp] = {"citat": citat, "sursa": sursa_calc or f"{cand['fisier']}, p.{pag_reala}"}
                continue

            doc_c = cand.get("doc_complet", {})
            este_doc_probabil = (
                cand["tip_document"] in doc_probabile
                or bool(doc_probabile.intersection(doc_c.get("id_cerinte") or []))
            )
            pagina_citat = next((p for p in doc_c.get("pagini", []) if p.get("pagina") == pag_reala), {})
            incredere_calc = calculeaza_incredere_finala(
                incredere_llm=cand["incredere_llm"],
                citat_verificat=True,
                normalizare_reusita=True,
                este_document_probabil=este_doc_probabil,
                provine_din_ocr=bool(pagina_citat.get("ocr")),
            )
            if citat_reconstituit:
                incredere_calc = round(incredere_calc * FACTOR_CITAT_RECONSTITUIT, 2)
            sursa = sursa_calc or f"{cand['fisier']}, p.{pag_reala}"

            campuri_finale_valide[camp].append({
                "valoare_normalizata": val_norm,
                "valoare_bruta": cand["valoare_bruta"],
                "sursa": sursa,
                "incredere": incredere_calc,
                "citat": citat,
                "citat_verificat": True,
                "treapta": cand["treapta"],
                "fisier": cand["fisier"],
                "tip_document": cand["tip_document"],
                "unitate_originala": unitate_conv,
                "citat_reconstituit": citat_reconstituit,
            })

    # --- Rezolvarea conflictelor și selecția valorilor unice ---
    valori_selectate: dict[str, Optional[dict[str, Any]]] = {}
    conflicte_totale = []

    for camp in campuri_scalare:
        ales, conf = rezolva_conflicte_camp(camp, campuri_finale_valide[camp], catalog_campuri)
        valori_selectate[camp] = ales
        if conf:
            conflicte_totale.extend(conf)
        if ales:
            campuri_ambigue.pop(camp, None)  # alt candidat a dat o valoare clară
            if ales.get("unitate_originala"):
                conversii_unitati.append({
                    "camp": camp,
                    "valoare_bruta": ales["valoare_bruta"],
                    "unitate_originala": ales["unitate_originala"],
                    "valoare": ales["valoare_normalizata"],
                    "sursa": ales["sursa"],
                })

    # --- Câmpuri deterministe (afirmațiile clientului) ---
    for camp in campuri_deterministe:
        tinta = documente_tinta(selectate[camp], catalog_campuri.get(camp, {}), documente_clasificate)
        afirmatii, sursa_af, citate_af = extrage_afirmatii_determinist(tinta, catalog_campuri.get(camp, {}))
        valori_selectate[camp] = {
            "valoare_normalizata": afirmatii,
            "sursa": sursa_af or "",
            "incredere": 1.0,
            "citat": "; ".join(citate_af),
            "citat_verificat": True,
            "treapta": 1,
            "metoda": METODA_AFIRMATII,
        } if afirmatii else None

    # --- Liste: chiriași (determinist, Etapa 2) și liste din tabele (ex. vehicule) ---
    chiriasi_extrasi, sursa_chiriasi, citat_chiriasi = [], None, None
    liste_extrase: dict[str, dict[str, Any]] = {}
    for camp in campuri_lista:
        info_c = catalog_campuri.get(camp, {})
        tinta = documente_tinta(selectate[camp], info_c, documente_clasificate)
        if info_c.get("tip") == "lista_chiriasi":
            chiriasi_extrasi, sursa_chiriasi, citat_chiriasi = extrage_chiriasi_determinist(tinta or documente_clasificate)
            continue
        if not tinta:
            continue
        rezultat_lista = extrage_lista(camp, info_c, tinta, documente_clasificate, llm_client)
        if rezultat_lista:
            liste_extrase[camp] = rezultat_lista
            conversii_unitati.extend(rezultat_lista["conversii"])
            conflicte_totale.extend({"camp_lista": camp, **c} for c in rezultat_lista["conflicte"])

    # --- Câmpurile lipsă: obligatorii negăsite + cele cu citat ambiguu ---
    def are_valoare(camp: str) -> bool:
        if camp in valori_selectate:
            return valori_selectate[camp] is not None
        if catalog_campuri.get(camp, {}).get("tip") == "lista_chiriasi":
            return bool(chiriasi_extrasi)
        return camp in liste_extrase

    campuri_lipsa = []
    for camp in campuri_de_extras:
        if are_valoare(camp):
            continue
        if camp in campuri_ambigue:
            motiv = "citat ambiguu"
        elif este_camp_obligatoriu(camp):
            motiv = "negasit"
        else:
            continue
        campuri_lipsa.append({
            "camp": camp,
            "motiv": motiv,
            "documente_asteptate": selectate[camp].get("document") or [],
            "pentru": selectate[camp].get("pentru") or [],
            "obligatoriu": este_camp_obligatoriu(camp),
            **({"citat": campuri_ambigue[camp]["citat"], "sursa": campuri_ambigue[camp]["sursa"]} if camp in campuri_ambigue else {}),
        })

    # Chiriașii fără cod CAEN în document: regula pe chiriași nu îi poate verifica
    chiriasi_fara_caen = [c for c in chiriasi_extrasi if not c["caen"]]
    camp_chiriasi = next((c for c in campuri_lista if catalog_campuri.get(c, {}).get("tip") == "lista_chiriasi"), None)
    for chirias in chiriasi_fara_caen:
        campuri_lipsa.append({
            "camp": f"{camp_chiriasi}.caen",
            "motiv": MOTIV_CAEN_LIPSA_CHIRIAS,
            "chirias": chirias["nume"],
            "sursa": sursa_chiriasi,
            "documente_asteptate": selectate[camp_chiriasi].get("document") or [],
            "pentru": selectate[camp_chiriasi].get("pentru") or [],
            "obligatoriu": este_camp_obligatoriu(camp_chiriasi),
        })

    # --- Construirea modelului Pydantic DosarExtras ---
    def creeaza_obiect_camp(camp_ales: Optional[dict[str, Any]]) -> Optional[Camp]:
        if not camp_ales:
            return None
        return Camp(
            valoare=camp_ales["valoare_normalizata"],
            sursa=camp_ales["sursa"],
            incredere=camp_ales["incredere"],
        )

    def creeaza_camp_obligatoriu(camp_ales: Optional[dict[str, Any]]) -> Camp:
        return creeaza_obiect_camp(camp_ales) or Camp(valoare=None, sursa="", incredere=0.0)

    afirmatii_lista = []
    if valori_selectate.get("afirmatii_client"):
        val_af = valori_selectate["afirmatii_client"]["valoare_normalizata"]
        if isinstance(val_af, list):
            afirmatii_lista = val_af

    are_epc = any(d.get("tip_document") == "certificat_energetic" for d in documente_clasificate)
    val_epc_energie = valori_selectate.get("epc_energie_finala") or valori_selectate.get("energie_finala_kwh_m2")
    val_epc_sup = valori_selectate.get("epc_suprafata_m2") or (valori_selectate.get("suprafata_m2") if are_epc else None)

    # Indicatori: câmpurile din cerinte_dosar.yaml, cu cheia exact ca acolo
    indicatori_dict: dict[str, Camp] = {}
    for camp_nume, camp_dict in valori_selectate.items():
        if camp_nume not in CAMPURI_TOP_LEVEL and camp_dict is not None:
            indicatori_dict[camp_nume] = creeaza_obiect_camp(camp_dict)
    for camp_nume, rez in liste_extrase.items():
        indicatori_dict[camp_nume] = Camp(
            valoare=rez["valoare"],
            sursa=rez["sursa"],
            incredere=0.95 if rez["metoda"] == "determinist_tabele" else 0.8,
        )
    # Chirias.caen e text obligatoriu în contract: lista completă (cu caen null) stă în indicatori
    if chiriasi_fara_caen:
        indicatori_dict[camp_chiriasi] = Camp(valoare=chiriasi_extrasi, sursa=sursa_chiriasi or "", incredere=1.0)

    categorie_camp = subcategorie_camp = None
    if candidati_categorie:
        principal = candidati_categorie[0]
        sursa_cat = principal.get("sursa") or ""
        categorie_camp = Camp(valoare=principal["categorie"], sursa=sursa_cat, incredere=principal["incredere"])
        if principal.get("subcategorie"):
            subcategorie_camp = Camp(valoare=principal["subcategorie"], sursa=sursa_cat, incredere=principal["incredere"])
            if principal.get("camp_subcategorie"):
                indicatori_dict[principal["camp_subcategorie"]] = subcategorie_camp
        if principal.get("tip_nivel_3") and principal.get("camp_nivel_3"):
            indicatori_dict[principal["camp_nivel_3"]] = Camp(
                valoare=principal["tip_nivel_3"], sursa=sursa_cat, incredere=principal["incredere"],
            )

    dosar_extras = DosarExtras(
        dosar_id=dosar_id,
        cui=creeaza_camp_obligatoriu(valori_selectate.get("cui")),
        suma_eur=creeaza_camp_obligatoriu(valori_selectate.get("suma_eur")),
        cota_banca=creeaza_camp_obligatoriu(valori_selectate.get("cota_banca")),
        data_aprobare=creeaza_camp_obligatoriu(valori_selectate.get("data_aprobare")),
        tara=creeaza_camp_obligatoriu(valori_selectate.get("tara")),
        adresa_cladire=creeaza_camp_obligatoriu(valori_selectate.get("adresa_cladire")),
        suprafata_m2=creeaza_camp_obligatoriu(valori_selectate.get("suprafata_m2")),
        stadiu_cladire=creeaza_camp_obligatoriu(valori_selectate.get("stadiu_cladire")),
        nr_certificat_declarat=creeaza_camp_obligatoriu(valori_selectate.get("nr_certificat_declarat")),
        epc_clasa=creeaza_obiect_camp(valori_selectate.get("epc_clasa")),
        epc_energie_finala=creeaza_obiect_camp(val_epc_energie),
        epc_suprafata_m2=creeaza_obiect_camp(val_epc_sup),
        chiriasi=[Chirias(**c) for c in chiriasi_extrasi if c["caen"]],
        afirmatii_client=afirmatii_lista,
        categorie=categorie_camp,
        subcategorie=subcategorie_camp,
        indicatori=indicatori_dict,
    )

    # --- Construirea Raportului de Extracție ---
    campuri_raport: dict[str, Any] = {}
    for camp in campuri_scalare:
        ales = valori_selectate.get(camp)
        if ales:
            campuri_raport[camp] = {
                "valoare": ales["valoare_normalizata"],
                "valoare_bruta": ales.get("valoare_bruta"),
                "sursa": ales["sursa"],
                "citat": ales.get("citat"),
                "citat_verificat": ales.get("citat_verificat", False),
                "treapta_cautare": ales.get("treapta", 1),
                "incredere": ales["incredere"],
            }
            if ales.get("citat_reconstituit"):
                campuri_raport[camp]["citat_reconstituit"] = True
                campuri_raport[camp]["factor_incredere_citat_reconstituit"] = FACTOR_CITAT_RECONSTITUIT
            if ales.get("metoda"):
                campuri_raport[camp]["metoda"] = ales["metoda"]
        else:
            campuri_raport[camp] = {
                "valoare": None,
                "sursa": "",
                "citat": None,
                "citat_verificat": False,
                "treapta_cautare": None,
                "incredere": 0.0,
            }

    if chiriasi_extrasi:
        campuri_raport["chiriasi"] = {
            "valoare": chiriasi_extrasi,
            "numar_chiriasi": len(chiriasi_extrasi),
            "fara_caen": [c["nume"] for c in chiriasi_fara_caen],
            "sursa": sursa_chiriasi,
            "citat": citat_chiriasi,
            "citat_verificat": True,
            "metoda": "determinist_tabele",
            "incredere": 1.0,
        }
    for camp, rez in liste_extrase.items():
        campuri_raport[camp] = {
            "valoare": rez["valoare"],
            "sursa": rez["sursa"],
            "citat": rez["citat"],
            "citat_verificat": True,
            "metoda": rez["metoda"],
            "nr_randuri_brute": rez["nr_randuri_brute"],
        }

    # --- Documente găsite / lipsă (pe ID-urile din cerinte_dosar.yaml) ---
    evaluari_documente = [
        {
            "categorie": c["categorie"],
            "subcategorie": c.get("subcategorie"),
            **evalueaza_documente(c["categorie"], c.get("subcategorie"), c.get("tip_nivel_3"), documente_clasificate),
        }
        for c in candidati_categorie
    ] or [{"categorie": None, "subcategorie": None, **evalueaza_documente(None, None, None, documente_clasificate)}]
    principal_doc = evaluari_documente[0]

    raport_extractie = {
        "dosar_id": dosar_id,
        "categorie_candidati": candidati_categorie,
        "categorie_ambigua": rezultat_categorie["ambiguu"],
        "indicii_categorie": rezultat_categorie["indicii"],
        "documente_clasificate": raport_documente,
        "documente_gasite": principal_doc["documente_gasite"],
        "documente_lipsa": principal_doc["documente_lipsa"],
        "documente_recomandate_lipsa": principal_doc["documente_recomandate_lipsa"],
        **({"documente_per_candidat": evaluari_documente} if len(evaluari_documente) > 1 else {}),
        "campuri_selectate": list(selectate),
        "campuri_extrase": campuri_raport,
        "campuri_lipsa": campuri_lipsa,
        "conflicte": conflicte_totale,
        "conversii_unitati": conversii_unitati,
        "valori_respinse": valori_respinse,
        "statistici_llm": {
            k: v - statistici_start.get(k, 0) for k, v in llm_client.get_statistici().items()
        },
        # Un rând per apel real făcut pentru acest dosar: modelul cerut și cel raportat de API
        "apeluri_llm_reale": llm_client.apeluri_reale_detalii[index_apeluri_start:],
    }

    # Salvare în folderul _extras
    folder_extras = folder_dosar / "_extras"
    folder_extras.mkdir(parents=True, exist_ok=True)

    with open(folder_extras / "dosar_extras.json", "w", encoding="utf-8") as f:
        f.write(dosar_extras.model_dump_json(indent=2))

    with open(folder_extras / "raport_extractie.json", "w", encoding="utf-8") as f:
        json.dump(raport_extractie, f, ensure_ascii=False, indent=2)

    return dosar_extras, raport_extractie


def main() -> None:
    """Punct de intrare CLI pentru extragerea structurată."""
    argumente = sys.argv[1:]
    if argumente:
        dosare = [Path(arg).resolve() for arg in argumente]
    else:
        cale_dosare = Path("dosare")
        if not cale_dosare.exists():
            cale_dosare = Path(__file__).resolve().parent.parent / "dosare"
        dosare = sorted([
            p.resolve() for p in cale_dosare.iterdir()
            if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("_")
        ])

    llm_client = get_llm_client()
    llm_client.reseteaza_statistici()

    for d in dosare:
        print(f"Procesare dosar: {d.name} ...")
        proceseaza_dosar_structurat(d)

    stats = llm_client.get_statistici()
    print("=" * 50)
    print("REZUMAT EXTRACȚIE STRUCTURATĂ")
    print("=" * 50)
    print(f"Dosare procesate: {len(dosare)}")
    print(f"Apeluri LLM reale: {stats['apeluri_reale']}")
    print(f"Apeluri din cache: {stats['apeluri_cache']}")
    print(f"Total apeluri LLM: {stats['total_apeluri']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
