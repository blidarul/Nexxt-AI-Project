"""Extragerea câmpurilor de tip listă (ex. vehicule) din tabele, determinist.

Coloanele, sinonimele antetelor, tipurile coloanelor și cheia de agregare vin din campuri.yaml.
Pași: recunoaștere antet -> unire tabele continuate pe pagina următoare -> conversie unități din antet
-> agregare pe model (cantitatea se adună). LLM-ul se folosește doar dacă nu există tabel recognoscibil.
"""

import re
from typing import Any, Optional

from extraction.cautare import normalizeaza_text_cautare
from extraction.llm_client import LLMClient, get_llm_client
from extraction.normalizare import detecteaza_si_normalizeaza_unitate, normalizeaza_data, normalizeaza_numar
from extraction.verificare import verifica_citat

MIN_COLOANE_RECUNOSCUTE = 3
LUNGIME_SINONIM_SCURT = 4

# Unitățile întoarse de detecteaza_si_normalizeaza_unitate care înseamnă că s-a aplicat o conversie
UNITATI_CONVERTITE = {"kWh/100km", "Wh/km", "g/mi", "kW", "GW", "kWh", "GWh"}

# Unitățile care pot apărea în antetul unei coloane
_UNITATI_ANTET = re.compile(r"kwh\s*/\s*100\s*km|wh\s*/\s*km|kwh\s*/\s*km|g\s*/\s*mi\b|g\s*/\s*km", re.IGNORECASE)


def _cuvinte(text: str) -> list[str]:
    return [c for c in re.split(r"[\s()\[\],;:]+", text) if c]


def _scor_sinonim(antet_norm: str, sinonim: str) -> float:
    s = normalizeaza_text_cautare(sinonim).strip()
    if not s:
        return 0.0
    if antet_norm == s:
        return 100.0 + len(s)
    if len(s) <= LUNGIME_SINONIM_SCURT:
        return float(len(s)) if s in _cuvinte(antet_norm) else 0.0
    return float(len(s)) if s in antet_norm else 0.0


def potriveste_antet(antet: list[str], coloane: list[dict[str, Any]]) -> dict[int, str]:
    """Mapează indexul fiecărei celule de antet la cheia coloanei (cea mai lungă potrivire câștigă).

    Fiecare cheie se atribuie unei singure coloane.
    """
    perechi = []
    for idx, celula in enumerate(antet):
        antet_norm = normalizeaza_text_cautare(str(celula)).strip()
        if not antet_norm:
            continue
        for col in coloane:
            scor = max((_scor_sinonim(antet_norm, s) for s in col.get("sinonime", [])), default=0.0)
            if scor > 0:
                perechi.append((scor, idx, col["cheie"]))

    perechi.sort(reverse=True)
    mapare: dict[int, str] = {}
    folosite: set[str] = set()
    for _, idx, cheie in perechi:
        if idx in mapare or cheie in folosite:
            continue
        mapare[idx] = cheie
        folosite.add(cheie)
    return mapare


def _este_antet(rand: list[str], coloane: list[dict[str, Any]]) -> bool:
    return len(potriveste_antet(rand, coloane)) >= MIN_COLOANE_RECUNOSCUTE


def gaseste_tabele_lista(
    doc: dict[str, Any],
    coloane: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Găsește tabelele recognoscibile dintr-un document și le unește pe cele continuate.

    Un tabel continuă pe pagina următoare dacă primul tabel de acolo are același număr de coloane
    și fie își repetă antetul, fie nu are antet deloc.
    Ieșire: [{"antet": [...], "mapare": {idx: cheie}, "randuri": [(pagina, rand), ...], "pagini": [..]}]
    """
    rezultat: list[dict[str, Any]] = []
    curent: Optional[dict[str, Any]] = None
    pagina_anterioara = None

    for pag in doc.get("pagini", []):
        nr = pag.get("pagina", 1)
        for i_tab, tab in enumerate(pag.get("tabele", [])):
            randuri = [[str(c) for c in r] for r in tab.get("randuri", []) if any(str(c).strip() for c in r)]
            if not randuri:
                continue

            if _este_antet(randuri[0], coloane):
                antet = randuri[0]
                if (curent and i_tab == 0 and pagina_anterioara == nr - 1
                        and [normalizeaza_text_cautare(c) for c in antet] == [normalizeaza_text_cautare(c) for c in curent["antet"]]):
                    # antet repetat pe pagina următoare: continuare
                    curent["randuri"].extend((nr, r) for r in randuri[1:])
                    curent["pagini"].append(nr)
                else:
                    curent = {
                        "antet": antet,
                        "mapare": potriveste_antet(antet, coloane),
                        "randuri": [(nr, r) for r in randuri[1:]],
                        "pagini": [nr],
                    }
                    rezultat.append(curent)
                pagina_anterioara = nr
            elif (curent and i_tab == 0 and pagina_anterioara == nr - 1
                    and len(randuri[0]) == len(curent["antet"])):
                # tabel fără antet la începutul paginii următoare: continuare
                curent["randuri"].extend((nr, r) for r in randuri)
                curent["pagini"].append(nr)
                pagina_anterioara = nr
            else:
                curent = None

    return rezultat


def _unitate_din_antet(celula_antet: str) -> Optional[str]:
    m = _UNITATI_ANTET.search(celula_antet or "")
    return re.sub(r"\s+", " ", m.group(0)) if m else None


def converteste_valoare(cheie: str, tip: str, valoare: str, unitate_antet: Optional[str]) -> tuple[Any, Optional[str]]:
    """Convertește o celulă după tipul coloanei și unitatea din antet.

    Întoarce (valoare, unitate_originala) — unitatea doar dacă s-a aplicat o conversie.
    """
    text = str(valoare).strip()
    if not text or text in ("-", "—", "n/a", "N/A"):
        return None, None
    if tip == "intreg":
        num = normalizeaza_numar(text)
        return (int(num) if num is not None else None), None
    if tip == "data":
        return normalizeaza_data(text), None
    if tip == "numar":
        text_cu_unitate = f"{text} {unitate_antet}" if unitate_antet and not re.search(r"[a-zA-Z]", text) else text
        val, unitate = detecteaza_si_normalizeaza_unitate(cheie, text_cu_unitate)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            return normalizeaza_numar(text), None
        return val, (unitate if unitate in UNITATI_CONVERTITE else None)
    return text, None


def _cheie_model(rand: dict[str, Any], chei: list[str]) -> tuple:
    return tuple(normalizeaza_text_cautare(str(rand.get(k) or "")).strip() for k in chei)


def extrage_lista_din_tabele(
    camp: str,
    info_camp: dict[str, Any],
    documente: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Extrage lista determinist din primul document cu tabel recognoscibil.

    Ieșire: {"valoare": [...], "sursa", "citat", "conversii": [...], "conflicte": [...]} sau None.
    """
    coloane = info_camp.get("coloane") or []
    tip_coloana = {c["cheie"]: c.get("tip", "text") for c in coloane}
    chei_agregare = info_camp.get("cheie_agregare") or []
    col_cantitate = info_camp.get("coloana_cantitate")

    for doc in documente:
        tabele = gaseste_tabele_lista(doc, coloane)
        for tabel in tabele:
            if not tabel["randuri"]:
                continue
            unitati = {idx: _unitate_din_antet(tabel["antet"][idx]) for idx in tabel["mapare"]}
            ordine_coloane = [c["cheie"] for c in coloane]
            mapare_ordonata = sorted(tabel["mapare"].items(), key=lambda x: ordine_coloane.index(x[1]))
            conversii = []
            randuri_parsate = []
            citate = []
            for nr_pag, rand in tabel["randuri"]:
                obiect: dict[str, Any] = {}
                for idx, cheie in mapare_ordonata:
                    if idx >= len(rand):
                        continue
                    val, unitate_orig = converteste_valoare(cheie, tip_coloana.get(cheie, "text"), rand[idx], unitati.get(idx))
                    obiect[cheie] = val
                    if unitate_orig and val is not None:
                        conversii.append({
                            "camp": f"{camp}.{cheie}", "valoare_bruta": rand[idx], "unitate_originala": unitate_orig,
                            "valoare": val, "sursa": f"{doc.get('fisier')}, p.{nr_pag}",
                        })
                if not any(v is not None for v in obiect.values()):
                    continue
                if normalizeaza_text_cautare(" ".join(rand)).strip().startswith("total"):
                    continue
                randuri_parsate.append(obiect)
                citate.append(" | ".join(rand))

            if not randuri_parsate:
                continue

            agregate, conflicte = agrega_randuri(randuri_parsate, chei_agregare, col_cantitate)
            pagini = tabel["pagini"]
            sursa_pag = f"p.{pagini[0]}" if len(pagini) == 1 else f"p.{pagini[0]}-{pagini[-1]}"
            return {
                "valoare": agregate,
                "sursa": f"{doc.get('fisier')}, {sursa_pag}",
                "citat": "; ".join(citate[:3]),
                "conversii": conversii,
                "conflicte": conflicte,
                "metoda": "determinist_tabele",
                "nr_randuri_brute": len(randuri_parsate),
            }
    return None


def agrega_randuri(
    randuri: list[dict[str, Any]],
    chei_agregare: list[str],
    col_cantitate: Optional[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Agregă rândurile cu aceeași cheie de model: cantitatea se adună, restul trebuie să coincidă."""
    if not chei_agregare:
        return randuri, []
    grupuri: dict[tuple, dict[str, Any]] = {}
    ordine: list[tuple] = []
    conflicte = []
    for rand in randuri:
        cheie = _cheie_model(rand, chei_agregare)
        if cheie not in grupuri:
            grupuri[cheie] = dict(rand)
            ordine.append(cheie)
            continue
        tinta = grupuri[cheie]
        for k, v in rand.items():
            if k == col_cantitate:
                tinta[k] = (tinta.get(k) or 0) + (v or 0)
            elif tinta.get(k) is None:
                tinta[k] = v
            elif v is not None and v != tinta[k]:
                conflicte.append({"camp": k, "model": " ".join(cheie), "valori": [tinta[k], v], "ales": tinta[k],
                                  "motiv": "valori diferite pentru același model în listă"})
    return [grupuri[k] for k in ordine], conflicte


def extrage_din_document_autoritate(
    camp: str,
    info_camp: dict[str, Any],
    doc: dict[str, Any],
    llm_client: Optional[LLMClient] = None,
) -> Optional[dict[str, Any]]:
    """Extrage dintr-un document de autoritate (ex. CoC) modelul și coloanele de autoritate.

    Ieșire: {"valori": {cheie: valoare}, "citate": {cheie: citat}, "sursa"} sau None.
    """
    client = llm_client or get_llm_client()
    coloane = {c["cheie"]: c for c in info_camp.get("coloane") or []}
    chei = list(dict.fromkeys((info_camp.get("cheie_agregare") or []) + (info_camp.get("coloane_autoritate") or [])))
    descrieri = "\n".join(f"- {k}: {', '.join(coloane[k].get('sinonime', [])[:5])}" for k in chei if k in coloane)
    text = "\n".join(f"=== PAGINA {p.get('pagina')} ===\n{p.get('text', '')}" for p in doc.get("pagini", []))[:6000]

    prompt_sistem = (
        "Extragi date dintr-un document tehnic al unui vehicul. Pentru fiecare cheie întoarce "
        "{\"valoare_text\": ..., \"citat\": ..., \"pagina\": ...}. Valoarea exact cum apare (cu unitatea), "
        "citatul copiat EXACT din document (max 200 caractere). Dacă nu apare explicit: null. "
        "Întoarce EXCLUSIV JSON cu cheile cerute."
    )
    prompt_utilizator = f"Chei de extras (cu sinonime):\n{descrieri}\n\nDocument:\n{text}"
    date_json, _ = client.apeleaza_cu_json([
        {"role": "system", "content": prompt_sistem},
        {"role": "user", "content": prompt_utilizator},
    ])
    if not isinstance(date_json, dict):
        return None

    valori: dict[str, Any] = {}
    citate: dict[str, str] = {}
    conversii = []
    for k in chei:
        intrare = date_json.get(k)
        if not isinstance(intrare, dict) or intrare.get("valoare_text") in (None, "", "null"):
            continue
        citat = str(intrare.get("citat") or "")
        gasit, pagina, _ = verifica_citat(citat, int(intrare.get("pagina") or 1), doc)
        if not gasit:
            continue
        val, unitate = converteste_valoare(k, coloane.get(k, {}).get("tip", "text"), str(intrare["valoare_text"]), None)
        if val is None:
            continue
        valori[k] = val
        citate[k] = citat
        if unitate and coloane.get(k, {}).get("tip") == "numar":
            conversii.append({"camp": f"{camp}.{k}", "valoare_bruta": intrare["valoare_text"], "unitate_originala": unitate,
                              "valoare": val, "sursa": f"{doc.get('fisier')}, p.{pagina}"})
    if not valori:
        return None
    return {"valori": valori, "citate": citate, "sursa": doc.get("fisier"), "conversii": conversii}


def aplica_document_autoritate(
    lista: list[dict[str, Any]],
    autoritate: list[dict[str, Any]],
    info_camp: dict[str, Any],
) -> list[dict[str, Any]]:
    """Suprascrie coloanele de autoritate cu valorile din documentele de autoritate (ex. CoC).

    Potrivirea se face pe model (și marcă, dacă e prezentă). Întoarce lista de conflicte.
    """
    chei_auto = info_camp.get("coloane_autoritate") or []
    conflicte = []
    for doc_auto in autoritate:
        val_auto = doc_auto["valori"]
        model_auto = normalizeaza_text_cautare(str(val_auto.get("model") or "")).strip()
        marca_auto = normalizeaza_text_cautare(str(val_auto.get("marca") or "")).strip()
        if not model_auto:
            continue
        for rand in lista:
            model = normalizeaza_text_cautare(str(rand.get("model") or "")).strip()
            marca = normalizeaza_text_cautare(str(rand.get("marca") or "")).strip()
            if not model or (model != model_auto and model not in model_auto and model_auto not in model):
                continue
            if marca and marca_auto and marca != marca_auto:
                continue
            for k in chei_auto:
                if k not in val_auto:
                    continue
                if rand.get(k) is not None and not _egal_numeric(rand[k], val_auto[k]):
                    conflicte.append({
                        "camp": k, "model": rand.get("model"), "valoare_lista": rand[k], "valoare_autoritate": val_auto[k],
                        "ales": val_auto[k], "sursa_autoritate": doc_auto["sursa"],
                        "motiv": "valoarea din documentul de autoritate (CoC) câștigă",
                    })
                rand[k] = val_auto[k]
            rand.setdefault("_surse_autoritate", []).append(doc_auto["sursa"])
    return conflicte


def _egal_numeric(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return a == b


def extrage_lista_llm(
    camp: str,
    info_camp: dict[str, Any],
    doc: dict[str, Any],
    llm_client: Optional[LLMClient] = None,
) -> Optional[dict[str, Any]]:
    """Fallback când nu există tabel recognoscibil: LLM-ul întoarce rândurile listei, cu citat per rând."""
    client = llm_client or get_llm_client()
    coloane = info_camp.get("coloane") or []
    tip_coloana = {c["cheie"]: c.get("tip", "text") for c in coloane}
    chei = [c["cheie"] for c in coloane]
    text = "\n".join(f"=== PAGINA {p.get('pagina')} ===\n{p.get('text', '')}" for p in doc.get("pagini", []))[:8000]
    prompt_sistem = (
        f"Extragi lista '{camp}' din document. Întoarce EXCLUSIV JSON: "
        '{"randuri": [{"valori": {cheie: valoare_text sau null}, "citat": "...", "pagina": 1}]}. '
        f"Chei: {', '.join(chei)}. Valorile exact cum apar (cu unitatea). Citatul copiat EXACT. "
        "Nu inventa rânduri; dacă lista nu există, întoarce randuri: []."
    )
    date_json, _ = client.apeleaza_cu_json([
        {"role": "system", "content": prompt_sistem},
        {"role": "user", "content": text},
    ])
    if not isinstance(date_json, dict):
        return None
    randuri = []
    citate = []
    for r in date_json.get("randuri") or []:
        if not isinstance(r, dict):
            continue
        gasit, _, _ = verifica_citat(str(r.get("citat") or ""), int(r.get("pagina") or 1), doc)
        if not gasit:
            continue
        obiect = {}
        for k, v in (r.get("valori") or {}).items():
            if k in tip_coloana and v not in (None, "", "null"):
                obiect[k], _ = converteste_valoare(k, tip_coloana[k], str(v), None)
        if obiect:
            randuri.append(obiect)
            citate.append(str(r.get("citat")))
    if not randuri:
        return None
    agregate, conflicte = agrega_randuri(randuri, info_camp.get("cheie_agregare") or [], info_camp.get("coloana_cantitate"))
    return {"valoare": agregate, "sursa": doc.get("fisier"), "citat": "; ".join(citate[:3]),
            "conversii": [], "conflicte": conflicte, "metoda": "llm", "nr_randuri_brute": len(randuri)}
