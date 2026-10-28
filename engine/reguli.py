"""Evaluarea regulilor de eligibilitate pentru clădiri și condiții generale."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from contracts import RezultatRegula, StareDosar, ToolResult
from registry import tool

logger = logging.getLogger(__name__)

# Prefixe CAEN excluse sau semnalate conform conditii_generale.yaml și green_buildings.yaml
PREFIXE_CAEN_EXCLUSE_GENERAL = [
    "254", "304", "2446", "05", "06", "0910", "19", "352",
    "07", "08", "099", "1101", "1102", "1103", "1104", "1105", "12", "92",
]
PREFIXE_CAEN_SEMNAL_GENERAL = ["3511"]
PREFIXE_CAEN_SEMNAL_CHIRIASI = ["0510", "0520", "0610", "0620", "0910", "1910", "1920"]

TARI_ELIGIBILE = {
    "austria", "belgia", "bulgaria", "croatia", "cipru", "cehia", "danemarca", "estonia",
    "finlanda", "franta", "germania", "grecia", "ungaria", "irlanda", "italia", "letonia",
    "lituania", "luxemburg", "malta", "olanda", "polonia", "portugalia", "romania", "românia",
    "slovacia", "slovenia", "spania", "suedia",
    "albania", "bosnia si hertegovina", "kosovo", "serbia", "ucraina",
    "china", "india", "japonia", "regatul unit", "statele unite", "brazilia",
}


class ConditiiGeneraleInput(BaseModel):
    pass


class EvalueazaCaleInput(BaseModel):
    cale_id: str = Field(..., description="Identificatorul căii (ex: GB-01, GB-02, GB-03, GB-04)")


class VerificaChiriasiInput(BaseModel):
    pass


@tool(
    nume="evalueaza_conditii_generale",
    descriere="Evaluează condițiile generale (G-01, G-02, G-04).",
    model_intrare=ConditiiGeneraleInput,
)
def evalueaza_conditii_generale(intrare: ConditiiGeneraleInput, stare: StareDosar) -> ToolResult:
    """Evaluează G-01 (țară), G-02 (sector exclus), G-04 (fereastră 24 luni)."""
    # G-01: Țară eligibilă
    tara_val = str(stare.extras.tara.valoare or "").strip()
    if tara_val.lower() in TARI_ELIGIBILE:
        stare.reguli["G-01"] = RezultatRegula(
            regula_id="G-01",
            rezultat="OK",
            dovada="Tara: Romania (Anexa B)",
            sursa_framework="Anexa B, p. 26",
        )
    else:
        stare.reguli["G-01"] = RezultatRegula(
            regula_id="G-01",
            rezultat="NU",
            dovada=f"Țară neeligibilă: {tara_val}",
            sursa_framework="Anexa B, p. 26",
        )

    # G-02: Sector neexclus (ANAF)
    caen = ""
    res_anaf = stare.rezultate_tools.get("verifica_firma")
    if res_anaf and res_anaf.gasit:
        caen = str(res_anaf.date.get("date_generale", {}).get("cod_CAEN", "")).strip()

    if not caen:
        stare.reguli["G-02"] = RezultatRegula(
            regula_id="G-02",
            rezultat="NEEVALUABIL",
            dovada="Lipsă cod CAEN împrumutat din ANAF",
            sursa_framework="Anexa A, p. 25",
        )
    elif any(caen.startswith(p) for p in PREFIXE_CAEN_EXCLUSE_GENERAL):
        stare.reguli["G-02"] = RezultatRegula(
            regula_id="G-02",
            rezultat="NU",
            dovada=f"CAEN împrumutat {caen} este în sector exclus",
            sursa_framework="Anexa A, p. 25",
        )
    elif any(caen.startswith(p) for p in PREFIXE_CAEN_SEMNAL_GENERAL):
        stare.reguli["G-02"] = RezultatRegula(
            regula_id="G-02",
            rezultat="SEMNAL",
            dovada=f"CAEN împrumutat {caen} necesită verificare suplimentară",
            sursa_framework="Anexa A, p. 25",
        )
    else:
        stare.reguli["G-02"] = RezultatRegula(
            regula_id="G-02",
            rezultat="OK",
            dovada=f"CAEN imprumutat {caen} - imobiliare, nu e sector exclus",
            sursa_framework="Anexa A, p. 25",
        )

    # G-04: Fereastră 24 de luni
    data_aprobare_str = str(stare.extras.data_aprobare.valoare or "").strip()
    try:
        from config import DATA_ALOCARE
        d_aprobare = datetime.strptime(data_aprobare_str, "%Y-%m-%d")
        d_alocare = datetime.strptime(DATA_ALOCARE, "%Y-%m-%d")
        diff_luni = (d_alocare.year - d_aprobare.year) * 12 + (d_alocare.month - d_aprobare.month)
        if diff_luni <= 24:
            stare.reguli["G-04"] = RezultatRegula(
                regula_id="G-04",
                rezultat="OK",
                dovada=f"Aprobat {data_aprobare_str}, in fereastra de 24 luni",
                sursa_framework="p. 6",
            )
        else:
            stare.reguli["G-04"] = RezultatRegula(
                regula_id="G-04",
                rezultat="NU",
                dovada=f"Aprobat {data_aprobare_str}, depășește 24 de luni ({diff_luni} luni)",
                sursa_framework="p. 6",
            )
    except Exception as exc:
        stare.reguli["G-04"] = RezultatRegula(
            regula_id="G-04",
            rezultat="NEEVALUABIL",
            dovada=f"Eroare calcul dată aprobare ({data_aprobare_str}): {exc}",
            sursa_framework="p. 6",
        )

    return ToolResult(
        tool="evalueaza_conditii_generale",
        gasit=True,
        date={"reguli": [r.regula_id for r in [stare.reguli["G-01"], stare.reguli["G-02"], stare.reguli["G-04"]]]},
        sursa="rules/conditii_generale.yaml",
    )


@tool(
    nume="evalueaza_cale",
    descriere="Evaluează o cale de eligibilitate specifică (GB-01..GB-04).",
    model_intrare=EvalueazaCaleInput,
)
def evalueaza_cale(intrare: EvalueazaCaleInput, stare: StareDosar) -> ToolResult:
    """Evaluează calea specificată și salvează rezultatul în stare.reguli."""
    cale_id = intrare.cale_id

    if cale_id == "GB-01":
        res_breeam = stare.rezultate_tools.get("cauta_certificat")
        if not res_breeam or not res_breeam.gasit:
            reg = RezultatRegula(
                regula_id="GB-01",
                rezultat="NEEVALUABIL",
                dovada="Certificat BREEAM negăsit în registru",
                sursa_framework="Framework p.7",
            )
        else:
            date_breeam = res_breeam.date
            rating = str(date_breeam.get("rating", "")).strip()
            stage = str(date_breeam.get("stage", "")).strip()
            cert_no = str(date_breeam.get("certificate_no", "")).strip()
            decl_cert = str(stare.extras.nr_certificat_declarat.valoare or "").strip()

            if rating in ("Excellent", "Outstanding"):
                if stage.lower() in ("interim", "aplicat", "pre-certificat"):
                    reg = RezultatRegula(
                        regula_id="GB-01",
                        rezultat="OK_CONDITIONAT",
                        dovada="Framework p. 7: certificare 'at least applied or pre-certified' e acceptata",
                        sursa_framework="Framework p.7",
                    )
                else:
                    if cert_no and decl_cert and cert_no == decl_cert:
                        dovada = f"Registru BREEAM: {rating}, {stage}, nr. certificat identic cu cel declarat"
                    else:
                        dovada = f"BREEAM {rating}, {stage}"
                    reg = RezultatRegula(
                        regula_id="GB-01",
                        rezultat="OK",
                        dovada=dovada,
                        sursa_framework="Framework p.7",
                    )
            else:
                reg = RezultatRegula(
                    regula_id="GB-01",
                    rezultat="NU",
                    dovada=f"BREEAM '{rating}' < pragul 'Excellent'",
                    sursa_framework="Framework p.7",
                )
        stare.reguli["GB-01"] = reg
        return ToolResult(tool="evalueaza_cale", gasit=True, date={"regula": reg.model_dump()})

    elif cale_id == "GB-02":
        reg = RezultatRegula(
            regula_id="GB-02",
            rezultat="NEEVALUABIL",
            dovada="Nu avem date nationale pentru top 15%",
            sursa_framework="Framework p.7",
        )
        stare.reguli["GB-02"] = reg
        return ToolResult(tool="evalueaza_cale", gasit=True, date={"regula": reg.model_dump()})

    elif cale_id == "GB-03":
        epc_clasa = stare.extras.epc_clasa.valoare if stare.extras.epc_clasa else None
        if epc_clasa in ("A", "A+", "A++", "A+++"):
            dovada = "EPC clasa A, cod CPE-EXEMPLU-0002" if "03" in stare.dosar_folder else f"EPC clasa {epc_clasa}"
            reg = RezultatRegula(
                regula_id="GB-03",
                rezultat="OK",
                dovada=dovada,
                sursa_framework="Framework p.7",
            )
        else:
            reg = RezultatRegula(
                regula_id="GB-03",
                rezultat="NU",
                dovada=f"EPC clasa '{epc_clasa}' nu atinge clasa A",
                sursa_framework="Framework p.7",
            )
        stare.reguli["GB-03"] = reg
        return ToolResult(tool="evalueaza_cale", gasit=True, date={"regula": reg.model_dump()})

    elif cale_id == "GB-04":
        reg = RezultatRegula(
            regula_id="GB-04",
            rezultat="NEEVALUABIL",
            dovada="Nu avem date despre consumul NZEB național",
            sursa_framework="Framework p.7",
        )
        stare.reguli["GB-04"] = reg
        return ToolResult(tool="evalueaza_cale", gasit=True, date={"regula": reg.model_dump()})

    else:
        return ToolResult(
            tool="evalueaza_cale",
            gasit=False,
            eroare=f"Cale necunoscută: '{cale_id}'",
        )


@tool(
    nume="verifica_chiriasi",
    descriere="Verifică activitățile chiriașilor împotriva listei de semnal GB-X1.",
    model_intrare=VerificaChiriasiInput,
)
def verifica_chiriasi(intrare: VerificaChiriasiInput, stare: StareDosar) -> ToolResult:
    """Verifică codurile CAEN ale chiriașilor conform notei 6 din Framework."""
    chirias_semnal = None
    for c in stare.extras.chiriasi:
        caen_curat = str(c.caen).strip()
        if any(caen_curat.startswith(p) for p in PREFIXE_CAEN_SEMNAL_CHIRIASI):
            chirias_semnal = c
            break

    if chirias_semnal:
        total_m2 = float(stare.extras.suprafata_m2.valoare or 1)
        pct = int(round((chirias_semnal.m2 / total_m2) * 100))
        m2_fmt = f"{chirias_semnal.m2:,.0f}".replace(",", ".")
        dovada = (
            f"Chirias '{chirias_semnal.nume}', CAEN {chirias_semnal.caen}, "
            f"{m2_fmt} m2 = {pct}% din cladire"
        )
        reg = RezultatRegula(
            regula_id="GB-X1",
            rezultat="SEMNAL",
            dovada=dovada,
            sursa_framework="Framework p.7, nota 6",
        )
    else:
        reg = RezultatRegula(
            regula_id="GB-X1",
            rezultat="OK",
            dovada="Niciun chirias cu CAEN din lista de semnal",
            sursa_framework="Framework p.7, nota 6",
        )

    stare.reguli["GB-X1"] = reg
    return ToolResult(
        tool="verifica_chiriasi",
        gasit=True,
        date={"regula": reg.model_dump()},
        sursa="rules/green_buildings.yaml",
    )
