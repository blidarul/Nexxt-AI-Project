"""Teste unitare pentru conversiile și normalizările de unități din Etapa 3."""

import pytest
from extraction.normalizare import (
    normalizeaza_kwh_per_100km_la_km,
    normalizeaza_wh_per_km,
    normalizeaza_putere_la_mw,
    normalizeaza_energie_la_mwh,
    normalizeaza_emisii_g_per_mi_la_km,
    normalizeaza_pue,
    normalizeaza_da_nu,
    detecteaza_si_normalizeaza_unitate,
)


def test_kwh_100km_la_km():
    assert normalizeaza_kwh_per_100km_la_km("16 kWh/100 km") == 0.16
    assert normalizeaza_kwh_per_100km_la_km("21.0 kWh/100km") == 0.21
    assert normalizeaza_kwh_per_100km_la_km("0.16 kWh/km") == 0.16
    assert normalizeaza_kwh_per_100km_la_km(None) is None


def test_wh_per_km():
    assert normalizeaza_wh_per_km("160 Wh/km") == 0.16
    assert normalizeaza_wh_per_km(None) is None


def test_kw_la_mw():
    assert normalizeaza_putere_la_mw("500 kW") == 0.5
    assert normalizeaza_putere_la_mw("1.5 GW") == 1500.0
    assert normalizeaza_putere_la_mw("2 MW") == 2.0
    assert normalizeaza_putere_la_mw(None) is None


def test_energie_la_mwh():
    assert normalizeaza_energie_la_mwh("500 kWh") == 0.5
    assert normalizeaza_energie_la_mwh("1.5 GWh") == 1500.0
    assert normalizeaza_energie_la_mwh("2 MWh") == 2.0
    assert normalizeaza_energie_la_mwh(None) is None


def test_g_per_mi_la_km():
    result = normalizeaza_emisii_g_per_mi_la_km("80.47 g/mi")
    assert result is not None
    assert abs(result - 50.01) < 0.1
    assert normalizeaza_emisii_g_per_mi_la_km(None) is None


def test_pue():
    assert normalizeaza_pue("1,38") == 1.38
    assert normalizeaza_pue("1.5") == 1.5
    assert normalizeaza_pue("0.9") is None  # PUE < 1.0 invalid
    assert normalizeaza_pue(None) is None


def test_da_nu():
    assert normalizeaza_da_nu("da") is True
    assert normalizeaza_da_nu("true") is True
    assert normalizeaza_da_nu("yes") is True
    assert normalizeaza_da_nu("nu") is False
    assert normalizeaza_da_nu("false") is False
    assert normalizeaza_da_nu("no") is False
    assert normalizeaza_da_nu(None) is None


def test_detecteaza_si_normalizeaza_unitate():
    val, u = detecteaza_si_normalizeaza_unitate("consum_kwh_km", "16 kWh/100 km")
    assert val == 0.16
    assert u == "kWh/100km"

    val, u = detecteaza_si_normalizeaza_unitate("capacitate_mw", "500 kW")
    assert val == 0.5
    assert u == "kW"

    val, u = detecteaza_si_normalizeaza_unitate("pue_anualizat", "1,38")
    assert val == 1.38
    assert u == "PUE"

    val, u = detecteaza_si_normalizeaza_unitate("pondere_aluminiu_reciclat", "80%")
    assert val == 0.8
    assert u == "%"

    val, u = detecteaza_si_normalizeaza_unitate("transporta_combustibili_fosili", "nu")
    assert val is False
    assert u == "da_nu"
