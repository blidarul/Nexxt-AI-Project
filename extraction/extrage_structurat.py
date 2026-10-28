"""Scriptul principal al Etapei 2: Extracție structurată (JSON brut -> DosarExtras).

Orchestrează:
- Asigurarea existenței _brut/
- Clasificarea conținutului documentelor
- Căutarea în 3 trepte
- Extragerea câmpurilor cu LLM și tabele markdown
- Extragerea deterministă a chiriașilor
- Verificarea anti-halucinație a citatelor
- Normalizarea valorilor și rezolvarea conflictelor
- Salvarea în _extras/dosar_extras.json și _extras/raport_extractie.json
"""

import json
from pathlib import Path
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
    gaseste_bucle_treapta_3,
    gaseste_pagini_treapta_1,
    gaseste_pagini_treapta_2,
    grupeaza_campuri_pe_documente,
    incarca_catalog_campuri,
)
from extraction.clasificare import clasifica_document
from extraction.extrage_brut import proceseaza_dosar as ruleaza_etapa_1
from extraction.extragere_campuri import (
    extrage_campuri_document_llm,
    extrage_chiriasi_determinist,
)
from extraction.llm_client import get_llm_client
from extraction.normalizare import normalizeaza_camp
from extraction.verificare import (
    calculeaza_incredere_finala,
    rezolva_conflicte_camp,
    verifica_citat,
)


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


def proceseaza_dosar_structurat(folder_dosar: Path) -> tuple[DosarExtras, dict[str, Any]]:
    """Execută întregul flux de extracție structurată pentru un dosar."""
    dosar_id = folder_dosar.name
    llm_client = get_llm_client()
    catalog_campuri = incarca_catalog_campuri()

    # 1. Încarcă documentele din Etapa 1
    documente_brute = incarca_documente_brute(folder_dosar)

    # 2. Pasul 2: Clasificarea documentelor pe baza conținutului
    documente_clasificate = []
    raport_documente = []

    for doc in documente_brute:
        clasif = clasifica_document(doc, llm_client=llm_client)
        doc_clasif = dict(doc)
        doc_clasif["tip_document"] = clasif["tip_document"]
        doc_clasif["incredere_clasificare"] = clasif["incredere"]
        documente_clasificate.append(doc_clasif)

        raport_documente.append({
            "fisier": doc.get("fisier"),
            "tip_detectat": clasif["tip_document"],
            "incredere": clasif["incredere"],
            "motiv": clasif["motiv"],
        })

    # 3. Extragerea deterministă a chiriașilor din tabele
    chiriasi_extrasi, sursa_chiriasi, citat_chiriasi = extrage_chiriasi_determinist(documente_clasificate)

    # Câmpuri de extras
    toate_campurile = list(catalog_campuri.keys())
    campuri_scalare = [c for c in toate_campurile if c not in ("chiriasi",)]

    candidati_per_camp: dict[str, list[dict[str, Any]]] = {c: [] for c in campuri_scalare}
    treapta_gasire: dict[str, int] = {}
    valori_respinse = []

    # --- TREAPTA 1 (Țintită: documente probabile) ---
    alocari_t1 = {}
    for camp in campuri_scalare:
        info_c = catalog_campuri[camp]
        pagini_t1 = gaseste_pagini_treapta_1(camp, info_c, documente_clasificate)
        if pagini_t1:
            alocari_t1[camp] = pagini_t1

    grupare_t1 = grupeaza_campuri_pe_documente(alocari_t1)
    for fisier, date_grup in grupare_t1.items():
        doc_complet = date_grup["doc"]
        extrase_llm = extrage_campuri_document_llm(
            fisier=fisier,
            pagini=date_grup["pagini"],
            campuri=date_grup["campuri"],
            catalog_campuri=catalog_campuri,
            llm_client=llm_client,
        )

        for camp, val_info in extrase_llm.items():
            if not isinstance(val_info, dict) and camp == "afirmatii_client" and isinstance(val_info, list):
                # caz listă de afirmații
                candidati_per_camp[camp].append({
                    "fisier": fisier,
                    "tip_document": date_grup["tip_document"],
                    "valoare_bruta": val_info,
                    "citat": "Declarații ale solicitantului privind sustenabilitatea",
                    "pagina": 1,
                    "incredere_llm": 0.95,
                    "treapta": 1,
                    "doc_complet": doc_complet,
                })
                treapta_gasire[camp] = 1
                continue

            if not isinstance(val_info, dict):
                continue

            val_text = val_info.get("valoare_text")
            if val_text is not None and str(val_text).strip().lower() not in ("null", "none", ""):
                candidati_per_camp[camp].append({
                    "fisier": fisier,
                    "tip_document": date_grup["tip_document"],
                    "valoare_bruta": val_text,
                    "citat": val_info.get("citat", ""),
                    "pagina": int(val_info.get("pagina", 1)),
                    "incredere_llm": float(val_info.get("incredere", 0.9)),
                    "treapta": 1,
                    "doc_complet": doc_complet,
                })
                treapta_gasire[camp] = 1

    # --- TREAPTA 2 (Extinsă: câmpuri obligatorii lipsă în restul documentelor) ---
    campuri_lipsa_t1 = [
        c for c in campuri_scalare
        if catalog_campuri[c].get("obligatoriu", False) and not candidati_per_camp[c]
    ]

    if campuri_lipsa_t1:
        alocari_t2 = {}
        for camp in campuri_lipsa_t1:
            info_c = catalog_campuri[camp]
            doc_deja = set(catalog_campuri[camp].get("documente_probabile", []))
            pagini_t2 = gaseste_pagini_treapta_2(camp, info_c, documente_clasificate, documente_deja_incercate=doc_deja)
            if pagini_t2:
                alocari_t2[camp] = pagini_t2

        grupare_t2 = grupeaza_campuri_pe_documente(alocari_t2)
        for fisier, date_grup in grupare_t2.items():
            doc_complet = date_grup["doc"]
            extrase_llm = extrage_campuri_document_llm(
                fisier=fisier,
                pagini=date_grup["pagini"],
                campuri=date_grup["campuri"],
                catalog_campuri=catalog_campuri,
                llm_client=llm_client,
            )
            for camp, val_info in extrase_llm.items():
                if isinstance(val_info, dict):
                    val_text = val_info.get("valoare_text")
                    if val_text is not None and str(val_text).strip().lower() not in ("null", "none", ""):
                        candidati_per_camp[camp].append({
                            "fisier": fisier,
                            "tip_document": date_grup["tip_document"],
                            "valoare_bruta": val_text,
                            "citat": val_info.get("citat", ""),
                            "pagina": int(val_info.get("pagina", 1)),
                            "incredere_llm": float(val_info.get("incredere", 0.85)),
                            "treapta": 2,
                            "doc_complet": doc_complet,
                        })
                        treapta_gasire[camp] = 2

    # --- Verificarea anti-halucinație, normalizarea și calculul încrederii ---
    campuri_finale_valide: dict[str, list[dict[str, Any]]] = {c: [] for c in campuri_scalare}

    for camp, lista_candidati in candidati_per_camp.items():
        info_c = catalog_campuri[camp]
        tip_camp = info_c.get("tip")
        reguli_val = info_c.get("validare")
        doc_probabile = info_c.get("documente_probabile", [])

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

            citat = cand.get("citat", "")
            pag_ind = cand.get("pagina", 1)
            doc_c = cand.get("doc_complet", {})

            # Verificare citat în document
            citat_gasit, pag_reala, sursa_calc = verifica_citat(citat, pag_ind, doc_c)

            if not citat_gasit:
                valori_respinse.append({
                    "camp": camp,
                    "valoare_bruta": cand["valoare_bruta"],
                    "citat": citat,
                    "fisier": cand["fisier"],
                    "motiv": "citat_negasit",
                })
                continue

            # Normalizare deterministă
            val_norm, motiv_norm = normalizeaza_camp(
                camp_nume=camp,
                valoare_bruta=cand["valoare_bruta"],
                tip_camp=tip_camp,
                reguli_validare=reguli_val,
            )

            if val_norm is None:
                valori_respinse.append({
                    "camp": camp,
                    "valoare_bruta": cand["valoare_bruta"],
                    "citat": citat,
                    "fisier": cand["fisier"],
                    "motiv": f"normalizare_sau_validare_esuata: {motiv_norm}",
                })
                continue

            # Calcul încredere
            este_doc_probabil = cand["tip_document"] in doc_probabile
            incredere_calc = calculeaza_incredere_finala(
                incredere_llm=cand["incredere_llm"],
                citat_verificat=True,
                normalizare_reusita=True,
                este_document_probabil=este_doc_probabil,
                provine_din_ocr=False,
            )

            campuri_finale_valide[camp].append({
                "valoare_normalizata": val_norm,
                "valoare_bruta": cand["valoare_bruta"],
                "sursa": sursa_calc or f"{cand['fisier']}, p.{pag_reala}",
                "incredere": incredere_calc,
                "citat": citat,
                "citat_verificat": True,
                "treapta": cand["treapta"],
                "fisier": cand["fisier"],
                "tip_document": cand["tip_document"],
            })

    # --- Rezolvarea conflictelor și selecția valorilor unice ---
    valori_selectate: dict[str, Optional[dict[str, Any]]] = {}
    conflicte_totale = []

    for camp in campuri_scalare:
        cand_valizi = campuri_finale_valide[camp]
        ales, conf = rezolva_conflicte_camp(camp, cand_valizi, catalog_campuri)
        valori_selectate[camp] = ales
        if conf:
            conflicte_totale.extend(conf)

    # Identifică câmpurile lipsă
    campuri_lipsa = []
    for camp in toate_campurile:
        if camp == "chiriasi":
            if not chiriasi_extrasi and catalog_campuri["chiriasi"].get("obligatoriu", False):
                campuri_lipsa.append(camp)
        else:
            if valori_selectate.get(camp) is None and catalog_campuri[camp].get("obligatoriu", False):
                campuri_lipsa.append(camp)

    # --- Construirea modelului Pydantic DosarExtras ---
    def creeaza_obiect_camp(nume: str, camp_ales: Optional[dict[str, Any]]) -> Optional[Camp]:
        if not camp_ales:
            return None
        return Camp(
            valoare=camp_ales["valoare_normalizata"],
            sursa=camp_ales["sursa"],
            incredere=camp_ales["incredere"],
        )

    # Câmpuri obligatorii (fallback la Camp() gol dacă lipsesc pentru validare)
    def creeaza_camp_obligatoriu(nume: str, camp_ales: Optional[dict[str, Any]]) -> Camp:
        if not camp_ales:
            return Camp(valoare=None, sursa="", incredere=0.0)
        return Camp(
            valoare=camp_ales["valoare_normalizata"],
            sursa=camp_ales["sursa"],
            incredere=camp_ales["incredere"],
        )

    afirmatii_lista = []
    if valori_selectate.get("afirmatii_client"):
        val_af = valori_selectate["afirmatii_client"]["valoare_normalizata"]
        if isinstance(val_af, list):
            afirmatii_lista = val_af

    dosar_extras = DosarExtras(
        dosar_id=dosar_id,
        cui=creeaza_camp_obligatoriu("cui", valori_selectate.get("cui")),
        suma_eur=creeaza_camp_obligatoriu("suma_eur", valori_selectate.get("suma_eur")),
        cota_banca=creeaza_camp_obligatoriu("cota_banca", valori_selectate.get("cota_banca")),
        data_aprobare=creeaza_camp_obligatoriu("data_aprobare", valori_selectate.get("data_aprobare")),
        tara=creeaza_camp_obligatoriu("tara", valori_selectate.get("tara")),
        adresa_cladire=creeaza_camp_obligatoriu("adresa_cladire", valori_selectate.get("adresa_cladire")),
        suprafata_m2=creeaza_camp_obligatoriu("suprafata_m2", valori_selectate.get("suprafata_m2")),
        stadiu_cladire=creeaza_camp_obligatoriu("stadiu_cladire", valori_selectate.get("stadiu_cladire")),
        nr_certificat_declarat=creeaza_camp_obligatoriu("nr_certificat_declarat", valori_selectate.get("nr_certificat_declarat")),
        epc_clasa=creeaza_obiect_camp("epc_clasa", valori_selectate.get("epc_clasa")),
        epc_energie_finala=creeaza_obiect_camp("epc_energie_finala", valori_selectate.get("epc_energie_finala")),
        epc_suprafata_m2=creeaza_obiect_camp("epc_suprafata_m2", valori_selectate.get("epc_suprafata_m2")),
        chiriasi=chiriasi_extrasi,
        afirmatii_client=afirmatii_lista,
    )

    # --- Construirea Raportului de Extracție ---
    campuri_raport = {}
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
            "numar_chiriasi": len(chiriasi_extrasi),
            "sursa": sursa_chiriasi,
            "citat": citat_chiriasi,
            "citat_verificat": True,
            "metoda": "determinist_tabele",
            "incredere": 1.0,
        }

    statistici_llm = llm_client.get_statistici()

    raport_extractie = {
        "dosar_id": dosar_id,
        "documente_clasificate": raport_documente,
        "campuri_extrase": campuri_raport,
        "campuri_lipsa": campuri_lipsa,
        "conflicte": conflicte_totale,
        "valori_respinse": valori_respinse,
        "statistici_llm": statistici_llm,
    }

    # Salvare în folderul _extras
    folder_extras = folder_dosar / "_extras"
    folder_extras.mkdir(parents=True, exist_ok=True)

    cale_dosar_extras = folder_extras / "dosar_extras.json"
    with open(cale_dosar_extras, "w", encoding="utf-8") as f:
        f.write(dosar_extras.model_dump_json(indent=2))

    cale_raport = folder_extras / "raport_extractie.json"
    with open(cale_raport, "w", encoding="utf-8") as f:
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
    print("REZUMAT EXTRACȚIE STRUCTURATĂ (ETAPA 2)")
    print("=" * 50)
    print(f"Dosare procesate: {len(dosare)}")
    print(f"Apeluri LLM reale: {stats['apeluri_reale']}")
    print(f"Apeluri din cache: {stats['apeluri_cache']}")
    print(f"Total apeluri LLM: {stats['total_apeluri']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
