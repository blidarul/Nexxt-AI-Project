"""Modul pentru normalizarea deterministă a valorilor extrase din documente.

Nu folosește LLM. Curăță și transformă numere, procente, date, coduri CAEN,
clase energetice și CUI în formatele standardizate cerute de sistem.
"""

from datetime import datetime
import re
from typing import Any, Optional


LUNI = {
    # Română
    "ianuarie": 1, "ian": 1,
    "februarie": 2, "feb": 2,
    "martie": 3, "mar": 3,
    "aprilie": 4, "apr": 4,
    "mai": 5,
    "iunie": 6, "iun": 6,
    "iulie": 7, "iul": 7,
    "august": 8, "aug": 8,
    "septembrie": 9, "sep": 9, "sept": 9,
    "octombrie": 10, "oct": 10,
    "noiembrie": 11, "nov": 11,
    "decembrie": 12, "dec": 12,
    # Engleză
    "january": 1, "jan": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def normalizeaza_numar(valoare: Any) -> Optional[int | float]:
    """Convertește o valoare numerică în format întreg sau zecimal.

    Exemple:
        - "30.000.000 EUR" -> 30000000
        - "30.000.000,00 EUR" -> 30000000
        - "1.234,5" -> 1234.5
        - "1,234.5" -> 1234.5
        - "20.000 m²" -> 20000
        - "12 mil. EUR" -> 12000000
        - "10.5 mil." -> 10500000
        - "12 milioane EUR" -> 12000000
        - "12 million" -> 12000000
        - "16 kWh/100 km" -> 16
        - "120 gCO2/km" -> 120
        - "2,1 tCO2e/t" -> 2.1
        - "PUE: 1,38" -> 1.38
        - "CO2 emissions: 45 g/km" -> 45
    """
    if valoare is None:
        return None
    if isinstance(valoare, (int, float)):
        return valoare

    text = str(valoare).strip()
    if not text:
        return None

    # Detectează multiplicatori (mil., milioane, million, mld, k etc.)
    multiplicator = 1.0
    text_lower = text.lower()

    mld_pattern = r"(?:\bmld\.|\bmiliarde\b|\bmiliard\b|\bbillion\b|\bbln\b)"
    mil_pattern = r"(?:\bmil\.|\bmilioane\b|\bmilion\b|\bmillion\b|\bmil\b)"
    mii_pattern = r"(?:\bmii\b|\bthousand\b)"

    text_fara_mult = text
    if re.search(mld_pattern, text_lower):
        multiplicator = 1_000_000_000.0
        text_fara_mult = re.sub(mld_pattern, "", text_fara_mult, flags=re.IGNORECASE)
    elif re.search(mil_pattern, text_lower):
        multiplicator = 1_000_000.0
        text_fara_mult = re.sub(mil_pattern, "", text_fara_mult, flags=re.IGNORECASE)
    elif re.search(mii_pattern, text_lower):
        multiplicator = 1_000.0
        text_fara_mult = re.sub(mii_pattern, "", text_fara_mult, flags=re.IGNORECASE)

    # Curățăm formule chimice și unități cu indici/puteri numerice (CO2, tCO2e, NOx, SO2, m2, m3 etc.)
    # precum și prefixe/unități (n50, h⁻¹, etc.)
    t_fara_n50 = re.sub(r"\bn[_-]?50\s*[:=]?\s*", "", text_fara_mult, flags=re.IGNORECASE)
    text_curat = re.sub(
        r"\b[a-z]*co2[a-z0-9]*\b|\b[a-z]*nox[a-z0-9]*\b|\b[a-z]*so2[a-z0-9]*\b|\bm[23]\b|m²|m³|h[\u207b\-]?[1\u00b9]|\b1/h\b",
        "",
        t_fara_n50,
        flags=re.IGNORECASE,
    )

    # Extragem primul număr din text cu regex (suportă separatori de mii și zecimale RO/EN)
    m = re.search(r"[-+]?\d+(?:[.,]\d+)*", text_curat)
    if not m:
        return None

    num_str = m.group(0).strip()
    punct_count = num_str.count(".")
    virgula_count = num_str.count(",")

    if punct_count > 0 and virgula_count > 0:
        # Format mixt: ultimul separator este separatorul zecimal
        ultimul_punct = num_str.rfind(".")
        ultima_virgula = num_str.rfind(",")
        if ultima_virgula > ultimul_punct:
            # Format european: 1.234,5 sau 30.000.000,00 -> 1234.5 / 30000000.00
            num_str = num_str.replace(".", "").replace(",", ".")
        else:
            # Format anglo-saxon: 1,234.5 sau 30,000,000.00 -> 1234.5 / 30000000.00
            num_str = num_str.replace(",", "")
    elif punct_count > 1:
        # Puncte multiple ca separatori de mii: 30.000.000 -> 30000000
        num_str = num_str.replace(".", "")
    elif virgula_count > 1:
        # Virgule multiple ca separatori de mii: 30,000,000 -> 30000000
        num_str = num_str.replace(",", "")
    elif punct_count == 1:
        # Un singur punct: ex: 20.000 vs 1234.5 vs 10.5
        parti = num_str.split(".")
        parte_intreaga, parte_zecimala = parti[0], parti[1]
        # Dacă după punct sunt exact 3 cifre și partea întreagă nu e 0:
        # În context de EUR, m² etc., 20.000 este 20000 (separator de mii),
        # cu excepția cazului când există multiplicator (ex: 10.5 mil)
        if len(parte_zecimala) == 3 and parte_intreaga != "0" and multiplicator == 1.0:
            num_str = num_str.replace(".", "")
        else:
            # Rămâne separator zecimal
            pass
    elif virgula_count == 1:
        # O singură virgulă:
        parti = num_str.split(",")
        parte_intreaga, parte_zecimala = parti[0], parti[1]
        if len(parte_zecimala) == 3 and parte_intreaga != "0" and multiplicator == 1.0:
            # 20,000 ca separator de mii
            num_str = num_str.replace(",", "")
        else:
            # Virgulă zecimală: 0,6 -> 0.6 sau 1234,5 -> 1234.5
            num_str = num_str.replace(",", ".")

    try:
        val = float(num_str) * multiplicator
        # Dacă numărul este întreg (fără fracție), întoarce int
        if val.is_integer():
            return int(val)
        return round(val, 4)
    except ValueError:
        return None

def normalizeaza_procent(valoare: Any) -> Optional[float]:
    """Convertește o valoare procentuală la un număr între 0.0 și 1.0.

    Exemple:
        - "60%" -> 0.6
        - "0,6" -> 0.6
        - "0.6" -> 0.6
        - "60" -> 0.6
        - "100%" -> 1.0
        - "1" -> 1.0
    """
    if valoare is None:
        return None
    if isinstance(valoare, (int, float)):
        num = float(valoare)
        if num > 1.0:
            return round(num / 100.0, 4)
        return round(num, 4)

    text = str(valoare).strip()
    if not text:
        return None

    are_simbol_procent = "%" in text
    num = normalizeaza_numar(text)
    if num is None:
        return None

    val = float(num)
    if are_simbol_procent or val > 1.0:
        val = val / 100.0

    return round(val, 4)


def normalizeaza_data(valoare: Any) -> Optional[str]:
    """Convertește o dată în format ISO (YYYY-MM-DD).

    Exemple:
        - "15.03.2026" -> "2026-03-15"
        - "15/03/2026" -> "2026-03-15"
        - "2026-03-15" -> "2026-03-15"
        - "15 martie 2026" -> "2026-03-15"
        - "15 March 2026" -> "2026-03-15"
    """
    if valoare is None:
        return None

    text = str(valoare).strip()
    if not text:
        return None

    # Dacă este deja în format ISO YYYY-MM-DD
    m_iso = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if m_iso:
        an, luna, zi = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            return datetime(an, luna, zi).strftime("%Y-%m-%d")
        except ValueError:
            return None

    # Format numeric DD.MM.YYYY sau DD/MM/YYYY
    m_num = re.search(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b", text)
    if m_num:
        zi, luna, an = int(m_num.group(1)), int(m_num.group(2)), int(m_num.group(3))
        try:
            return datetime(an, luna, zi).strftime("%Y-%m-%d")
        except ValueError:
            return None

    # Format textual: "15 martie 2026" sau "15 March 2026"
    m_text = re.search(r"\b(\d{1,2})\s+([a-zA-ZăîâșțĂÎÂȘȚ]+)\s+(\d{4})\b", text)
    if m_text:
        zi = int(m_text.group(1))
        nume_luna = m_text.group(2).lower()
        an = int(m_text.group(3))
        luna = LUNI.get(nume_luna)
        if luna:
            try:
                return datetime(an, luna, zi).strftime("%Y-%m-%d")
            except ValueError:
                return None

    return None


def normalizeaza_caen(valoare: Any) -> Optional[str]:
    """Păstrează primele 4 cifre ale codului CAEN.

    Exemple:
        - "0610 – Extracția petrolului" -> "0610"
        - "6201" -> "6201"
        - "CAEN 7022" -> "7022"
    """
    if valoare is None:
        return None

    text = str(valoare).strip()
    m = re.search(r"\b(\d{4})\b", text)
    if m:
        return m.group(1)

    # Dacă sunt 4 cifre oriunde în text
    m_any = re.search(r"(\d{4})", text)
    if m_any:
        return m_any.group(1)

    return None


def normalizeaza_clasa_energetica(valoare: Any) -> Optional[str]:
    """Extrage clasa energetică standard (ex: A, A+, B, C).

    Exemple:
        - "A" -> "A"
        - "A+" -> "A+"
        - "clasa A" -> "A"
        - "Clasa B" -> "B"
    """
    if valoare is None:
        return None

    text = str(valoare).strip()
    m = re.search(r"(?<![a-zA-Z0-9])([A-G]\+?)(?![a-zA-Z0-9])", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()

    return None


def normalizeaza_cui(valoare: Any) -> Optional[str]:
    """Curăță CUI-ul/CIF-ul, eliminând prefixul RO și caracterele non-cifre.

    Exemple:
        - "RO9900000010" -> "9900000010"
        - "RO 9900000010" -> "9900000010"
        - "9900000010" -> "9900000010"
    """
    if valoare is None:
        return None

    text = str(valoare).strip()
    # Elimină RO / ro de la început
    text = re.sub(r"^(RO|ro)\s*", "", text, flags=re.IGNORECASE)
    # Păstrează doar cifrele
    cifre = re.sub(r"[^\d]", "", text)
    if 2 <= len(cifre) <= 12:
        return cifre

    return None


def valideaza_valoare(valoare: Any, reguli: Optional[dict[str, Any]]) -> tuple[bool, Optional[str]]:
    """Verifică dacă o valoare normalizată respectă regulile de validare din catalog.

    Întoarce (este_valid, motiv_invalidare).
    """
    if valoare is None or reguli is None:
        return True, None

    if "min" in reguli and isinstance(valoare, (int, float)):
        if valoare < reguli["min"]:
            return False, f"Valoarea {valoare} este sub pragul minim admis ({reguli['min']})"

    if "max" in reguli and isinstance(valoare, (int, float)):
        if valoare > reguli["max"]:
            return False, f"Valoarea {valoare} depășește pragul maxim admis ({reguli['max']})"

    if "regex" in reguli and isinstance(valoare, str):
        if not re.match(reguli["regex"], valoare):
            return False, f"Valoarea '{valoare}' nu corespunde tiparului cerut ({reguli['regex']})"

    return True, None


def normalizeaza_camp(
    camp_nume: str,
    valoare_bruta: Any,
    tip_camp: Optional[str] = None,
    reguli_validare: Optional[dict[str, Any]] = None,
) -> tuple[Any, Optional[str]]:
    """Funcție unificată de normalizare și validare pentru un câmp specificat.

    Întoarce:
        (valoare_normalizata, motiv_eroare_sau_respingere)
    """
    if valoare_bruta is None:
        return None, None

    # CUI-ul are normalizare proprie (prefixul de TVA „RO”), chiar dacă în catalog e de tip text
    if camp_nume == "cui":
        tip_camp = "cui"

    # Dacă tipul nu este specificat explicit, deducem după numele câmpului
    if tip_camp is None:
        if camp_nume in ("cui",):
            tip_camp = "cui"
        elif camp_nume in ("suma_eur", "suprafata_m2", "epc_energie_finala", "epc_suprafata_m2"):
            tip_camp = "numar"
        elif camp_nume in ("cota_banca",):
            tip_camp = "procent"
        elif camp_nume in ("data_aprobare",):
            tip_camp = "data"
        elif camp_nume in ("epc_clasa",):
            tip_camp = "clasa_energetica"
        elif camp_nume in ("caen",):
            tip_camp = "cod_caen"
        else:
            tip_camp = "text"

    val_norm = None

    if tip_camp == "numar":
        val_norm = normalizeaza_numar(valoare_bruta)
    elif tip_camp == "procent":
        val_norm = normalizeaza_procent(valoare_bruta)
    elif tip_camp == "data":
        val_norm = normalizeaza_data(valoare_bruta)
    elif tip_camp == "cod_caen":
        val_norm = normalizeaza_caen(valoare_bruta)
    elif tip_camp == "clasa_energetica":
        val_norm = normalizeaza_clasa_energetica(valoare_bruta)
    elif tip_camp in ("cui",):
        val_norm = normalizeaza_cui(valoare_bruta)
    else:
        # text brut curățat
        val_norm = str(valoare_bruta).strip()

    if val_norm is None:
        return None, f"Nu s-a putut normaliza valoarea brută: '{valoare_bruta}' pentru tipul '{tip_camp}'"

    # Validare
    valid, motiv = valideaza_valoare(val_norm, reguli_validare)
    if not valid:
        return None, motiv

    return val_norm, None


# ---------------------------------------------------------------------------
# Conversii și normalizări specifice de unități de măsură (Etapa 3)
# ---------------------------------------------------------------------------

def normalizeaza_kwh_per_100km_la_km(valoare: Any) -> Optional[float]:
    """Convertește consumul din kWh/100 km în kWh/km (împărțire la 100).

    Exemple:
        - "16 kWh/100 km" -> 0.16
        - "21.0 kWh/100km" -> 0.21
        - "0.16 kWh/km" -> 0.16
    """
    if valoare is None:
        return None

    text = str(valoare).strip()
    num = normalizeaza_numar(text)
    if num is None:
        return None

    val = float(num)
    # Dacă în text apare '100' sau '100km' / '100 km', se împarte la 100
    if re.search(r"\b100\s*km\b|100km", text, re.IGNORECASE) or val >= 5.0:
        val = val / 100.0

    return round(val, 4)


def normalizeaza_wh_per_km(valoare: Any) -> Optional[float]:
    """Convertește consumul din Wh/km în kWh/km (împărțire la 1000).

    Exemple:
        - "160 Wh/km" -> 0.16
    """
    if valoare is None:
        return None

    num = normalizeaza_numar(valoare)
    if num is None:
        return None

    val = float(num) / 1000.0
    return round(val, 4)


def normalizeaza_putere_la_mw(valoare: Any, unitate: str = "") -> Optional[float]:
    """Convertește puterea la MW (kW -> MW prin /1000, GW -> MW prin *1000).

    Exemple:
        - "500 kW" -> 0.5
        - "1.5 GW" -> 1500.0
        - "2 MW" -> 2.0
    """
    if valoare is None:
        return None

    text = str(valoare).strip()
    u = unitate.lower() if unitate else ""
    if not u:
        if re.search(r"\bkw\b", text, re.IGNORECASE):
            u = "kw"
        elif re.search(r"\bgw\b", text, re.IGNORECASE):
            u = "gw"
        elif re.search(r"\bmw\b", text, re.IGNORECASE):
            u = "mw"

    num = normalizeaza_numar(text)
    if num is None:
        return None

    val = float(num)
    if u == "kw":
        val = val / 1000.0
    elif u == "gw":
        val = val * 1000.0

    return round(val, 4)


def normalizeaza_energie_la_mwh(valoare: Any, unitate: str = "") -> Optional[float]:
    """Convertește energia la MWh (kWh -> MWh prin /1000, GWh -> MWh prin *1000).

    Exemple:
        - "500 kWh" -> 0.5
        - "1.5 GWh" -> 1500.0
        - "2 MWh" -> 2.0
    """
    if valoare is None:
        return None

    text = str(valoare).strip()
    u = unitate.lower() if unitate else ""
    if not u:
        if re.search(r"\bkwh\b", text, re.IGNORECASE):
            u = "kwh"
        elif re.search(r"\bgwh\b", text, re.IGNORECASE):
            u = "gwh"
        elif re.search(r"\bmwh\b", text, re.IGNORECASE):
            u = "mwh"

    num = normalizeaza_numar(text)
    if num is None:
        return None

    val = float(num)
    if u == "kwh":
        val = val / 1000.0
    elif u == "gwh":
        val = val * 1000.0

    return round(val, 4)


def normalizeaza_emisii_g_per_mi_la_km(valoare: Any) -> Optional[float]:
    """Convertește emisiile din g/mi în g/km (împărțire la 1.609).

    Exemple:
        - "80.47 g/mi" -> ~50.01
    """
    if valoare is None:
        return None

    num = normalizeaza_numar(valoare)
    if num is None:
        return None

    val = float(num) / 1.609
    return round(val, 2)


def normalizeaza_pue(valoare: Any) -> Optional[float]:
    """Normalizează valoarea PUE (Power Usage Effectiveness).

    Exemple:
        - "1,38" -> 1.38
        - "1.5" -> 1.5
        - "0.9" -> None (invalid, PUE >= 1.0)
    """
    if valoare is None:
        return None

    num = normalizeaza_numar(valoare)
    if num is None:
        return None

    val = float(num)
    if val < 1.0:
        return None

    return round(val, 4)


def normalizeaza_da_nu(valoare: Any) -> Optional[bool]:
    """Normalizează o valoare booleană / da-nu din text.

    Exemple:
        - "da", "true", "yes" -> True
        - "nu", "false", "no" -> False
    """
    if valoare is None:
        return None
    if isinstance(valoare, bool):
        return valoare

    text = str(valoare).strip().lower()
    if text in ("da", "true", "yes", "1", "afirmativ", "conform"):
        return True
    elif text in ("nu", "false", "no", "0", "negativ", "neconform"):
        return False

    return None


def detecteaza_si_normalizeaza_unitate(
    camp: str,
    valoare_text: str,
) -> tuple[Any, Optional[str]]:
    """Detectează unitatea din valoare_text și aplică conversia corespunzătoare conform cerințelor.

    Întoarce:
        (valoare_normalizata, unitate_originala_detectata)
    """
    if valoare_text is None:
        return None, None

    text = str(valoare_text).strip()
    text_lower = text.lower()

    # 1. PUE
    if "pue" in camp:
        val = normalizeaza_pue(text)
        return val, "PUE"

    # 2. Consum electric vehicule (kWh/km)
    if "consum_kwh_km" in camp or ("kwh" in text_lower and "km" in text_lower):
        if re.search(r"\b100\s*km\b|100km", text_lower):
            val = normalizeaza_kwh_per_100km_la_km(text)
            return val, "kWh/100km"
        elif "wh" in text_lower and "kwh" not in text_lower:
            val = normalizeaza_wh_per_km(text)
            return val, "Wh/km"
        else:
            val = normalizeaza_numar(text)
            return val, "kWh/km"

    # 3. Putere (kW, MW, GW -> MW)
    if "capacitate_mw" in camp or "putere" in camp:
        if re.search(r"\bkw\b", text_lower):
            val = normalizeaza_putere_la_mw(text, "kw")
            return val, "kW"
        elif re.search(r"\bgw\b", text_lower):
            val = normalizeaza_putere_la_mw(text, "gw")
            return val, "GW"
        elif re.search(r"\bmw\b", text_lower):
            val = normalizeaza_putere_la_mw(text, "mw")
            return val, "MW"

    # 4. Energie (kWh, MWh, GWh -> MWh)
    if any(k in camp for k in ("productie_anuala_mwh", "consum_inainte_mwh", "consum_dupa_mwh", "energie_generata_mwh_an", "economie_energie_mwh_an")):
        if re.search(r"\bkwh\b", text_lower):
            val = normalizeaza_energie_la_mwh(text, "kwh")
            return val, "kWh"
        elif re.search(r"\bgwh\b", text_lower):
            val = normalizeaza_energie_la_mwh(text, "gwh")
            return val, "GWh"
        elif re.search(r"\bmwh\b", text_lower):
            val = normalizeaza_energie_la_mwh(text, "mwh")
            return val, "MWh"

    # 5. Emisii per pasager-milă sau tonă-milă -> km
    if "pkm" in camp or "tkm" in camp or "g/mi" in text_lower or "gco2/mi" in text_lower:
        if re.search(r"\bmi\b|mila|mile", text_lower):
            val = normalizeaza_emisii_g_per_mi_la_km(text)
            return val, "g/mi"
        else:
            val = normalizeaza_numar(text)
            return val, "g/km"

    # 6. Procente (campuri *_pct sau pondere_*)
    if camp.endswith("_pct") or camp.startswith("pondere_") or "cota_" in camp:
        val = normalizeaza_procent(text)
        return val, "%"

    # 7. Valori de tip da_nu
    if camp in ("aprobat_proces_standard", "fir_de_apa_fara_rezervor", "eia_risc_semnificativ",
                 "tehnologie_bat", "echipament_combustibil_fosil", "transporta_combustibili_fosili",
                 "reciclare_chimica_plastic", "segregare_la_sursa", "foloseste_plastic_virgin",
                 "statie_in_cladire", "integrat_cu_regenerabile", "deserveste_sistem_fosil",
                 "sistem_management_agent_frigorific", "alimentat_regenerabil",
                 "conform_renovare_majora", "conexiune_dedicata_centrala_fosila",
                 "dedicat_conectarii_regenerabile", "dedicat_zero_emisii"):
        val = normalizeaza_da_nu(text)
        return val, "da_nu"

    # Implicit număr dacă e cazul
    num = normalizeaza_numar(text)
    if num is not None:
        return num, None

    return text, None

