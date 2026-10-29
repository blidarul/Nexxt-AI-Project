"""Motor de reguli generic: evaluează orice fișier din rules/*.yaml.

Suportă toate tipurile de reguli definite în Framework-ul RBI:
- prag (operatori: <, <=, ==, !=, >=, >)
- lista (apartenență la listă)
- lista_cu_ordine (ierarhii de certificare: BREEAM, LEED, DGNB, OGNI, EDGE)
- da_nu (comparare booleană Python True/False)
- excludere (criterii de respingere directă sau semnal)
- oricare (agregare logică OR pe căi sau condiții)
- toate (agregare logică AND pe condiții)
- prag_dependent_de_data (grandfathering G-05 cu data marcării / data aprobării)
- informativ (reguli descriptive sau de atenționare)
- monitorizare (stadii intermediare sau monitorizare post-acordare)

Suportă de asemenea:
- aplica_daca / doar_pentru (filtrare condiționată pe tehnologie/subcategorie/etc.)
- daca_lipseste (tratare explicită a valorilor absente: NEEVALUABIL, OK_CONDITIONAT, SEMNAL)
- calcul dinamic de câmpuri derivate cu păstrarea formulei în dovadă
- evaluare item-by-item pe liste de vehicule (cu calcul pro-rata și acțiune generată)
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from contracts import Camp, RezultatRegula, RezultatTip, StareDosar

logger = logging.getLogger(__name__)

# Directorul de reguli
RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
_RULES_CACHE: dict[str, dict] = {}


def strip_accents(s: Any) -> str:
    """Normalizează textul eliminând diacriticele și spațiile albe în exces."""
    if s is None:
        return ""
    text = str(s).strip()
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()


def incarca_reguli_yaml(nume_fisier: str) -> dict:
    """Încarcă și pune în cache un fișier YAML din directorul rules/."""
    if not nume_fisier.endswith(".yaml"):
        nume_fisier = f"{nume_fisier}.yaml"

    if nume_fisier in _RULES_CACHE:
        return _RULES_CACHE[nume_fisier]

    cale = RULES_DIR / nume_fisier
    if not cale.exists():
        raise FileNotFoundError(f"Fișierul de reguli {cale} nu a fost găsit.")

    with open(cale, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    _RULES_CACHE[nume_fisier] = data
    return data


# ---------------------------------------------------------------------------
# Câmpuri calculate (punctul 2 din Partea 1)
# ---------------------------------------------------------------------------

def _parse_data(val: Any) -> Optional[date]:
    """Parsează o dată în format ISO (YYYY-MM-DD)."""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    val_str = str(val).strip()
    if not val_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val_str[:10], fmt).date()
        except ValueError:
            continue
    return None


def calculeaza_campuri_derivate(stare: StareDosar) -> dict[str, tuple[Any, str]]:
    """Calculează câmpurile derivate specificate în cerințe.
    
    Întoarce un dicționar: nume_camp -> (valoare_calculata, formula_sau_dovada)
    """
    derivate: dict[str, tuple[Any, str]] = {}
    extras = stare.extras
    indicatori = extras.indicatori or {}

    def get_raw(name: str) -> Any:
        if name in indicatori and indicatori[name] is not None:
            return indicatori[name].valoare
        val_attr = getattr(extras, name, None)
        if isinstance(val_attr, Camp):
            return val_attr.valoare
        return val_attr

    # 1. luni_de_la_aprobare
    # Formula: diferența în luni între data de referință (data_alocare sau data curentă) și data_aprobare
    data_aprobare_val = get_raw("data_aprobare")
    d_apr = _parse_data(data_aprobare_val)
    if d_apr:
        d_ref = _parse_data(get_raw("data_alocare")) or _parse_data(get_raw("data_marcare_verde")) or date(2026, 1, 1)
        luni = (d_ref.year - d_apr.year) * 12 + (d_ref.month - d_apr.month)
        formula = f"luni_de_la_aprobare = ({d_ref} - {d_apr}) în luni = {luni} luni"
        derivate["luni_de_la_aprobare"] = (luni, formula)

    # 2. reducere_ped_pct
    # Formula: 1 - ped_dupa / ped_inainte
    ped_inainte = get_raw("ped_inainte_kwh_m2") or get_raw("ped_inainte")
    ped_dupa = get_raw("ped_dupa_kwh_m2") or get_raw("ped_dupa")
    if ped_inainte is not None and ped_dupa is not None:
        try:
            pin = float(ped_inainte)
            pdp = float(ped_dupa)
            if pin > 0:
                pct = round(1.0 - (pdp / pin), 4)
                formula = f"reducere_ped_pct = 1 - ({pdp} / {pin}) = {pct:.2%}"
                derivate["reducere_ped_pct"] = (pct, formula)
        except (ValueError, TypeError):
            pass

    # 3. imbunatatire_eficienta_pct
    # Formula: 1 - consum_dupa / consum_inainte
    c_inainte = get_raw("consum_inainte_mwh") or get_raw("consum_inainte_kwh") or get_raw("consum_inainte")
    c_dupa = get_raw("consum_dupa_mwh") or get_raw("consum_dupa_kwh") or get_raw("consum_dupa")
    if c_inainte is not None and c_dupa is not None:
        try:
            cin = float(c_inainte)
            cdp = float(c_dupa)
            if cin > 0:
                pct = round(1.0 - (cdp / cin), 4)
                formula = f"imbunatatire_eficienta_pct = 1 - ({cdp} / {cin}) = {pct:.2%}"
                derivate["imbunatatire_eficienta_pct"] = (pct, formula)
        except (ValueError, TypeError):
            pass

    # 4. densitate_putere_w_m2
    # Când lipsește: din putere_instalata_w ÷ suprafață_lac_m2 (sau capacitate_mw * 1e6 / suprafata)
    densitate_existenta = get_raw("densitate_putere_w_m2")
    if densitate_existenta is not None:
        try:
            derivate["densitate_putere_w_m2"] = (float(densitate_existenta), f"densitate declarată = {densitate_existenta} W/m2")
        except (ValueError, TypeError):
            pass
    else:
        p_w = get_raw("putere_instalata_w")
        cap_mw = get_raw("capacitate_mw")
        suprafata_lac = get_raw("suprafata_lac_m2")
        if suprafata_lac is not None:
            try:
                s_lac = float(suprafata_lac)
                if s_lac > 0:
                    if p_w is not None:
                        val_w = float(p_w)
                        dens = round(val_w / s_lac, 2)
                        formula = f"densitate_putere_w_m2 = {val_w} W / {s_lac} m2 = {dens} W/m2"
                        derivate["densitate_putere_w_m2"] = (dens, formula)
                    elif cap_mw is not None:
                        val_w = float(cap_mw) * 1_000_000.0
                        dens = round(val_w / s_lac, 2)
                        formula = f"densitate_putere_w_m2 = ({cap_mw} MW x 1.000.000) / {s_lac} m2 = {dens} W/m2"
                        derivate["densitate_putere_w_m2"] = (dens, formula)
            except (ValueError, TypeError):
                pass

    # 5. factor_capacitate
    # Formula: productie_anuala_mwh / (capacitate_mw x 8760)
    prod_mwh = get_raw("productie_anuala_mwh")
    cap_mw = get_raw("capacitate_mw")
    if prod_mwh is not None and cap_mw is not None:
        try:
            p_mwh = float(prod_mwh)
            c_mw = float(cap_mw)
            if c_mw > 0:
                fc = round(p_mwh / (c_mw * 8760.0), 4)
                formula = f"factor_capacitate = {p_mwh} MWh / ({c_mw} MW x 8760h) = {fc:.4f} ({fc:.1%})"
                derivate["factor_capacitate"] = (fc, formula)
        except (ValueError, TypeError):
            pass

    # 6. ped_fata_de_nzeb
    # Formula: ped_cladire / prag_nzeb_national
    ped_cladire = get_raw("ped_kwh_m2") or get_raw("epc_energie_finala")
    prag_nzeb = get_raw("prag_nzeb_national") or get_raw("nzeb_referinta")
    if ped_cladire is not None and prag_nzeb is not None:
        try:
            p_clad = float(ped_cladire)
            p_nzeb = float(prag_nzeb)
            if p_nzeb > 0:
                ratio = round(p_clad / p_nzeb, 4)
                formula = f"ped_fata_de_nzeb = {p_clad} / {p_nzeb} = {ratio:.2f}"
                derivate["ped_fata_de_nzeb"] = (ratio, formula)
        except (ValueError, TypeError):
            pass

    return derivate


# ---------------------------------------------------------------------------
# Extragere și rezolvare valori de câmpuri
# ---------------------------------------------------------------------------

def obtine_valoare_camp(
    stare: StareDosar,
    camp_nume: str,
    context_item: dict | None = None,
) -> tuple[Any, str]:
    """Extrage valoarea unui câmp din starea dosarului sau contextul curent.
    
    Ordinea de căutare:
    1. context_item (când se evaluează o listă de elemente, ex. vehicule)
    2. stare.extras.indicatori[camp_nume]
    3. getattr(stare.extras, camp_nume)
    4. rezultate unelte (ex. verifica_firma, cauta_certificat)
    5. câmpuri derivate calculate
    
    Întoarce: (valoare, sursa_dovada)
    """
    # 1. Context local (item din listă)
    if context_item and camp_nume in context_item:
        val = context_item[camp_nume]
        if isinstance(val, Camp):
            return val.valoare, val.sursa or "listă elemente"
        return val, "listă elemente"

    # 2. Indicatori extrași
    if stare.extras.indicatori and camp_nume in stare.extras.indicatori:
        c = stare.extras.indicatori[camp_nume]
        if c is not None:
            return c.valoare, c.sursa or f"indicator:{camp_nume}"

    # 3. Câmpuri directe din DosarExtras
    if hasattr(stare.extras, camp_nume):
        attr_val = getattr(stare.extras, camp_nume)
        if isinstance(attr_val, Camp):
            return attr_val.valoare, attr_val.sursa or f"extras.{camp_nume}"
        elif attr_val is not None:
            return attr_val, f"extras.{camp_nume}"

    # 4. Rezultate din unelte
    # CAEN
    if camp_nume in ("caen_imprumutat", "caen", "cod_caen"):
        res_anaf = stare.rezultate_tools.get("verifica_firma")
        if res_anaf and res_anaf.gasit and isinstance(res_anaf.date, dict):
            caen = res_anaf.date.get("date_generale", {}).get("cod_CAEN") or res_anaf.date.get("cod_CAEN") or res_anaf.date.get("caen")
            if caen:
                return str(caen).strip(), "ANAF API (verifica_firma)"
        if stare.dosar_folder:
            cale_anaf = Path(stare.dosar_folder) / "05_raspuns_anaf.json"
            if cale_anaf.exists():
                try:
                    with open(cale_anaf, "r", encoding="utf-8") as f:
                        d_anaf = json.load(f)
                    found = d_anaf.get("found", [])
                    if found:
                        c_val = found[0].get("date_generale", {}).get("cod_CAEN")
                        if c_val:
                            return str(c_val).strip(), "05_raspuns_anaf.json"
                except Exception:
                    pass

    # Fallback pentru subcategorie/tehnologie/tip_proiect/tip_masura
    if camp_nume in ("tip", "tehnologie", "tip_proiect", "tip_masura", "subcategorie"):
        if hasattr(stare.extras, "subcategorie") and stare.extras.subcategorie:
            subcat_val = stare.extras.subcategorie.valoare if isinstance(stare.extras.subcategorie, Camp) else stare.extras.subcategorie
            if subcat_val:
                return subcat_val, "extras.subcategorie"

    # Certificare
    if camp_nume.startswith("certificare_"):
        res_cert = stare.rezultate_tools.get("cauta_certificat")
        if res_cert and res_cert.gasit and isinstance(res_cert.date, dict):
            sub = camp_nume.replace("certificare_", "")
            if sub in ("nivel", "rating"):
                return res_cert.date.get("rating"), "registru BREEAM (cauta_certificat)"
            if sub in ("stadiu", "stage"):
                return res_cert.date.get("stage") or res_cert.date.get("stadiu"), "registru BREEAM (cauta_certificat)"
            if sub == "sistem":
                return res_cert.date.get("sistem") or "BREEAM", "registru certificare"
        if stare.dosar_folder:
            cale_breeam = Path(stare.dosar_folder) / "02_registru_breeam.json"
            if cale_breeam.exists():
                try:
                    with open(cale_breeam, "r", encoding="utf-8") as f:
                        d_breeam = json.load(f)
                    sub = camp_nume.replace("certificare_", "")
                    if sub in ("nivel", "rating"):
                        return d_breeam.get("rating"), "02_registru_breeam.json"
                    if sub in ("stadiu", "stage"):
                        return d_breeam.get("stage") or d_breeam.get("stadiu"), "02_registru_breeam.json"
                    if sub == "sistem":
                        return d_breeam.get("sistem") or "BREEAM", "02_registru_breeam.json"
                except Exception:
                    pass

    # 5. Câmpuri calculate
    derivate = calculeaza_campuri_derivate(stare)
    if camp_nume in derivate:
        return derivate[camp_nume]

    # Cazul în care se cere direct o valoare din extras_mock / dicționar
    return None, "lipsă"


# ---------------------------------------------------------------------------
# Evaluator generic de condiții și reguli
# ---------------------------------------------------------------------------

def _compara_valori(val_obtinuta: Any, operator: str, val_tinta: Any) -> bool:
    """Compară două valori după operatorul matematic specificat."""
    if val_obtinuta is None:
        return False

    # Tratare booleeni (punctul 3 din Partea 1)
    if isinstance(val_tinta, bool):
        if isinstance(val_obtinuta, bool):
            val_bool = val_obtinuta
        elif isinstance(val_obtinuta, (int, float)):
            val_bool = bool(val_obtinuta)
        else:
            val_bool = str(val_obtinuta).strip().lower() in ("true", "da", "yes", "1")

        if operator in ("==", "="):
            return val_bool is val_tinta
        elif operator in ("!=", "<>"):
            return val_bool is not val_tinta
        return False

    try:
        f_obt = float(val_obtinuta)
        f_tinta = float(val_tinta)
        if operator == "<":
            return f_obt < f_tinta
        elif operator in ("<=", "=<"):
            return f_obt <= f_tinta
        elif operator in ("==", "="):
            return abs(f_obt - f_tinta) < 1e-6
        elif operator in ("!=", "<>"):
            return abs(f_obt - f_tinta) >= 1e-6
        elif operator in (">=", "=>"):
            return f_obt >= f_tinta
        elif operator == ">":
            return f_obt > f_tinta
    except (ValueError, TypeError):
        pass

    # Comparare ca șiruri de caractere (cu ignorare diacritice și majuscule)
    s_obt = strip_accents(val_obtinuta)
    s_tinta = strip_accents(val_tinta)
    if operator in ("==", "="):
        return s_obt == s_tinta
    elif operator in ("!=", "<>"):
        return s_obt != s_tinta
    return False


def _verifica_aplica_daca(regula: dict, stare: StareDosar, context_item: dict | None = None) -> bool:
    """Verifică dacă o regulă se aplică dosarului/contextului curent."""
    aplica = regula.get("aplica_daca")
    if not aplica or not isinstance(aplica, dict):
        return True

    for k, v_asteptata in aplica.items():
        v_reala, _ = obtine_valoare_camp(stare, k, context_item)
        if v_reala is None:
            # Verificăm dacă cheia se află în subcategorie sau categorie
            if k == "tip" and hasattr(stare.extras, "subcategorie") and stare.extras.subcategorie:
                v_reala = stare.extras.subcategorie.valoare
            elif k == "tehnologie" and hasattr(stare.extras, "subcategorie") and stare.extras.subcategorie:
                v_reala = stare.extras.subcategorie.valoare
            elif k == "tip_proiect" and hasattr(stare.extras, "subcategorie") and stare.extras.subcategorie:
                v_reala = stare.extras.subcategorie.valoare
            elif k == "tip_masura" and hasattr(stare.extras, "subcategorie") and stare.extras.subcategorie:
                v_reala = stare.extras.subcategorie.valoare

        if v_reala is None:
            return False

        # Condiție numerică ca șir, ex: "<=2020", ">2020"
        if isinstance(v_asteptata, str) and (v_asteptata.startswith(("<=", ">=", "<", ">", "=="))):
            op = v_asteptata[:2] if v_asteptata[:2] in ("<=", ">=", "==") else v_asteptata[:1]
            val_tinta_str = v_asteptata[len(op):].strip()
            if not _compara_valori(v_reala, op, val_tinta_str):
                return False
            continue

        # Listă de valori permise
        if isinstance(v_asteptata, list):
            s_reala = str(v_reala).strip().lower()
            if not any(str(x).strip().lower() == s_reala for x in v_asteptata):
                return False
            continue

        # Comparare booleană sau egalitate
        if isinstance(v_asteptata, bool):
            b_reala = v_reala if isinstance(v_reala, bool) else str(v_reala).strip().lower() in ("true", "da", "yes", "1")
            if b_reala != v_asteptata:
                return False
            continue

        # Egalitate simplă ca string
        if str(v_reala).strip().lower() != str(v_asteptata).strip().lower():
            return False

    return True


# ---------------------------------------------------------------------------
# Evaluare regulă individuală
# ---------------------------------------------------------------------------

def evalueaza_regula(
    regula: dict,
    stare: StareDosar,
    context_item: dict | None = None,
) -> Optional[RezultatRegula]:
    """Evaluează o definiție de regulă din YAML împotriva stării dosarului."""
    regula_id = regula.get("id", "UNKNOWN")
    nume = regula.get("nume", regula_id)
    sursa_fw = regula.get("sursa", "RBI Framework")
    tip = regula.get("tip")
    camp = regula.get("camp")
    daca_lipseste: RezultatTip = regula.get("daca_lipseste", "NEEVALUABIL")

    # Deducere tip dacă nu este specificat explicit în sub-condiții
    if not tip:
        if "operator" in regula:
            tip = "prag"
        elif "in_lista" in regula:
            tip = "lista"
        elif "conditii" in regula or "cai" in regula:
            tip = "oricare"
        elif "valoare" in regula and isinstance(regula["valoare"], bool):
            tip = "da_nu"

    # 1. Verificare aplicabilitate (aplica_daca)
    if not _verifica_aplica_daca(regula, stare, context_item):
        return None

    # 2. Caz informativ
    if tip == "informativ":
        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK",
            dovada=f"{nume}: respectat conform cerințelor descriptive ({regula.get('nota', '')})",
            sursa_framework=sursa_fw,
        )

    # 3. Caz monitorizare
    if tip == "monitorizare":
        val_stadiu, _ = obtine_valoare_camp(stare, camp or "certificare_stadiu", context_item)
        val_stadiu_str = str(val_stadiu or "").lower()
        stadiu_clad = str(getattr(stare.extras, "stadiu_cladire", None) and stare.extras.stadiu_cladire.valoare or "").lower()
        if "final" in val_stadiu_str or ("final" in stadiu_clad and not "interim" in val_stadiu_str):
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="OK",
                dovada=f"{nume}: certificare/stadiu final confirmat ({val_stadiu or stadiu_clad})",
                sursa_framework=sursa_fw,
            )
        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK_CONDITIONAT",
            dovada=f"{nume}: necesită monitorizare periodică (stadiu: {val_stadiu or 'în derulare'})",
            sursa_framework=sursa_fw,
        )

    # 4. Agregare OR (oricare)
    if tip == "oricare":
        conditii = regula.get("conditii") or regula.get("cai") or []
        rezultate_sub: list[RezultatRegula] = []
        for cond in conditii:
            res_sub = evalueaza_regula(cond, stare, context_item)
            if res_sub:
                rezultate_sub.append(res_sub)

        if not rezultate_sub:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: nicio condiție/cale evaluabilă din lista 'oricare'",
                sursa_framework=sursa_fw,
            )

        # Dacă oricare este OK -> regula e OK
        ok_res = next((r for r in rezultate_sub if r.rezultat == "OK"), None)
        if ok_res:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="OK",
                dovada=f"{nume}: îndeplinită prin sub-regula {ok_res.regula_id} ({ok_res.dovada})",
                sursa_framework=sursa_fw,
            )

        # Dacă oricare este OK_CONDITIONAT -> regula e OK_CONDITIONAT
        cond_res = next((r for r in rezultate_sub if r.rezultat == "OK_CONDITIONAT"), None)
        if cond_res:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="OK_CONDITIONAT",
                dovada=f"{nume}: îndeplinită condiționat prin {cond_res.regula_id} ({cond_res.dovada})",
                sursa_framework=sursa_fw,
            )

        # Dacă toate sunt NEEVALUABIL -> NEEVALUABIL
        if all(r.rezultat == "NEEVALUABIL" for r in rezultate_sub):
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: toate condițiile alternative sunt neevaluabile din lipsă date",
                sursa_framework=sursa_fw,
            )

        # Altfel -> NU
        motive_nu = "; ".join(f"{r.regula_id}: {r.dovada}" for r in rezultate_sub)
        return RezultatRegula(
            regula_id=regula_id,
            rezultat="NU",
            dovada=f"{nume}: nicio cale din 'oricare' nu a fost îndeplinită ({motive_nu})",
            sursa_framework=sursa_fw,
        )

    # 5. Agregare AND (toate)
    if tip == "toate":
        conditii = regula.get("conditii") or []
        rezultate_sub: list[RezultatRegula] = []
        for cond in conditii:
            res_sub = evalueaza_regula(cond, stare, context_item)
            if res_sub:
                rezultate_sub.append(res_sub)

        if not rezultate_sub:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: nicio condiție specificată pentru agregarea 'toate'",
                sursa_framework=sursa_fw,
            )

        if any(r.rezultat == "NU" for r in rezultate_sub):
            picate = [r for r in rezultate_sub if r.rezultat == "NU"]
            dovada = "; ".join(f"{p.regula_id}: {p.dovada}" for p in picate)
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="NU",
                dovada=f"{nume}: cel puțin o condiție obligatorie a picat: {dovada}",
                sursa_framework=sursa_fw,
            )

        if any(r.rezultat == "SEMNAL" for r in rezultate_sub):
            semnale = [r for r in rezultate_sub if r.rezultat == "SEMNAL"]
            dovada = "; ".join(f"{s.regula_id}: {s.dovada}" for s in semnale)
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="SEMNAL",
                dovada=f"{nume}: semnal la verificarea condițiilor: {dovada}",
                sursa_framework=sursa_fw,
            )

        if any(r.rezultat == "NEEVALUABIL" for r in rezultate_sub):
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: date lipsă pentru unele condiții obligatorii",
                sursa_framework=sursa_fw,
            )

        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK",
            dovada=f"{nume}: toate condițiile au fost îndeplinite cu succes",
            sursa_framework=sursa_fw,
        )

    # 6. Lista cu ordine (ex. BREEAM, LEED, DGNB, OGNI, EDGE)
    if tip == "lista_cu_ordine":
        sistem_val, sursa_sis = obtine_valoare_camp(stare, regula.get("camp_sistem", "certificare_sistem"), context_item)
        nivel_val, sursa_niv = obtine_valoare_camp(stare, regula.get("camp_nivel", "certificare_nivel"), context_item)
        stadiu_val, sursa_std = obtine_valoare_camp(stare, regula.get("camp_stadiu", "certificare_stadiu"), context_item)

        if not sistem_val or not nivel_val:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: lipsesc detalii de certificare (sistem={sistem_val}, nivel={nivel_val})",
                sursa_framework=sursa_fw,
            )

        sistem_str = str(sistem_val).strip().upper()
        # Normalizare sistem (ex: "BREEAM-TEST" -> "BREEAM")
        sisteme_suportate = ["BREEAM", "LEED", "DGNB", "OGNI", "EDGE"]
        matched_sistem = next((s for s in sisteme_suportate if s in sistem_str), None)
        if not matched_sistem:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="NU",
                dovada=f"{nume}: sistem de certificare nerecunoscut ({sistem_val})",
                sursa_framework=sursa_fw,
            )

        ordinea_dict = regula.get("ordinea", {})
        ierarhie = ordinea_dict.get(matched_sistem, [])
        praguri_minime = regula.get("praguri_minime", {})
        prag_minim = praguri_minime.get(matched_sistem)

        ierarhie_lower = [str(x).strip().lower() for x in ierarhie]
        nivel_lower = str(nivel_val).strip().lower()
        prag_lower = str(prag_minim).strip().lower() if prag_minim else ""

        if nivel_lower not in ierarhie_lower:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="NU",
                dovada=f"{nume}: nivelul '{nivel_val}' nu există în ierarhia {matched_sistem}",
                sursa_framework=sursa_fw,
            )

        idx_obtinut = ierarhie_lower.index(nivel_lower)
        idx_minim = ierarhie_lower.index(prag_lower) if prag_lower in ierarhie_lower else 0

        if idx_obtinut < idx_minim:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="NU",
                dovada=f"{nume}: nivel obținut '{nivel_val}' este sub pragul minim '{prag_minim}' pentru {matched_sistem}",
                sursa_framework=sursa_fw,
            )

        # Condiție suplimentară (ex: EDGE Basic necesită >= 30% economie)
        cond_suplimentara = regula.get("conditie_suplimentara", {}).get(matched_sistem)
        if cond_suplimentara:
            c_camp = cond_suplimentara.get("camp")
            c_op = cond_suplimentara.get("operator", ">=")
            c_val = cond_suplimentara.get("valoare")
            val_supl, _ = obtine_valoare_camp(stare, c_camp, context_item)
            if val_supl is None or not _compara_valori(val_supl, c_op, c_val):
                return RezultatRegula(
                    regula_id=regula_id,
                    rezultat="NU",
                    dovada=f"{nume}: certificarea {matched_sistem} nu îndeplinește condiția suplimentară ({c_camp} {c_op} {c_val})",
                    sursa_framework=sursa_fw,
                )

        # Verificare stadiu (pre-certificat / interim / aplicat -> monitorizare)
        stadiu_str = str(stadiu_val or "").strip().lower()
        stadiu_neconfirmat = regula.get("stadiu_neconfirmat", "OK_CONDITIONAT")
        if any(w in stadiu_str for w in ("interim", "pre", "aplicat", "proiect")):
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=stadiu_neconfirmat,
                dovada=f"{nume}: certificare {matched_sistem} {nivel_val} validă, dar stadiul este intermediar ({stadiu_val})",
                sursa_framework=sursa_fw,
            )

        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK",
            dovada=f"{nume}: certificare {matched_sistem} {nivel_val} (stadiu: {stadiu_val or 'Final'}) respectă cerințele",
            sursa_framework=sursa_fw,
        )

    # 7. Prag dependent de dată (Grandfathering G-05)
    if tip == "prag_dependent_de_data":
        camp_data_nume = regula.get("camp_data", "data_marcare_verde")
        data_val, sursa_dt = obtine_valoare_camp(stare, camp_data_nume, context_item)

        d_ref = _parse_data(data_val)
        folosit_proxy_aprobare = False

        if not d_ref:
            # G-05: dacă data_marcare_verde lipsește, se folosește data_aprobare + SEMNAL informativ
            data_aprobare_val, _ = obtine_valoare_camp(stare, "data_aprobare", context_item)
            d_ref = _parse_data(data_aprobare_val)
            folosit_proxy_aprobare = True
            if not any("G-05" in a for a in stare.actiuni):
                stare.actiuni.append(
                    "G-05: Lipsă data_marcare_verde; s-a utilizat data_aprobare ca proxy conform regulilor de grandfathering."
                )

        if not d_ref:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: lipsă dată de marcare verde sau aprobare pentru stabilirea pragului istoric",
                sursa_framework=sursa_fw,
            )

        # Găsim intervalul aplicabil
        praguri = regula.get("praguri", [])
        prag_ales = None
        for p in praguri:
            pana_la = _parse_data(p.get("pana_la"))
            de_la = _parse_data(p.get("de_la"))
            if pana_la and d_ref <= pana_la:
                prag_ales = p
                break
            if de_la and d_ref >= de_la:
                prag_ales = p
                break

        if not prag_ales:
            prag_ales = praguri[-1] if praguri else {}

        op = prag_ales.get("operator", "<=")
        val_tinta = prag_ales.get("valoare")
        camp_tinta = regula.get("camp")

        val_obtinuta, sursa_val = obtine_valoare_camp(stare, camp_tinta, context_item)
        if val_obtinuta is None:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: lipsă valoare pentru {camp_tinta} la data {d_ref}",
                sursa_framework=sursa_fw,
            )

        trece = _compara_valori(val_obtinuta, op, val_tinta)
        dovada_text = (
            f"{nume}: valoare {camp_tinta}={val_obtinuta} {op} {val_tinta} "
            f"(evaluat la data {d_ref}{' [proxy aprobare]' if folosit_proxy_aprobare else ''})"
        )

        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK" if trece else "NU",
            dovada=dovada_text,
            sursa_framework=sursa_fw,
        )

    # 8. Regulă simplă de prag (prag)
    if tip == "prag":
        camp = regula.get("camp")
        op = regula.get("operator", "<=")
        val_tinta = regula.get("valoare")

        val_obtinuta, sursa_val = obtine_valoare_camp(stare, camp, context_item)
        if val_obtinuta is None:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: valoarea pentru {camp} nu a fost găsită",
                sursa_framework=sursa_fw,
            )

        trece = _compara_valori(val_obtinuta, op, val_tinta)
        dovada_text = f"{nume}: {camp}={val_obtinuta} {op} {val_tinta} ({sursa_val})"
        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK" if trece else "NU",
            dovada=dovada_text,
            sursa_framework=sursa_fw,
        )

    # 9. Apartenență la listă (lista)
    if tip == "lista":
        camp = regula.get("camp")
        lista_permisa = [strip_accents(x) for x in (regula.get("in_lista") or [])]

        val_obtinuta, sursa_val = obtine_valoare_camp(stare, camp, context_item)
        if val_obtinuta is None:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: valoarea pentru {camp} nu a fost găsită",
                sursa_framework=sursa_fw,
            )

        s_val = strip_accents(val_obtinuta)
        trece = s_val in lista_permisa
        dovada_text = f"{nume}: {camp}='{val_obtinuta}' {'este' if trece else 'nu este'} în lista permisă"
        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK" if trece else "NU",
            dovada=dovada_text,
            sursa_framework=sursa_fw,
        )

    # 10. Da / Nu (da_nu)
    if tip == "da_nu":
        camp = regula.get("camp")
        val_tinta = regula.get("valoare", True)

        val_obtinuta, sursa_val = obtine_valoare_camp(stare, camp, context_item)
        if val_obtinuta is None:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: valoarea booleană pentru {camp} nu a fost găsită",
                sursa_framework=sursa_fw,
            )

        trece = _compara_valori(val_obtinuta, "==", val_tinta)
        dovada_text = f"{nume}: {camp}={val_obtinuta} (așteptat {val_tinta})"
        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK" if trece else "NU",
            dovada=dovada_text,
            sursa_framework=sursa_fw,
        )

    # 11. Excludere (excludere)
    if tip == "excludere":
        # Verificare sub-condiție oricare în cadrul excluderii (ex. EE-X1)
        if "oricare" in regula and isinstance(regula["oricare"], list):
            for sub_c in regula["oricare"]:
                camp = sub_c.get("camp")
                val_obtinuta, sursa_val = obtine_valoare_camp(stare, camp, context_item)
                if val_obtinuta is not None:
                    if "in_lista" in sub_c:
                        lista_excl = [str(x).strip().lower() for x in sub_c["in_lista"]]
                        if str(val_obtinuta).strip().lower() in lista_excl:
                            return RezultatRegula(
                                regula_id=regula_id,
                                rezultat="NU",
                                dovada=f"{nume}: exclus pe baza {camp}='{val_obtinuta}' aflat în lista interzisă {lista_excl}",
                                sursa_framework=sursa_fw,
                            )
                    elif "valoare" in sub_c:
                        op = sub_c.get("operator", "==")
                        if _compara_valori(val_obtinuta, op, sub_c["valoare"]):
                            return RezultatRegula(
                                regula_id=regula_id,
                                rezultat="NU",
                                dovada=f"{nume}: exclus pe baza {camp}={val_obtinuta} ({op} {sub_c['valoare']})",
                                sursa_framework=sursa_fw,
                            )
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="OK",
                dovada=f"{nume}: nu se aplică niciun criteriu de excludere",
                sursa_framework=sursa_fw,
            )

        # Verificare CAEN (G-02, GB-X1)
        if "sectoare_excluse_prefixe_caen" in regula or "prefixe_caen_semnal" in regula:
            caen_val, _ = obtine_valoare_camp(stare, regula.get("camp", "caen_imprumutat"), context_item)
            # Verificare chiriași pentru GB-X1
            if regula.get("camp") == "chiriasi_caen" and hasattr(stare.extras, "chiriasi"):
                chiriasi = stare.extras.chiriasi or []
                prefixe_semnal = [str(p) for p in regula.get("prefixe_caen_semnal", [])]
                semnalati = [ch for ch in chiriasi if any(str(ch.caen).startswith(p) for p in prefixe_semnal)]
                if semnalati:
                    detalii_ch = ", ".join(f"{ch.nume} (CAEN {ch.caen})" for ch in semnalati)
                    return RezultatRegula(
                        regula_id=regula_id,
                        rezultat="SEMNAL",
                        dovada=f"{nume}: chiriași cu activități potențial fosile identificați: {detalii_ch}",
                        sursa_framework=sursa_fw,
                    )
                return RezultatRegula(
                    regula_id=regula_id,
                    rezultat="OK",
                    dovada=f"{nume}: niciun chiriaș nu are cod CAEN din lista de semnal",
                    sursa_framework=sursa_fw,
                )

            # Verificare CAEN împrumutat (G-02)
            if not caen_val:
                return RezultatRegula(
                    regula_id=regula_id,
                    rezultat=daca_lipseste,
                    dovada=f"{nume}: lipsă cod CAEN pentru verificarea sectorului exclus",
                    sursa_framework=sursa_fw,
                )

            caen_str = str(caen_val).strip()
            # Prefixe excluse
            sectoare_dict = regula.get("sectoare_excluse_prefixe_caen", {})
            prefixe_excluse: list[str] = []
            if isinstance(sectoare_dict, dict):
                for p_list in sectoare_dict.values():
                    prefixe_excluse.extend([str(x) for x in p_list])
            elif isinstance(sectoare_dict, list):
                prefixe_excluse.extend([str(x) for x in sectoare_dict])

            if any(caen_str.startswith(p) for p in prefixe_excluse):
                return RezultatRegula(
                    regula_id=regula_id,
                    rezultat="NU",
                    dovada=f"{nume}: CAEN {caen_str} face parte dintr-un sector exclus",
                    sursa_framework=sursa_fw,
                )

            prefixe_semnal = [str(x) for x in regula.get("prefixe_caen_semnal", {}).get("productie_energie_electrica", [])]
            if any(caen_str.startswith(p) for p in prefixe_semnal):
                return RezultatRegula(
                    regula_id=regula_id,
                    rezultat="SEMNAL",
                    dovada=f"{nume}: CAEN {caen_str} necesită verificare suplimentară (semnal producție energie)",
                    sursa_framework=sursa_fw,
                )

            return RezultatRegula(
                regula_id=regula_id,
                rezultat="OK",
                dovada=f"{nume}: CAEN {caen_str} nu este în sector exclus",
                sursa_framework=sursa_fw,
            )

        camp = regula.get("camp")
        val_obtinuta, sursa_val = obtine_valoare_camp(stare, camp, context_item)
        if val_obtinuta is None:
            return RezultatRegula(
                regula_id=regula_id,
                rezultat=daca_lipseste,
                dovada=f"{nume}: informație lipsă pentru {camp}",
                sursa_framework=sursa_fw,
            )

        if "in_lista" in regula:
            in_l = [str(x).strip().lower() for x in regula["in_lista"]]
            if str(val_obtinuta).strip().lower() in in_l:
                return RezultatRegula(
                    regula_id=regula_id,
                    rezultat="NU",
                    dovada=f"{nume}: {camp}='{val_obtinuta}' este în lista de excluderi {in_l}",
                    sursa_framework=sursa_fw,
                )
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="OK",
                dovada=f"{nume}: {camp}='{val_obtinuta}' este permis",
                sursa_framework=sursa_fw,
            )

        val_tinta = regula.get("valoare", True)
        if _compara_valori(val_obtinuta, "==", val_tinta):
            return RezultatRegula(
                regula_id=regula_id,
                rezultat="NU",
                dovada=f"{nume}: criteriu de excludere îndeplinit ({camp}={val_obtinuta})",
                sursa_framework=sursa_fw,
            )

        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK",
            dovada=f"{nume}: criteriu de excludere neaplicabil ({camp}={val_obtinuta})",
            sursa_framework=sursa_fw,
        )

    # Tip necunoscut sau neconfigurat
    logger.warning("Tip regulă necunoscut: %s pentru %s", tip, regula_id)
    return RezultatRegula(
        regula_id=regula_id,
        rezultat="NEEVALUABIL",
        dovada=f"Tip regulă necunoscut: {tip}",
        sursa_framework=sursa_fw,
    )


# ---------------------------------------------------------------------------
# Evaluare pe liste (vehicule) - punctul 4 din Partea 1
# ---------------------------------------------------------------------------

def evalueaza_regula_pe_lista(
    regula: dict,
    lista_elemente: list[dict],
    stare: StareDosar,
) -> RezultatRegula:
    """Evaluează o regulă pe fiecare element dintr-o listă (ex. flotă vehicule).
    
    Dacă doar o parte trec:
    - rezultatul regulii conține lista celor care trec și a celor care pică
    - se calculează ponderea eligibilă (pro-rata, Framework p. 19)
    - se notează în stare.impact["pondere_eligibila"] și în stare.actiuni
    """
    regula_id = regula.get("id", "UNKNOWN")
    nume = regula.get("nume", regula_id)
    sursa_fw = regula.get("sursa", "RBI Framework")

    trecute: list[dict] = []
    picate: list[tuple[dict, str]] = []

    for item in lista_elemente:
        res = evalueaza_regula(regula, stare, context_item=item)
        nume_item = item.get("model") or item.get("nume") or str(item)
        if res and res.rezultat in ("OK", "OK_CONDITIONAT"):
            trecute.append(item)
        else:
            motiv = res.dovada if res else "condiție neîndeplinită"
            picate.append((item, motiv))

    total = len(lista_elemente)
    nr_trecute = len(trecute)
    pondere = nr_trecute / total if total > 0 else 0.0

    if nr_trecute == total:
        return RezultatRegula(
            regula_id=regula_id,
            rezultat="OK",
            dovada=f"{nume}: toate cele {total} elemente respectă criteriile",
            sursa_framework=sursa_fw,
        )

    if nr_trecute == 0:
        detalii_picate = "; ".join(f"{i.get('model', 'item')}: {m}" for i, m in picate[:3])
        return RezultatRegula(
            regula_id=regula_id,
            rezultat="NU",
            dovada=f"{nume}: niciun element din {total} nu respectă criteriile ({detalii_picate})",
            sursa_framework=sursa_fw,
        )

    # Parțial eligibil: pro-rata (Framework p. 19)
    stare.impact["pondere_eligibila"] = pondere
    actiune_prorata = (
        f"Finanțare parțial eligibilă (pro-rata): {pondere:.1%} din elemente "
        f"({nr_trecute}/{total}) respectă criteriile verzi (Framework p. 19)."
    )
    if actiune_prorata not in stare.actiuni:
        stare.actiuni.append(actiune_prorata)

    detalii_trecute = ", ".join(str(i.get("model", "item")) for i in trecute)
    detalii_picate = "; ".join(f"{i.get('model', 'item')} ({m})" for i, m in picate)

    return RezultatRegula(
        regula_id=regula_id,
        rezultat="NU",
        dovada=(
            f"{nume}: parțial eligibil ({nr_trecute}/{total} trecute, {pondere:.1%}). "
            f"Trecute: [{detalii_trecute}]; Picate: [{detalii_picate}]"
        ),
        sursa_framework=sursa_fw,
    )


# ---------------------------------------------------------------------------
# Evaluare la nivel de fișier de reguli
# ---------------------------------------------------------------------------

def evalueaza_fisier_reguli(nume_fisier: str, stare: StareDosar) -> list[RezultatRegula]:
    """Evaluează toate regulile aplicabile dintr-un fișier YAML din rules/."""
    data = incarca_reguli_yaml(nume_fisier)
    rezultate: list[RezultatRegula] = []

    # Verificăm dacă există o listă de vehicule / elemente
    lista_vehicule = None
    if stare.extras.indicatori:
        for cheie_l in ("vehicule", "flota", "lista_vehicule"):
            if cheie_l in stare.extras.indicatori and stare.extras.indicatori[cheie_l]:
                val_l = stare.extras.indicatori[cheie_l].valoare
                if isinstance(val_l, list):
                    lista_vehicule = val_l
                    break

    def proceseaza_regula_sau_grup(item: dict) -> None:
        if not isinstance(item, dict):
            return

        rid = item.get("id")
        if rid:
            # Dacă avem o listă de vehicule și regula este una de vehicul (ex. CT-03, CT-04)
            if lista_vehicule and item.get("aplica_daca", {}).get("tip") in ("autoturism_sau_utilitara", "camion"):
                res = evalueaza_regula_pe_lista(item, lista_vehicule, stare)
            else:
                res = evalueaza_regula(item, stare)

            if res:
                rezultate.append(res)
                stare.reguli[res.regula_id] = res
            return

        # Grupuri imbricate (ex: cladire_noua_sau_existenta, renovare, etc.)
        for v in item.values():
            if isinstance(v, list):
                for elem in v:
                    if isinstance(elem, dict):
                        proceseaza_regula_sau_grup(elem)
            elif isinstance(v, dict):
                proceseaza_regula_sau_grup(v)

    # Verificare rutare pe subcategorie (ex. cladire_noua vs renovare vs masura_individuala)
    subcat_val, _ = obtine_valoare_camp(stare, "subcategorie")
    subcat_str = str(subcat_val or "").strip().lower()
    subcategorii_declarate = [str(x).strip().lower() for x in data.get("subcategorii", [])]

    # Parcurgem secțiunile principale
    for cheie, val in data.items():
        if cheie in ("categorie", "sursa", "taxonomie_ue", "subcategorii", "tehnologii", "tipuri", "tipuri_proiect", "indicatori_impact", "portofoliu"):
            continue

        # Dacă fișierul declară subcategorii, evaluăm doar secțiunea specifică (+ excluderi)
        if subcategorii_declarate and cheie.lower() in subcategorii_declarate:
            if subcat_str and cheie.lower() != subcat_str:
                continue
            if not subcat_str and cheie.lower() != subcategorii_declarate[0]:
                continue

        if isinstance(val, list):
            for elem in val:
                if isinstance(elem, dict):
                    proceseaza_regula_sau_grup(elem)
        elif isinstance(val, dict):
            proceseaza_regula_sau_grup(val)

    return rezultate
