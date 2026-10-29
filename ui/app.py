"""Interfață minimalistă GreenProof pentru demonstrarea implementării tehnice (Pitch Deck).

Structură Single-Page concisă, orientată direct pe pipeline:
1. Verdict & Impact CO2
2. Traseul Agentului (Tool-uri & Raționament)
3. Criterii & Reguli Evaluate (Motorul de Reguli)
4. Date Extrase din Documente (Modulul de Extracție)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Optional

# Asigură accesul la rădăcina proiectului când Streamlit rulează din subdirectorul ui/
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from contracts import DosarExtras, Verdict
from agent.orchestrator import proceseaza_dosar


# ---------------------------------------------------------------------------
# Configurare Pagină & Stiluri CSS Curate (Fără elemente inutile)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="GreenProof — Evaluator Green Bond RBI",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
/* Reset & Dark Theme */
[data-testid="stAppViewContainer"] {
    background-color: #121212;
    color: #F3F4F6;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

[data-testid="stSidebar"] {
    background-color: #181818;
    border-right: 1px solid #282828;
}

/* Header simplu */
.gp-header {
    padding: 12px 18px;
    background: #1A1A1A;
    border: 1px solid #2E2E2E;
    border-radius: 6px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.gp-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #FAFAFA;
    margin: 0;
}

.gp-subtitle {
    font-size: 0.78rem;
    color: #9CA3AF;
    margin: 2px 0 0 0;
}

/* Carduri & Containere */
.gp-card {
    background: #1A1A1A;
    border: 1px solid #2B2B2B;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 18px;
}

/* Status Badges */
.gp-badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 700;
    font-family: monospace;
}

.gp-badge-lg {
    font-size: 0.95rem;
    padding: 6px 14px;
}

.gp-badge-ok {
    background-color: rgba(16, 185, 129, 0.15);
    color: #10B981;
    border: 1px solid rgba(16, 185, 129, 0.4);
}

.gp-badge-warn {
    background-color: rgba(245, 158, 11, 0.15);
    color: #F59E0B;
    border: 1px solid rgba(245, 158, 11, 0.4);
}

.gp-badge-alert {
    background-color: rgba(239, 68, 68, 0.15);
    color: #EF4444;
    border: 1px solid rgba(239, 68, 68, 0.4);
}

.gp-badge-info {
    background-color: rgba(6, 182, 212, 0.15);
    color: #06B6D4;
    border: 1px solid rgba(6, 182, 212, 0.4);
}

/* Step Card pentru Agent Trace */
.gp-step-row {
    background: #1E1E1E;
    border: 1px solid #2D2D2D;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 8px;
}

.gp-pill-tool {
    background: #262626;
    color: #FDE047;
    border: 1px solid #3D3D3D;
    font-family: monospace;
    font-size: 0.78rem;
    padding: 2px 6px;
    border-radius: 4px;
}

/* Tabele curate */
.gp-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
}

.gp-table th {
    text-align: left;
    padding: 8px 10px;
    background: #222222;
    color: #9CA3AF;
    font-weight: 600;
    border-bottom: 1px solid #333333;
    font-size: 0.72rem;
    text-transform: uppercase;
}

.gp-table td {
    padding: 8px 10px;
    border-bottom: 1px solid #262626;
    color: #E5E7EB;
    vertical-align: top;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers Încărcare Date
# ---------------------------------------------------------------------------

@st.cache_data
def incarca_catalog_dosare() -> dict[str, str]:
    """Încarcă lista de dosare și descrierile din dosare/index.csv."""
    catalog: dict[str, str] = {}
    csv_path = Path("dosare/index.csv")
    if csv_path.exists():
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d_id = row.get("dosar", "").strip()
                if d_id:
                    catalog[d_id] = row.get("descriere", "")
    return catalog


def citeste_extras(folder_cale: str) -> Optional[DosarExtras]:
    """Extrage datele structurate din dosar sau citește extras_mock.json."""
    cale = Path(folder_cale)
    if not cale.exists():
        return None
    try:
        from extraction.extractor import extrage
        return extrage(folder_cale)
    except Exception:
        mock_file = cale / "extras_mock.json"
        if mock_file.exists():
            try:
                date = json.loads(mock_file.read_text(encoding="utf-8"))
                return DosarExtras(**date)
            except Exception:
                return None
    return None


def get_verdict_badge_html(verdict_tip: str) -> str:
    """Returnează badge-ul HTML pentru verdict."""
    if verdict_tip == "ELIGIBIL":
        return '<span class="gp-badge gp-badge-lg gp-badge-ok">ELIGIBIL</span>'
    elif verdict_tip == "EXCEPTIE_ESCALADARE_COMITET":
        return '<span class="gp-badge gp-badge-lg gp-badge-warn">EXCEPTIE ESCALADARE COMITET</span>'
    elif verdict_tip == "ELIGIBIL_CU_MONITORIZARE":
        return '<span class="gp-badge gp-badge-lg gp-badge-info">ELIGIBIL CU MONITORIZARE</span>'
    elif verdict_tip == "NEELIGIBIL":
        return '<span class="gp-badge gp-badge-lg gp-badge-alert">NEELIGIBIL</span>'
    return f'<span class="gp-badge gp-badge-lg">{verdict_tip}</span>'


def get_rule_badge_html(rezultat: str) -> str:
    """Badge scurt pentru tabelul de reguli."""
    if rezultat == "OK":
        return '<span class="gp-badge gp-badge-ok">OK</span>'
    elif rezultat == "SEMNAL":
        return '<span class="gp-badge gp-badge-warn">SEMNAL</span>'
    elif rezultat == "NU":
        return '<span class="gp-badge gp-badge-alert">NU</span>'
    elif rezultat == "OK_CONDITIONAT":
        return '<span class="gp-badge gp-badge-info">OK CONDITIONAT</span>'
    return f'<span class="gp-badge">{rezultat}</span>'


# ---------------------------------------------------------------------------
# Sidebar: Doar un Dropdown de Selectare a Dosarului
# ---------------------------------------------------------------------------

catalog = incarca_catalog_dosare()
lista_dosare = list(catalog.keys()) if catalog else ["dosar_01_complet_eligibil"]

with st.sidebar:
    st.markdown("### GreenProof")
    st.caption("Raiffeisen Bank Romania")
    st.markdown("---")

    dosar_selectat = st.selectbox(
        "Selectează Dosar:",
        lista_dosare,
        index=0,
    )

    if dosar_selectat in catalog:
        st.caption(f"**Descriere:** {catalog[dosar_selectat]}")

    st.markdown("---")
    st.caption("Modul de analiză se actualizează automat la schimbarea dosarului.")


# ---------------------------------------------------------------------------
# Procesare Automată a Dosarului Selectat
# ---------------------------------------------------------------------------

cale_dosar = str(Path("dosare") / dosar_selectat)

try:
    verdict: Verdict = proceseaza_dosar(cale_dosar)
    extras: Optional[DosarExtras] = citeste_extras(cale_dosar)
except Exception as err:
    st.error(f"Eroare la procesarea dosarului {dosar_selectat}: {err}")
    st.stop()


# ---------------------------------------------------------------------------
# Header Principal Sober
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="gp-header">
        <div>
            <h1 class="gp-title">GreenProof — Evaluator Green Bond RBI</h1>
            <p class="gp-subtitle">Pipeline integrat de extracție documente, verificare tool-uri externe și reguli de conformitate</p>
        </div>
        <div style="font-family: monospace; font-size: 0.75rem; color: #9CA3AF;">
            RBI Framework 2025
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Blocul 1: Verdict Final & Impact CO2 (Rezultatul)
# ---------------------------------------------------------------------------

verdict_badge = get_verdict_badge_html(verdict.verdict)
impact_display = f"{verdict.impact_tco2_an:,.1f} tCO2 / an" if verdict.impact_tco2_an is not None else "N/A"
cale_display = verdict.cale_eligibilitate or "Nicio cale validată"
cui_display = extras.cui.valoare if extras and extras.cui and extras.cui.valoare else "—"

col_v1, col_v2 = st.columns([1.2, 0.8])

with col_v1:
    st.markdown(
        f"""
        <div class="gp-card">
            <div style="font-size: 0.72rem; text-transform: uppercase; color: #9CA3AF; letter-spacing: 0.05em;">Dosar Evaluat: {verdict.dosar_id} (CUI: {cui_display})</div>
            <div style="margin: 8px 0 10px 0;">{verdict_badge}</div>
            <div style="font-size: 0.88rem; color: #D1D5DB;">
                <strong>Cale de Eligibilitate:</strong> <span style="color: #FDE047;">{cale_display}</span>
            </div>
            <div style="font-size: 0.88rem; color: #D1D5DB; margin-top: 4px;">
                <strong>Economie CO2 Alocată Băncii:</strong> <span style="font-weight: bold; color: #FDE047;">{impact_display}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_v2:
    if verdict.actiuni:
        actiuni_html = "".join([f"<li style='margin-bottom: 4px;'>{act}</li>" for act in verdict.actiuni])
        st.markdown(
            f"""
            <div class="gp-card" style="border-left: 3px solid #F59E0B;">
                <div style="font-size: 0.8rem; font-weight: bold; color: #F59E0B; text-transform: uppercase;">Acțiuni Necesare</div>
                <ul style="padding-left: 16px; margin: 6px 0 0 0; font-size: 0.82rem; color: #E5E7EB;">
                    {actiuni_html}
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="gp-card" style="border-left: 3px solid #10B981;">
                <div style="font-size: 0.8rem; font-weight: bold; color: #10B981; text-transform: uppercase;">Conformitate Verificată</div>
                <div style="font-size: 0.82rem; color: #9CA3AF; margin-top: 4px;">
                    Dosarul este complet și validat. Nu sunt necesare măsuri de escaladare sau clarificări suplimentare.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Blocul 2: Traseul Agentului (Cum funcționează Agentul & Tool-urile)
# ---------------------------------------------------------------------------

st.markdown("### 1. Traseul Agentului (Tool Calls & Raționament)")
st.caption("Fiecare acțiune autonomă a agentului: ce tool a apelat, motivul apelului și rezultatul primit.")

for pas in verdict.trace:
    pas_num = pas.get("pas", "-")
    actiune = pas.get("actiune") or "final"
    motiv = pas.get("motiv", "Nespecificat")
    rezultat = pas.get("rezultat", {})
    arg = pas.get("argumente", {})

    arg_str = ", ".join([f"{k}='{v}'" for k, v in arg.items()]) if arg else "fără argumente"

    if isinstance(rezultat, dict):
        if rezultat.get("eroare"):
            res_txt = f'<span class="gp-badge gp-badge-alert">Eroare: {rezultat.get("eroare")}</span>'
        elif rezultat.get("gasit") is True:
            res_txt = '<span class="gp-badge gp-badge-ok">Succes (gasit=True)</span>'
        elif rezultat.get("gasit") is False:
            res_txt = '<span class="gp-badge gp-badge-warn">Negăsit (gasit=False)</span>'
        else:
            res_txt = '<span class="gp-badge">Complet</span>'
    else:
        res_txt = f'<span class="gp-badge gp-badge-ok">{rezultat}</span>'

    st.markdown(
        f"""
        <div class="gp-step-row">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                <div>
                    <span style="font-weight: 700; color: #9CA3AF; font-size: 0.8rem;">Pasul {pas_num}:</span>
                    <span class="gp-pill-tool">{actiune}</span>
                </div>
                <div>{res_txt}</div>
            </div>
            <div style="font-size: 0.84rem; color: #E5E7EB; margin-top: 4px;">
                <strong style="color: #FDE047;">Raționament:</strong> {motiv}
            </div>
            <div style="font-size: 0.75rem; color: #9CA3AF; margin-top: 2px; font-family: monospace;">
                Argumente: {arg_str}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Blocul 3: Criteriile Verificate (Motorul Determinist de Reguli)
# ---------------------------------------------------------------------------

st.markdown("### 2. Criterii Evaluate (Cadrul Green Bond RBI)")

rows_reguli = []
for r in verdict.reguli:
    badge = get_rule_badge_html(r.rezultat)
    rows_reguli.append(f"""
    <tr>
        <td style="font-weight: 700; font-family: monospace;">{r.regula_id}</td>
        <td>{badge}</td>
        <td>{r.dovada}</td>
        <td style="color: #9CA3AF; font-size: 0.78rem;">{r.sursa_framework}</td>
    </tr>
    """)

st.markdown(
    f"""
    <table class="gp-table">
        <thead>
            <tr>
                <th style="width: 90px;">Criteriu</th>
                <th style="width: 130px;">Rezultat</th>
                <th>Dovadă Identificată din Documente / Registre</th>
                <th style="width: 180px;">Referință Cadru RBI</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows_reguli)}
        </tbody>
    </table>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Blocul 4: Date Extrase din Documente (Modulul de Extracție)
# ---------------------------------------------------------------------------

st.markdown("### 3. Date Extrase din Documente")

if extras:
    col_e1, col_e2 = st.columns([1.1, 0.9])

    with col_e1:
        st.markdown("**Parametri Imobil & Finanțare (DosarExtras)**")
        l_parametri = [
            ("CUI Companie", extras.cui),
            ("Suprafață Clădire", extras.suprafata_m2),
            ("Cotă Finanțare Bancă", extras.cota_banca),
            ("Sumă Finanțată", extras.suma_eur),
            ("Dată Aprobare Credit", extras.data_aprobare),
            ("Stadiu Clădire", extras.stadiu_cladire),
            ("Certificat Declarat", extras.nr_certificat_declarat),
        ]
        if extras.epc_clasa:
            l_parametri.append(("Clasă Energetică EPC", extras.epc_clasa))
        if extras.epc_energie_finala:
            l_parametri.append(("Consum Energie Finală", extras.epc_energie_finala))

        rows_p = []
        for eticheta, camp in l_parametri:
            if camp is None:
                continue
            v_val = str(camp.valoare) if camp.valoare is not None else "—"
            sursa_doc = camp.sursa or "—"
            rows_p.append(f"""
            <tr>
                <td style="font-weight: 600;">{eticheta}</td>
                <td style="color: #FDE047; font-weight: bold;">{v_val}</td>
                <td style="font-size: 0.78rem; color: #9CA3AF;">{sursa_doc}</td>
            </tr>
            """)

        st.markdown(
            f"""
            <table class="gp-table">
                <thead>
                    <tr>
                        <th>Parametru</th>
                        <th>Valoare Extrasă</th>
                        <th>Document Sursă</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows_p)}
                </tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )

    with col_e2:
        st.markdown("**Chiriași & Verificare Filtru GB-X1**")
        if extras.chiriasi:
            rows_ch = []
            for ch in extras.chiriasi:
                is_fosil = str(ch.caen).startswith(("06", "19", "05", "09"))
                b_ch = '<span class="gp-badge gp-badge-alert">Fosil (Semnal)</span>' if is_fosil else '<span class="gp-badge gp-badge-ok">Eligibil</span>'
                rows_ch.append(f"""
                <tr>
                    <td style="font-weight: 600;">{ch.nume}</td>
                    <td style="font-family: monospace;">{ch.caen}</td>
                    <td>{ch.m2:,.0f} m²</td>
                    <td>{b_ch}</td>
                </tr>
                """)

            st.markdown(
                f"""
                <table class="gp-table">
                    <thead>
                        <tr>
                            <th>Chiriaș</th>
                            <th>CAEN</th>
                            <th>Suprafață</th>
                            <th>Filtru GB-X1</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_ch)}
                    </tbody>
                </table>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("Nu există chiriași raportați în dosar.")
else:
    st.info("Datele extrase nu sunt disponibile pentru acest dosar.")
