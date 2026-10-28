"""Calculul impactului de mediu (CO2 evitat, energie economisită) pe categorii.

Conform metodologiei din reference/metodologie_impact.yaml:
- RBI Sustainability Bond Allocation and Impact Report 2025, p. 22-28
- Păstrează pașii transparenți de calcul în lista 'pasi'
- Utilizează cota băncii și factorul de emisie de rețea (din tool-ul factor_emisie_tara sau valoarea proxy de 0.25 kgCO2/kWh)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from contracts import StareDosar
from engine.evaluator_generic import obtine_valoare_camp

logger = logging.getLogger(__name__)

# Valori proxy de rezervă din reference/metodologie_impact.yaml și factori_referinta.yaml
PROXY_BASELINE_KWH_M2 = 297.0
PROXY_FACTOR_EMISIE_KGCO2_KWH = 0.25          # kgCO2/kWh = tCO2/MWh
PROXY_DISTANTA_MEDIE_VEHICUL_KM = 17746.0     # Impact Report p. 15
PROXY_EMISIE_MEDIE_TERMIC_G_KM = 120.0        # gCO2/km referință parc convențional


def obtine_factor_emisie_retea(stare: StareDosar) -> tuple[float, str]:
    """Obține factorul de emisie al rețelei (din tool sau proxy de rezervă)."""
    res_tool = stare.rezultate_tools.get("factor_emisie_tara")
    if res_tool and res_tool.gasit and isinstance(res_tool.date, dict):
        fe = res_tool.date.get("factor_emisie_kgco2_kwh")
        if fe is not None:
            return float(fe), res_tool.sursa or "Tool factor_emisie_tara (Ember)"

    return PROXY_FACTOR_EMISIE_KGCO2_KWH, "Proxy de rezervă: 0.25 kgCO2/kWh (Ember / Our World in Data proxy)"


def calculeaza_impact_categorie(categorie: str, stare: StareDosar) -> dict[str, Any]:
    """Calculează impactul pe categoria specificată conform formulelor din reference/metodologie_impact.yaml."""
    cat_norm = str(categorie or "").strip().lower()
    cota_banca_val, _ = obtine_valoare_camp(stare, "cota_banca")
    cota_banca = float(cota_banca_val or 1.0)
    factor_emisie, sursa_fe = obtine_factor_emisie_retea(stare)

    impact_data: dict[str, Any] = {
        "categorie": cat_norm,
        "cota_banca": cota_banca,
        "factor_emisie_kgco2_kwh": factor_emisie,
        "sursa_factor_emisie": sursa_fe,
        "pasi": [],
        "rezultat_tco2_an": None,
    }

    def _val(camp_nume: str, implicit: Any = None) -> Any:
        v, _ = obtine_valoare_camp(stare, camp_nume)
        return v if v is not None else implicit

    # -----------------------------------------------------------------------
    # 1. Clădiri Verzi (Green Buildings)
    # -----------------------------------------------------------------------
    if cat_norm in ("green_buildings", "cladiri"):
        stadiu = str(_val("stadiu_cladire", "")).lower()
        if "construc" in stadiu:
            impact_data["pasi"].append(
                "Clădire în curs de construcție: impactul CO2 nu se calculează conform Allocation & Impact Report 2025, p. 18."
            )
            stare.impact = impact_data
            return impact_data

        ef_val = _val("energie_finala_kwh_m2") or _val("epc_energie_finala")
        suprafata_val = _val("suprafata_m2")

        if ef_val is None or suprafata_val is None:
            impact_data["pasi"].append("Date energetice insuficiente (lipsă energie finală sau suprafață).")
            stare.impact = impact_data
            return impact_data

        try:
            ef = float(ef_val)
            suprafata = float(suprafata_val)
            dif_consum = PROXY_BASELINE_KWH_M2 - ef
            kwh_total = dif_consum * suprafata
            kwh_banca = kwh_total * cota_banca
            kg_co2 = kwh_banca * factor_emisie
            tco2_an = round(kg_co2 / 1000.0, 1)

            impact_data["formula"] = "(baseline - energie_finala) x suprafata x cota_banca x factor_emisie / 1000"
            impact_data["sursa"] = "Allocation & Impact Report 2025, p. 22"
            impact_data["rezultat_tco2_an"] = tco2_an
            impact_data["pasi"] = [
                f"1. Diferență consum: {PROXY_BASELINE_KWH_M2:.0f} - {ef:.1f} = {dif_consum:.1f} kWh/m2/an",
                f"2. x suprafață: {dif_consum:.1f} x {suprafata:.0f} = {kwh_total:,.0f} kWh/an",
                f"3. x cota băncii ({cota_banca:.2f}): = {kwh_banca:,.0f} kWh/an",
                f"4. x factor emisie ({factor_emisie} kgCO2/kWh): = {kg_co2:,.0f} kgCO2/an ({tco2_an} tCO2/an)",
            ]
            stare.impact = impact_data
            return impact_data
        except (ValueError, TypeError) as exc:
            impact_data["pasi"].append(f"Eroare la calcul: {exc}")
            stare.impact = impact_data
            return impact_data

    # -----------------------------------------------------------------------
    # 2. Energie Regenerabilă (Renewable Energy)
    # -----------------------------------------------------------------------
    if cat_norm in ("renewable_energy", "energie_regenerabila"):
        prod_mwh_val = _val("productie_anuala_mwh")
        cap_mw_val = _val("capacitate_mw")

        if prod_mwh_val is not None:
            prod_mwh = float(prod_mwh_val)
        elif cap_mw_val is not None:
            # Estimare din capacitate și factor de capacitate mediu
            cap_mw = float(cap_mw_val)
            subcat = str(_val("subcategorie") or _val("tehnologie") or "").lower()
            fc_est = 0.20 if "solar" in subcat else 0.35
            prod_mwh = cap_mw * 8760.0 * fc_est
        else:
            impact_data["pasi"].append("Lipsă date de capacitate sau producție anuală.")
            stare.impact = impact_data
            return impact_data

        try:
            mwh_banca = prod_mwh * cota_banca
            # Factor emisie tCO2/MWh = kgCO2/kWh
            tco2_an = round(mwh_banca * factor_emisie, 1)

            impact_data["formula"] = "productie_anuala_mwh x cota_banca x factor_emisie_retea_tara (proxy)"
            impact_data["sursa"] = "Allocation & Impact Report 2025, p. 23"
            impact_data["rezultat_tco2_an"] = tco2_an
            impact_data["pasi"] = [
                f"1. Producție anuală regenerabilă: {prod_mwh:,.0f} MWh/an",
                f"2. x cota băncii ({cota_banca:.2f}): = {mwh_banca:,.0f} MWh/an",
                f"3. x intensitate carbon rețea ({factor_emisie} tCO2/MWh): = {tco2_an} tCO2/an evitate",
            ]
            stare.impact = impact_data
            return impact_data
        except (ValueError, TypeError) as exc:
            impact_data["pasi"].append(f"Eroare la calcul: {exc}")
            stare.impact = impact_data
            return impact_data

    # -----------------------------------------------------------------------
    # 3. Transport Curat (Clean Transportation)
    # -----------------------------------------------------------------------
    if cat_norm in ("clean_transportation", "transport"):
        nr_vehicule = float(_val("nr_vehicule", 1.0))
        distanta_km = float(_val("distanta_anuala_km", PROXY_DISTANTA_MEDIE_VEHICUL_KM))
        emisii_wltp = float(_val("emisii_wltp_gco2_km", 0.0))
        consum_kwh_km = float(_val("consum_kwh_km", 0.18))
        pondere_eligibila = float(stare.impact.get("pondere_eligibila", 1.0))

        try:
            # Emisii evitate pe km = diferența față de un vehicul termic convențional
            # factor_emisie este în kgCO2/kWh -> x 1000 = gCO2/kWh
            factor_g_kwh = factor_emisie * 1000.0
            emisii_electrice_g_km = consum_kwh_km * factor_g_kwh
            dif_emisii_g_km = max(0.0, PROXY_EMISIE_MEDIE_TERMIC_G_KM - emisii_electrice_g_km - emisii_wltp)

            g_co2_total = dif_emisii_g_km * distanta_km * nr_vehicule * cota_banca * pondere_eligibila
            tco2_an = round(g_co2_total / 1_000_000.0, 1)

            impact_data["formula"] = (
                "(emisie_termic - consum_electric x factor_emisie - emisii_wltp) x distanta_km x nr_vehicule x cota_banca x pondere_eligibila"
            )
            impact_data["sursa"] = "Allocation & Impact Report 2025, p. 26"
            impact_data["rezultat_tco2_an"] = tco2_an
            impact_data["pasi"] = [
                f"1. Emisii vehicul convențional de referință: {PROXY_EMISIE_MEDIE_TERMIC_G_KM} gCO2/km",
                f"2. Emisii indirecte propulsie electrică: {consum_kwh_km:.2f} kWh/km x {factor_g_kwh:.0f} g/kWh = {emisii_electrice_g_km:.1f} gCO2/km",
                f"3. Emisie directă evacuare: {emisii_wltp} gCO2/km",
                f"4. Diferență netă: {dif_emisii_g_km:.1f} gCO2/km economisite",
                f"5. Total flotă ({nr_vehicule:.0f} vehicule, {distanta_km:,.0f} km/an, cota {cota_banca:.2f}, pondere {pondere_eligibila:.1%}): = {tco2_an} tCO2/an",
            ]
            stare.impact = impact_data
            return impact_data
        except (ValueError, TypeError) as exc:
            impact_data["pasi"].append(f"Eroare la calcul: {exc}")
            stare.impact = impact_data
            return impact_data

    # -----------------------------------------------------------------------
    # 4. Eficiență Energetică (Energy Efficiency)
    # -----------------------------------------------------------------------
    if cat_norm in ("energy_efficiency", "eficienta_energetica"):
        subcat = str(_val("subcategorie") or _val("tip_proiect") or "").lower()

        # Fibră optică
        if "fibra" in subcat:
            nr_gospodarii = float(_val("nr_gospodarii", 1000.0))
            # 100 kWh/an economie per gospodărie x 30% x factor
            kwh_economisiti = 100.0 * 0.30 * nr_gospodarii * cota_banca
            tco2_an = round(kwh_economisiti * factor_emisie / 1000.0, 1)
            impact_data["formula"] = "consum_acces_gospodarie x 0.30 x nr_gospodarii x cota_banca x factor_emisie"
            impact_data["sursa"] = "Allocation & Impact Report 2025, p. 24"
            impact_data["rezultat_tco2_an"] = tco2_an
            impact_data["pasi"] = [
                f"1. Fibră optică (30% economie vs cupru) pentru {nr_gospodarii:,.0f} gospodării",
                f"2. Energie economisită: {kwh_economisiti:,.0f} kWh/an",
                f"3. CO2 evitat: {tco2_an} tCO2/an",
            ]
            stare.impact = impact_data
            return impact_data

        # Contoare inteligente
        if "smart" in subcat or "contor" in subcat:
            nr_contoare = float(_val("nr_contoare", 1000.0))
            # 3% economie gospodărie (3000 kWh x 0.03 = 90 kWh/an)
            kwh_economisiti = 3000.0 * 0.03 * nr_contoare * cota_banca
            tco2_an = round(kwh_economisiti * factor_emisie / 1000.0, 1)
            impact_data["formula"] = "consum_mediu_gospodarie x 0.03 x nr_contoare x cota_banca x factor_emisie"
            impact_data["sursa"] = "Allocation & Impact Report 2025, p. 25"
            impact_data["rezultat_tco2_an"] = tco2_an
            impact_data["pasi"] = [
                f"1. Smart grid / contoare inteligente (3% economie) pentru {nr_contoare:,.0f} contoare",
                f"2. Energie economisită: {kwh_economisiti:,.0f} kWh/an",
                f"3. CO2 evitat: {tco2_an} tCO2/an",
            ]
            stare.impact = impact_data
            return impact_data

        # Eficiență industrială generică
        c_in = _val("consum_inainte_mwh")
        c_dp = _val("consum_dupa_mwh")
        if c_in is not None and c_dp is not None:
            try:
                mwh_eco = (float(c_in) - float(c_dp)) * cota_banca
                tco2_an = round(mwh_eco * factor_emisie, 1)
                impact_data["formula"] = "(consum_inainte - consum_dupa) x cota_banca x factor_emisie"
                impact_data["sursa"] = "Metodologie aliniată RBI (Impact Report p. 22)"
                impact_data["rezultat_tco2_an"] = tco2_an
                impact_data["pasi"] = [
                    f"1. Economie anuală energie: {float(c_in)} - {float(c_dp)} = {float(c_in) - float(c_dp):,.1f} MWh",
                    f"2. x cota băncii ({cota_banca:.2f}): = {mwh_eco:,.1f} MWh/an",
                    f"3. CO2 evitat: {tco2_an} tCO2/an",
                ]
                stare.impact = impact_data
                return impact_data
            except (ValueError, TypeError):
                pass

    # -----------------------------------------------------------------------
    # 5. Prevenirea Poluării & Economie Circulară
    # -----------------------------------------------------------------------
    if cat_norm in ("pollution_prevention", "circular_economy"):
        tone = float(_val("tone_deseuri_reciclate_an") or _val("economie_materie_prima_tone_an") or 0.0)
        if tone > 0:
            # Factor generic 1.5 tCO2 evitate per tonă de material reciclat/economisit
            tco2_an = round(tone * 1.5 * cota_banca, 1)
            impact_data["formula"] = "tone_reciclate x 1.5 tCO2/t x cota_banca"
            impact_data["sursa"] = "Allocation & Impact Report 2025, p. 28"
            impact_data["rezultat_tco2_an"] = tco2_an
            impact_data["pasi"] = [
                f"1. Materiale reciclate / economisite: {tone:,.1f} tone/an",
                f"2. CO2 evitat: {tco2_an} tCO2/an",
            ]
            stare.impact = impact_data
            return impact_data

    # Categorie generică sau fără date
    impact_data["pasi"].append(f"Nu există formulă specifică sau date suficiente de impact pentru categoria '{cat_norm}'.")
    stare.impact = impact_data
    return impact_data
