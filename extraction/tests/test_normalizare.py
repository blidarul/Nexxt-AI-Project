"""Teste unitare pentru funcțiile de normalizare deterministă."""

import pytest
from extraction.normalizare import (
    normalizeaza_numar,
    normalizeaza_procent,
    normalizeaza_data,
    normalizeaza_caen,
    normalizeaza_clasa_energetica,
    normalizeaza_cui,
    normalizeaza_camp,
    valideaza_valoare,
)


def test_normalizeaza_numar():
    assert normalizeaza_numar("30.000.000 EUR") == 30000000
    assert normalizeaza_numar("1.234,5") == 1234.5
    assert normalizeaza_numar("1,234.5") == 1234.5
    assert normalizeaza_numar("20.000 m²") == 20000
    assert normalizeaza_numar("12 mil. EUR") == 12000000
    assert normalizeaza_numar("10.5 mil.") == 10500000
    assert normalizeaza_numar("12 milioane EUR") == 12000000
    assert normalizeaza_numar("12 million") == 12000000
    assert normalizeaza_numar(None) is None
    assert normalizeaza_numar("") is None


def test_normalizeaza_procent():
    assert normalizeaza_procent("60%") == 0.6
    assert normalizeaza_procent("0,6") == 0.6
    assert normalizeaza_procent("0.6") == 0.6
    assert normalizeaza_procent("60") == 0.6
    assert normalizeaza_procent("100%") == 1.0
    assert normalizeaza_procent("1") == 1.0
    assert normalizeaza_procent("35%") == 0.35
    assert normalizeaza_procent(None) is None


def test_normalizeaza_data():
    assert normalizeaza_data("15.03.2026") == "2026-03-15"
    assert normalizeaza_data("15/03/2026") == "2026-03-15"
    assert normalizeaza_data("2026-03-15") == "2026-03-15"
    assert normalizeaza_data("15 martie 2026") == "2026-03-15"
    assert normalizeaza_data("15 March 2026") == "2026-03-15"
    assert normalizeaza_data("1 ianuarie 2025") == "2025-01-01"
    assert normalizeaza_data(None) is None
    assert normalizeaza_data("data invalida") is None


def test_normalizeaza_caen():
    assert normalizeaza_caen("0610 – Extracția petrolului") == "0610"
    assert normalizeaza_caen("6201 – Activități de software") == "6201"
    assert normalizeaza_caen("7022") == "7022"
    assert normalizeaza_caen("CAEN 5630") == "5630"
    assert normalizeaza_caen(None) is None


def test_normalizeaza_clasa_energetica():
    assert normalizeaza_clasa_energetica("A") == "A"
    assert normalizeaza_clasa_energetica("A+") == "A+"
    assert normalizeaza_clasa_energetica("clasa A") == "A"
    assert normalizeaza_clasa_energetica("Clasa B") == "B"
    assert normalizeaza_clasa_energetica("clasa C") == "C"
    assert normalizeaza_clasa_energetica(None) is None


def test_normalizeaza_cui():
    assert normalizeaza_cui("RO9900000010") == "9900000010"
    assert normalizeaza_cui("RO 9900000010") == "9900000010"
    assert normalizeaza_cui("9900000010") == "9900000010"
    assert normalizeaza_cui("ro 123456") == "123456"
    assert normalizeaza_cui(None) is None


def test_valideaza_valoare():
    valid, motiv = valideaza_valoare(20000, {"min": 10, "max": 2000000})
    assert valid is True
    assert motiv is None

    valid, motiv = valideaza_valoare(5, {"min": 10, "max": 2000000})
    assert valid is False
    assert "sub pragul minim" in motiv

    valid, motiv = valideaza_valoare(3000000, {"min": 10, "max": 2000000})
    assert valid is False
    assert "depășește pragul maxim" in motiv

    valid, motiv = valideaza_valoare("9900000010", {"regex": "^[0-9]{2,10}$"})
    assert valid is True


def test_normalizeaza_camp_unificat():
    val, motiv = normalizeaza_camp("suma_eur", "30.000.000 EUR", tip_camp="numar", reguli_validare={"min": 1000})
    assert val == 30000000
    assert motiv is None

    val, motiv = normalizeaza_camp("cota_banca", "60%", tip_camp="procent")
    assert val == 0.6
    assert motiv is None

    val, motiv = normalizeaza_camp("cui", "RO 9900000010", tip_camp="cui")
    assert val == "9900000010"
    assert motiv is None
