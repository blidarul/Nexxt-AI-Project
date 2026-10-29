"""Starea fiecărui pas din „Pașii agentului”, calculată doar din câmpurile structurate ale trace-ului
(gasit, eroare, verificat_in_registru, eroare_tehnica) și din verdict, niciodată din textul rezumatului.

Pentru un pas de verificare într-un registru:
  Verificat                                — gasit=True, fără eroare, confirmat de registru
  Găsit în dosar, neverificat în registru  — registrul nu a confirmat, dar valoarea e în documentele dosarului
  Negăsit                                  — nici în registru, nici în documente
  Eroare la verificare                     — eroare tehnică (rețea, argumente, nicio sursă disponibilă)
Pentru un pas de evaluare a regulilor: rezultatele regulilor evaluate, cu aceleași etichete ca în raport.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from engine.verdict import GENERALA, PLAUZIBILITATE, rol_regula

# Pasul de verificare -> (câmpul din documentele dosarului pe care îl verifică, cheia din fiecare element al listei)
CAMP_PENTRU_PAS: dict[str, tuple[str, Optional[str]]] = {
    "verifica_firma": ("cui", None),
    "cauta_certificat": ("nr_certificat_declarat", None),
    "cauta_emisii_vehicul": ("vehicule", "emisii_wltp_gco2_km"),
}

STARI: dict[str, tuple[str, str]] = {
    "verificat": ("Verificat", "pos"),
    "in_dosar": ("Găsit în dosar, neverificat în registru", "warn"),
    "negasit": ("Negăsit", "neg"),
    "eroare": ("Eroare la verificare", "eroare"),
    "efectuat": ("Efectuat", "neutru"),
}

ETICHETA_REZULTAT = {
    "OK": "OK", "NU": "NU", "NEEVALUABIL": "Neevaluabil", "SEMNAL": "Semnal", "OK_CONDITIONAT": "OK condiționat",
}

# Pasul de evaluare -> regulile din verdict pe care le-a evaluat
_REGULI_PENTRU_PAS: dict[str, Callable[[dict[str, Any], list[str]], list[str]]] = {
    "evalueaza_conditii_generale": lambda arg, ids: [i for i in ids if rol_regula(i) == GENERALA],
    "verifica_plauzibilitate": lambda arg, ids: [i for i in ids if rol_regula(i) == PLAUZIBILITATE],
    "evalueaza_cale": lambda arg, ids: [i for i in ids if i == str(arg.get("cale_id") or "").strip()],
    "verifica_chiriasi": lambda arg, ids: [i for i in ids if i == "GB-X1"],
    "evalueaza_categoria": lambda arg, ids: [i for i in ids if rol_regula(i) not in (GENERALA, PLAUZIBILITATE)],
}


def _gol(valoare: Any) -> bool:
    return valoare is None or valoare == "" or valoare == [] or valoare == {}


def camp_din_dosar(pas: str, campuri: dict[str, dict[str, Any]]) -> Optional[tuple[str, dict[str, Any]]]:
    """(numele câmpului, câmpul) când valoarea verificată de pas există în documentele dosarului."""
    if pas not in CAMP_PENTRU_PAS:
        return None
    nume, cheie_element = CAMP_PENTRU_PAS[pas]
    camp = campuri.get(nume)
    if not isinstance(camp, dict) or _gol(camp.get("valoare")):
        return None
    if cheie_element is not None:
        elemente = camp["valoare"] if isinstance(camp["valoare"], list) else []
        if not any(isinstance(e, dict) and not _gol(e.get(cheie_element)) for e in elemente):
            return None
    return nume, camp


def stare_pas(
    intrare: dict[str, Any],
    reguli: dict[str, str],
    campuri: dict[str, dict[str, Any]],
    camp_public: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Starea unui pas din trace. reguli: {id: rezultat} din verdict; campuri: valorile din documentele dosarului."""
    rez = intrare.get("rezultat")
    if not isinstance(rez, dict):
        return None  # pasul final („Concluzie”) sau escaladarea automată
    actiune = intrare.get("actiune") or ""

    if rez.get("eroare") and (rez.get("eroare_tehnica") or actiune not in CAMP_PENTRU_PAS):
        return _stare("eroare", detaliu=rez["eroare"])

    if actiune in _REGULI_PENTRU_PAS:
        ids = _REGULI_PENTRU_PAS[actiune](intrare.get("argumente") or {}, list(reguli))
        return {**_stare("efectuat"), "reguli": [
            {"id": i, "rezultat": reguli[i], "eticheta": ETICHETA_REZULTAT.get(reguli[i], reguli[i])} for i in ids
        ]}

    if actiune not in CAMP_PENTRU_PAS:
        return _stare("efectuat")

    if rez.get("gasit") and not rez.get("eroare") and rez.get("verificat_in_registru") is not False:
        return _stare("verificat")
    gasit_in_dosar = camp_din_dosar(actiune, campuri)
    if gasit_in_dosar:
        nume, camp = gasit_in_dosar
        return {**_stare("in_dosar", detaliu=rez.get("eroare")), "sursa": camp_public(nume, camp)}
    return _stare("negasit", detaliu=rez.get("eroare"))


def _stare(cheie: str, detaliu: Optional[str] = None) -> dict[str, Any]:
    eticheta, clasa = STARI[cheie]
    return {"cheie": cheie, "eticheta": eticheta, "clasa": clasa, "detaliu": detaliu}
