"""Verificări de plauzibilitate (anti-greenwashing și erori de unități).

Conform reference/plauzibilitate.yaml:
- Severitate 'blocant' (implicit) -> RezultatRegula cu SEMNAL, care duce la EXCEPTIE_ESCALADARE_COMITET
- Severitate 'informativ' -> Adaugă acțiune în stare.actiuni, nu afectează verdictul final
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from contracts import RezultatRegula, StareDosar
from engine.evaluator_generic import calculeaza_campuri_derivate, obtine_valoare_camp

logger = logging.getLogger(__name__)

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
_PLAUZIBILITATE_CACHE: dict = {}


def incarca_plauzibilitate_yaml() -> dict:
    global _PLAUZIBILITATE_CACHE
    if _PLAUZIBILITATE_CACHE:
        return _PLAUZIBILITATE_CACHE

    cale = REFERENCE_DIR / "plauzibilitate.yaml"
    if cale.exists():
        with open(cale, "r", encoding="utf-8") as f:
            _PLAUZIBILITATE_CACHE = yaml.safe_load(f) or {}
    return _PLAUZIBILITATE_CACHE


def evalueaza_plauzibilitate(stare: StareDosar) -> list[RezultatRegula]:
    """Rulează toate verificările de plauzibilitate pe starea curentă a dosarului."""
    rezultate: list[RezultatRegula] = []
    derivate = calculeaza_campuri_derivate(stare)

    def _val(camp_nume: str) -> Any:
        v, _ = obtine_valoare_camp(stare, camp_nume)
        return v

    # ------------------------------------------------------------ PL-02: registru vs declarație
    # Verificare emisii vehicul (oficial vs declarat)
    emisii_decl = _val("emisii_wltp_gco2_km")
    res_eea = stare.rezultate_tools.get("cauta_emisii_vehicul")
    emisii_oficial = None
    combustibil_oficial = ""
    if res_eea and res_eea.gasit and isinstance(res_eea.date, dict):
        emisii_oficial = res_eea.date.get("emisii_wltp_gco2_km") or res_eea.date.get("emisii_oficiale")
        combustibil_oficial = str(res_eea.date.get("combustibil", "")).lower()
    elif _val("emisii_registru_eea") is not None:
        emisii_oficial = _val("emisii_registru_eea")
        combustibil_oficial = str(_val("combustibil_registru_eea") or "diesel").lower()
    elif stare.dosar_folder:
        # Caută exclusiv în _brut sau în foldere generate de extracție
        folder_brut = Path(stare.dosar_folder) / "_brut"
        if folder_brut.is_dir():
            candidati_eea = [folder_brut / "03_registru_eea.json"] + [p for p in folder_brut.glob("*eea*.json") if p.name != "03_registru_eea.json"]
            for cale_eea in candidati_eea:
                if cale_eea.exists():
                    try:
                        import json
                        with open(cale_eea, "r", encoding="utf-8") as f:
                            d_eea = json.load(f)
                        date_eea = d_eea.get("date") or d_eea.get("continut_json") or d_eea
                        emisii_oficial = date_eea.get("emisii_wltp_gco2_km") or date_eea.get("emisii_oficiale")
                        combustibil_oficial = str(date_eea.get("combustibil", "")).lower()
                        if emisii_oficial is not None:
                            break
                    except Exception:
                        pass

    if emisii_decl is not None and emisii_oficial is not None:
        try:
            if abs(float(emisii_decl) - float(emisii_oficial)) > 1.0 or (float(emisii_decl) == 0 and "diesel" in combustibil_oficial):
                rezultate.append(RezultatRegula(
                    regula_id="PL-02",
                    rezultat="SEMNAL",
                    dovada=(
                        f"Valoarea declarată a emisiilor ({emisii_decl} g/km) diferă de datele oficiale "
                        f"din registrul EEA ({emisii_oficial} g/km, combustibil: {combustibil_oficial}). "
                        "Registrul oficial primează conform metodologiei."
                    ),
                    sursa_framework="reference/plauzibilitate.yaml (PL-02)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-03: afirmațiile clientului
    afirmatii = stare.extras.afirmatii_client or []
    if afirmatii:
        # Căutăm procente afirmate (ex: 60%)
        import re
        for af in afirmatii:
            match = re.search(r"(\d+)\s*%", af)
            if match:
                proc_declarat = float(match.group(1)) / 100.0
                # Comparăm cu imbunatatire_eficienta_pct sau reducere_ped_pct
                proc_calc = None
                if "imbunatatire_eficienta_pct" in derivate:
                    proc_calc = float(derivate["imbunatatire_eficienta_pct"][0])
                elif "reducere_ped_pct" in derivate:
                    proc_calc = float(derivate["reducere_ped_pct"][0])

                if proc_calc is not None and abs(proc_declarat - proc_calc) > 0.10:
                    actiune_text = (
                        f"Verificare PL-03: Afirmația de marketing a clientului ('{af}') declară economii de "
                        f"{proc_declarat:.0%}, dar calculul tehnic indică doar {proc_calc:.0%}. "
                        "Impactul calculat se bazează pe cifrele tehnice verificate."
                    )
                    if actiune_text not in stare.actiuni:
                        stare.actiuni.append(actiune_text)

    # ------------------------------------------------------------ PL-10: ped < energie_finala
    ped_val = _val("ped_kwh_m2")
    ef_val = _val("energie_finala_kwh_m2") or _val("epc_energie_finala")
    if ped_val is not None and ef_val is not None:
        try:
            if float(ped_val) < float(ef_val):
                rezultate.append(RezultatRegula(
                    regula_id="PL-10",
                    rezultat="SEMNAL",
                    dovada=f"Energia primară ({ped_val} kWh/m2) este mai mică decât energia finală ({ef_val} kWh/m2). Posibilă doar cu producție proprie regenerabilă majoră.",
                    sursa_framework="reference/plauzibilitate.yaml (PL-10)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-11: consum nerezidențial < 20
    if ef_val is not None:
        try:
            if 0 < float(ef_val) < 20:
                rezultate.append(RezultatRegula(
                    regula_id="PL-11",
                    rezultat="SEMNAL",
                    dovada=f"Consum final ({ef_val} kWh/m2) neobișnuit de mic pentru o clădire nerezidențială. Posibilă eroare de unități sau de pagină.",
                    sursa_framework="reference/plauzibilitate.yaml (PL-11)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-12: ped_dupa > ped_inainte (renovare)
    ped_in = _val("ped_inainte_kwh_m2") or _val("ped_inainte")
    ped_dp = _val("ped_dupa_kwh_m2") or _val("ped_dupa")
    if ped_in is not None and ped_dp is not None:
        try:
            if float(ped_dp) > float(ped_in):
                rezultate.append(RezultatRegula(
                    regula_id="PL-12",
                    rezultat="SEMNAL",
                    dovada=f"Consumul de energie primară după renovare ({ped_dp}) este mai mare decât cel inițial ({ped_in}).",
                    sursa_framework="reference/plauzibilitate.yaml (PL-12)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-20: factor de capacitate
    fc_val = derivate.get("factor_capacitate", (None, ""))[0]
    if fc_val is not None:
        try:
            fc_float = float(fc_val)
            subcat = str(_val("subcategorie") or _val("tehnologie") or "").lower()
            prag_fc = 0.50
            if "solar" in subcat or "fotovoltaic" in subcat:
                prag_fc = 0.25
            elif "eolian" in subcat:
                prag_fc = 0.55
            elif "hidro" in subcat:
                prag_fc = 0.75
            elif "geotermal" in subcat:
                prag_fc = 0.95

            if fc_float > prag_fc:
                rezultate.append(RezultatRegula(
                    regula_id="PL-20",
                    rezultat="SEMNAL",
                    dovada=f"Factor de capacitate imposibil ({fc_float:.1%}) depășește pragul maxim realist ({prag_fc:.1%}) pentru tehnologia '{subcat}'. Verificare eroare unități (kWh vs MWh).",
                    sursa_framework="reference/plauzibilitate.yaml (PL-20)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-21: densitate hidro vs tehnic
    d_decl = _val("densitate_putere_w_m2")
    p_w = _val("putere_instalata_w")
    s_lac = _val("suprafata_lac_m2")
    if d_decl is not None and p_w is not None and s_lac is not None:
        try:
            d_calc = float(p_w) / float(s_lac)
            if abs(float(d_decl) - d_calc) / max(d_calc, 0.001) > 0.10:
                rezultate.append(RezultatRegula(
                    regula_id="PL-21",
                    rezultat="SEMNAL",
                    dovada=f"Densitatea declarată ({d_decl} W/m2) diferă cu peste 10% de calculul tehnic ({d_calc:.2f} W/m2).",
                    sursa_framework="reference/plauzibilitate.yaml (PL-21)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-30: PUE data center
    pue_val = _val("pue_anualizat") or _val("pue")
    if pue_val is not None:
        try:
            p_val = float(pue_val)
            if p_val < 1.0:
                rezultate.append(RezultatRegula(
                    regula_id="PL-30",
                    rezultat="SEMNAL",
                    dovada=f"PUE anualizat ({p_val}) este fizic imposibil (< 1.0). Valoare respinsă.",
                    sursa_framework="reference/plauzibilitate.yaml (PL-30)",
                ))
            elif 1.0 <= p_val < 1.1:
                rezultate.append(RezultatRegula(
                    regula_id="PL-30",
                    rezultat="SEMNAL",
                    dovada=f"PUE ({p_val}) este excepțional de scăzut (< 1.1). Necesită dovada măsurătorii anuale oficiale.",
                    sursa_framework="reference/plauzibilitate.yaml (PL-30)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-31: îmbunătățire eficiență > 80%
    imb_val = derivate.get("imbunatatire_eficienta_pct", (None, ""))[0] or _val("imbunatatire_eficienta_pct")
    if imb_val is not None:
        try:
            if float(imb_val) > 0.80:
                rezultate.append(RezultatRegula(
                    regula_id="PL-31",
                    rezultat="SEMNAL",
                    dovada=f"Îmbunătățirea eficienței industriale declarată ({float(imb_val):.1%}) depășește pragul plauzibil de 80%.",
                    sursa_framework="reference/plauzibilitate.yaml (PL-31)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-40: consum kWh/km vehicul
    c_kwh = _val("consum_kwh_km")
    if c_kwh is not None:
        try:
            c_val = float(c_kwh)
            if c_val < 0.10 or c_val > 0.35:
                rezultate.append(RezultatRegula(
                    regula_id="PL-40",
                    rezultat="SEMNAL",
                    dovada=f"Consum electric declarat ({c_val} kWh/km) este în afara intervalului tipic (0.10 - 0.35 kWh/km).",
                    sursa_framework="reference/plauzibilitate.yaml (PL-40)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-41: 0 g/km dar combustibil fosil
    comb_val = str(_val("combustibil") or _val("propulsie") or "").lower()
    if emisii_decl is not None and comb_val:
        try:
            if float(emisii_decl) == 0 and any(f in comb_val for f in ("hibrid", "benzina", "diesel", "gpl")):
                rezultate.append(RezultatRegula(
                    regula_id="PL-41",
                    rezultat="SEMNAL",
                    dovada=f"Contradicție: emisii declarate 0 g/km, dar tipul de combustibil este '{comb_val}'.",
                    sursa_framework="reference/plauzibilitate.yaml (PL-41)",
                ))
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------ PL-51: procente în afara 0-1
    for camp_pct in ("cota_banca", "pondere_aluminiu_reciclat", "eficienta_captare_pct"):
        v_pct = _val(camp_pct)
        if v_pct is not None:
            try:
                f_pct = float(v_pct)
                if f_pct < 0 or f_pct > 1.0:
                    rezultate.append(RezultatRegula(
                        regula_id="PL-51",
                        rezultat="SEMNAL",
                        dovada=f"Câmpul procentual '{camp_pct}' are valoarea {f_pct}, fiind în afara intervalului permis [0, 1]. Probabil procent nenormalizat.",
                        sursa_framework="reference/plauzibilitate.yaml (PL-51)",
                    ))
            except (ValueError, TypeError):
                pass

    for r in rezultate:
        stare.reguli[r.regula_id] = r

    return rezultate

