"""Interfața de prezentare și audit GreenProof pentru evaluarea portofoliului Green Bond RBI.

Aplicație Streamlit orientată pe demonstrarea implementării tehnice și a pipeline-ului:
- Extracție date din documente (modul A)
- Registry de tool-uri și audit trail (modul B)
- Motor determinist de reguli și calcul CO2 (modul C)
- Buclă autonomă de decizie a agentului (modul D)
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

# Asigură accesul la rădăcina proiectului când Streamlit rulează din subdirectorul ui/
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from contracts import Camp, Chirias, DosarExtras, RezultatRegula, Verdict
from agent.orchestrator import proceseaza_dosar


# ---------------------------------------------------------------------------
# Configurare Pagină & Stiluri CSS Curate
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

/* Header Sober */
.gp-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    background: #1A1A1A;
    border-radius: 8px;
    border: 1px solid #2E2E2E;
    margin-bottom: 20px;
}

.gp-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #FAFAFA;
    margin: 0;
}

.gp-subtitle {
    font-size: 0.8rem;
    color: #9CA3AF;
    margin: 2px 0 0 0;
}

.gp-badge-meta {
    font-size: 0.75rem;
    background-color: #242424;
    color: #D1D5DB;
    border: 1px solid #383838;
    padding: 4px 10px;
    border-radius: 4px;
    font-family: monospace;
}

/* Carduri */
.gp-card {
    background: #1A1A1A;
    border: 1px solid #2E2E2E;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 16px;
}

.gp-card-hero {
    background: #1C1C1C;
    border: 1px solid #333333;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 20px;
}

/* Status Badges */
.gp-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.03em;
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

/* Grid Metrici */
.gp-metrics-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin-top: 16px;
}

.gp-metric-box {
    background: #222222;
    border: 1px solid #2D2D2D;
    border-radius: 6px;
    padding: 12px 14px;
}

.gp-metric-val {
    font-size: 1.25rem;
    font-weight: 700;
    color: #FFFFFF;
    margin-top: 2px;
}

.gp-metric-lbl {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #9CA3AF;
}

/* Step Card pentru Agent Trace */
.gp-step-box {
    background: #1A1A1A;
    border: 1px solid #2B2B2B;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 12px;
}

.gp-pill-tool {
    display: inline-block;
    background: #242424;
    color: #FDE047;
    border: 1px solid #3D3D3D;
    font-family: monospace;
    font-size: 0.8rem;
    padding: 2px 8px;
    border-radius: 4px;
}

/* Tabele */
.gp-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 6px;
    font-size: 0.85rem;
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
    letter-spacing: 0.03em;
}

.gp-table td {
    padding: 10px;
    border-bottom: 1px solid #262626;
    color: #E5E7EB;
    vertical-align: top;
}

.gp-table tr:hover {
    background-color: #1E1E1E;
}

/* Streamlit Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid #2B2B2B;
}

.stTabs [data-baseweb="tab"] {
    background-color: transparent;
    border-radius: 4px 4px 0 0;
    color: #9CA3AF;
    font-weight: 600;
    padding: 8px 14px;
    font-size: 0.9rem;
}

.stTabs [aria-selected="true"] {
    color: #FDE047 !important;
    border-bottom: 2px solid #FDE047 !important;
}

button[kind="primary"] {
    background-color: #FDE047 !important;
    color: #171717 !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 6px !important;
}

button[kind="secondary"] {
    background-color: #222222 !important;
    color: #FAFAFA !important;
    border: 1px solid #333333 !important;
    border-radius: 6px !important;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers Date & Catalog
# ---------------------------------------------------------------------------

@st.cache_data
def incarca_catalog_dosare() -> dict[str, dict[str, str]]:
    """Încarcă lista de dosare din dosare/index.csv."""
    catalog: dict[str, dict[str, str]] = {}
    csv_path = Path("dosare/index.csv")
    if csv_path.exists():
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                nume = row.get("dosar", "").strip()
                if nume:
                    catalog[nume] = {
                        "descriere": row.get("descriere", ""),
                        "verdict_asteptat": row.get("verdict_asteptat", ""),
                    }
    return catalog


def incarca_exemple_demo() -> dict[str, Path]:
    """Descoperă scenariile demo offline din ui/exemple/."""
    demo_dict: dict[str, Path] = {}
    p = Path("ui/exemple")
    if p.exists():
        for json_file in sorted(p.glob("*.json")):
            demo_dict[json_file.stem] = json_file
    return demo_dict


def citeste_extras_sigur(folder_cale: str) -> Optional[DosarExtras]:
    """Apelează extractorul sau citește extras_mock.json."""
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
    """Badge de verdict."""
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
    """Badge compact pentru tabelul de reguli."""
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
# Bara Laterală (Sidebar)
# ---------------------------------------------------------------------------

catalog = incarca_catalog_dosare()
demo_scenarii = incarca_exemple_demo()

with st.sidebar:
    st.markdown("### GreenProof")
    st.caption("Evaluator Portofoliu Green Bond RBI")
    st.markdown("---")

    sursa_optiune = st.radio(
        "Sursă date:",
        ["Dosare Portofoliu", "Scenarii Demo Offline", "Încărcare Dosar"],
        index=0,
    )

    cale_dosar_selectat: Optional[str] = None
    demo_json_selectat: Optional[Path] = None

    if sursa_optiune == "Dosare Portofoliu":
        lista_dosare = list(catalog.keys()) if catalog else ["dosar_01_complet_eligibil"]
        dosar_ales = st.selectbox("Selectează dosar:", lista_dosare)
        cale_dosar_selectat = str(Path("dosare") / dosar_ales)

        if dosar_ales in catalog:
            st.caption(f"{catalog[dosar_ales]['descriere']}")

    elif sursa_optiune == "Scenarii Demo Offline":
        scenarii_nume = list(demo_scenarii.keys())
        scenariu_ales = st.selectbox("Selectează scenariu demo:", scenarii_nume)
        demo_json_selectat = demo_scenarii[scenariu_ales]

    else:
        fisier_incarcat = st.file_uploader(
            "Încarcă arhivă (.zip) sau document (.pdf)",
            type=["zip", "pdf", "json"],
            accept_multiple_files=False,
        )

        if fisier_incarcat:
            temp_dir = Path(tempfile.gettempdir()) / "greenproof_uploads" / fisier_incarcat.name.replace(".", "_")
            temp_dir.mkdir(parents=True, exist_ok=True)
            if fisier_incarcat.name.endswith(".zip"):
                import zipfile
                with zipfile.ZipFile(fisier_incarcat) as z:
                    z.extractall(temp_dir)
            else:
                (temp_dir / fisier_incarcat.name).write_bytes(fisier_incarcat.getbuffer())
            cale_dosar_selectat = str(temp_dir)
            st.success(f"Încărcat: {fisier_incarcat.name}")

    st.markdown("---")

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        btn_analizeaza = st.button("Analizează", type="primary", use_container_width=True)
    with col_b2:
        btn_batch = st.button("Tot Lotul", type="secondary", use_container_width=True)


# ---------------------------------------------------------------------------
# Header Principal Sober
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="gp-header">
        <div>
            <h1 class="gp-title">GreenProof — Evaluator Green Bond RBI</h1>
            <p class="gp-subtitle">Demonstrație tehnică a pipeline-ului de extracție, reguli deterministe și agent autonom</p>
        </div>
        <div>
            <span class="gp-badge-meta">Framework 2025</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Caz 1: Rulare în Masă (Batch pe toate dosarele)
# ---------------------------------------------------------------------------

if btn_batch:
    st.subheader("Evaluare în Masă — Portofoliu Complet")
    dosare_de_evaluat = list(catalog.keys())
    progres_bar = st.progress(0.0)

    rezultate_batch: list[dict[str, Any]] = []
    co2_total = 0.0

    for idx, d_nume in enumerate(dosare_de_evaluat):
        cale_f = str(Path("dosare") / d_nume)
        try:
            verdict_obj = proceseaza_dosar(cale_f)
            tco2 = verdict_obj.impact_tco2_an or 0.0
            co2_total += tco2
            rezultate_batch.append({
                "Dosar": d_nume,
                "Verdict": verdict_obj.verdict,
                "Cale": verdict_obj.cale_eligibilitate or "—",
                "CO2 (t/an)": f"{tco2:,.1f}" if tco2 > 0 else "—",
                "Pasi": len(verdict_obj.trace),
                "Reguli": len(verdict_obj.reguli),
                "Asteptat": catalog.get(d_nume, {}).get("verdict_asteptat", "—"),
            })
        except Exception as err:
            rezultate_batch.append({
                "Dosar": d_nume,
                "Verdict": "EROARE",
                "Cale": str(err),
                "CO2 (t/an)": "—",
                "Pasi": 0,
                "Reguli": 0,
                "Asteptat": catalog.get(d_nume, {}).get("verdict_asteptat", "—"),
            })
        progres_bar.progress((idx + 1) / len(dosare_de_evaluat))

    progres_bar.empty()

    # Sumar
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Dosare", len(rezultate_batch))
    with col2:
        st.metric("Eligibile", sum(1 for r in rezultate_batch if r["Verdict"] == "ELIGIBIL"))
    with col3:
        st.metric("Monitorizare", sum(1 for r in rezultate_batch if r["Verdict"] == "ELIGIBIL_CU_MONITORIZARE"))
    with col4:
        st.metric("Escaladate", sum(1 for r in rezultate_batch if r["Verdict"] == "EXCEPTIE_ESCALADARE_COMITET"))
    with col5:
        st.metric("Total CO2", f"{co2_total:,.1f} t/an")

    table_rows = []
    for r in rezultate_batch:
        vb = get_verdict_badge_html(r["Verdict"])
        table_rows.append(f"""
        <tr>
            <td style="font-weight: 600;">{r['Dosar']}</td>
            <td>{vb}</td>
            <td style="color: #9CA3AF; font-size: 0.8rem;">{r['Cale']}</td>
            <td style="font-weight: bold; color: #FDE047;">{r['CO2 (t/an)']}</td>
            <td>{r['Pasi']} pasi</td>
            <td style="color: #9CA3AF;">{r['Asteptat']}</td>
        </tr>
        """)

    st.markdown(
        f"""
        <table class="gp-table">
            <thead>
                <tr>
                    <th>Dosar</th>
                    <th>Verdict Agent</th>
                    <th>Cale Eligibilitate</th>
                    <th>CO2 Economisit</th>
                    <th>Audit Agent</th>
                    <th>Verdict Așteptat</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# ---------------------------------------------------------------------------
# Caz 2: Analiză Dosar Individual
# ---------------------------------------------------------------------------

verdict_curent: Optional[Verdict] = None
extras_curent: Optional[DosarExtras] = None

if demo_json_selectat and demo_json_selectat.exists():
    try:
        date_demo = json.loads(demo_json_selectat.read_text(encoding="utf-8"))
        verdict_curent = Verdict(**date_demo)
        if Path(f"dosare/{verdict_curent.dosar_id}").exists():
            extras_curent = citeste_extras_sigur(f"dosare/{verdict_curent.dosar_id}")
    except Exception as err:
        st.error(f"Eroare încărcare scenariu demo: {err}")
elif cale_dosar_selectat:
    try:
        with st.spinner("Procesare dosar..."):
            verdict_curent = proceseaza_dosar(cale_dosar_selectat)
            extras_curent = citeste_extras_sigur(cale_dosar_selectat)
    except Exception as err:
        st.error(f"Eroare procesare dosar: {err}")

if not verdict_curent:
    st.warning("Selectează un dosar din meniul din stânga și apasă 'Analizează'.")
    st.stop()


# ---------------------------------------------------------------------------
# Hero Section — Rezumat Executiv
# ---------------------------------------------------------------------------

dosar_id_display = verdict_curent.dosar_id
verdict_badge = get_verdict_badge_html(verdict_curent.verdict)
impact_str = f"{verdict_curent.impact_tco2_an:,.1f} tCO2/an" if verdict_curent.impact_tco2_an else "N/A"
cale_str = verdict_curent.cale_eligibilitate or "Nicio cale validată"
cui_display = extras_curent.cui.valoare if extras_curent and extras_curent.cui else "—"

st.markdown(
    f"""
    <div class="gp-card-hero">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px;">
            <div>
                <span style="font-size: 0.72rem; text-transform: uppercase; color: #9CA3AF; letter-spacing: 0.05em;">Dosar Evaluat</span>
                <h2 style="font-size: 1.4rem; font-weight: 700; color: #FFFFFF; margin: 2px 0 4px 0;">{dosar_id_display}</h2>
                <div style="font-size: 0.85rem; color: #9CA3AF;">
                    CUI: <strong style="color: #E5E7EB;">{cui_display}</strong> &nbsp;|&nbsp; 
                    Cale: <strong style="color: #FDE047;">{cale_str}</strong>
                </div>
            </div>
            <div>
                {verdict_badge}
            </div>
        </div>
        <div class="gp-metrics-row">
            <div class="gp-metric-box">
                <div class="gp-metric-lbl">Economie CO2</div>
                <div class="gp-metric-val" style="color: #FDE047;">{impact_str}</div>
            </div>
            <div class="gp-metric-box">
                <div class="gp-metric-lbl">Reguli Evaluate</div>
                <div class="gp-metric-val">{len(verdict_curent.reguli)}</div>
            </div>
            <div class="gp-metric-box">
                <div class="gp-metric-lbl">Pași Audit Agent</div>
                <div class="gp-metric-val">{len(verdict_curent.trace)}</div>
            </div>
            <div class="gp-metric-box">
                <div class="gp-metric-lbl">Verdict Final</div>
                <div class="gp-metric-val" style="font-size: 0.95rem; padding-top: 4px;">{verdict_curent.verdict}</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cele 4 Tab-uri
# ---------------------------------------------------------------------------

tab_reguli, tab_agent, tab_extras, tab_documente = st.tabs([
    "Verdict & Reguli",
    "Traseu Agent",
    "Date Extrase",
    "Documente & Export",
])


# ---------------------------------------------------------------------------
# Tab 1: Verdict & Reguli
# ---------------------------------------------------------------------------

with tab_reguli:
    col_stg, col_drp = st.columns([1.1, 0.9])

    with col_stg:
        st.markdown("#### Calcul Impact CO2")
        if verdict_curent.impact_tco2_an is not None:
            detalii = verdict_curent.impact_detalii
            formula = detalii.get("formula", "(baseline - consum) x suprafata x cota_banca x factor_emisie")
            sursa_rep = detalii.get("sursa", "Metodologie RBI Green Bond")
            pasi_calcul = detalii.get("pasi", [])

            pasi_html = "".join([f"<li style='margin-bottom: 4px;'>{p}</li>" for p in pasi_calcul])

            st.markdown(
                f"""
                <div class="gp-card">
                    <div style="font-size: 1.8rem; font-weight: 700; color: #FDE047; margin: 4px 0 8px 0;">
                        {verdict_curent.impact_tco2_an:,.1f} <span style="font-size: 0.9rem; color: #E5E7EB; font-weight: normal;">tCO2 / an</span>
                    </div>
                    <div style="background: #222222; padding: 8px 10px; border-radius: 4px; font-family: monospace; font-size: 0.78rem; color: #E5E7EB; margin-bottom: 10px; border: 1px solid #333333;">
                        Formula: {formula}
                    </div>
                    <div style="font-size: 0.82rem; color: #D1D5DB;">
                        <strong>Pași calcul:</strong>
                        <ul style="padding-left: 18px; margin-top: 4px;">
                            {pasi_html}
                        </ul>
                    </div>
                    <div style="font-size: 0.75rem; color: #9CA3AF; margin-top: 6px;">Sursă metodologie: {sursa_rep}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="gp-card">
                    <strong style="color: #F59E0B;">Calcul CO2 Indisponibil</strong>
                    <p style="font-size: 0.82rem; color: #9CA3AF; margin: 4px 0 0 0;">
                        Emisiile nu pot fi alocate în portofoliul Green Bond fie din cauza unui semnal de excludere ce necesită decizia Comitetului, fie din cauza neîndeplinirii cerințelor de performanță.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_drp:
        st.markdown("#### Acțiuni Necesare")
        if verdict_curent.actiuni:
            actiuni_items = "".join([
                f"""
                <div style="background: rgba(245, 158, 11, 0.08); border-left: 3px solid #F59E0B; padding: 8px 12px; border-radius: 4px; margin-bottom: 6px; font-size: 0.82rem; color: #F3F4F6;">
                    {act}
                </div>
                """
                for act in verdict_curent.actiuni
            ])
            st.markdown(f'<div class="gp-card">{actiuni_items}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                """
                <div class="gp-card" style="border-left: 3px solid #10B981;">
                    <div style="color: #10B981; font-weight: 600; font-size: 0.85rem;">Conformitate Verificată</div>
                    <p style="font-size: 0.8rem; color: #9CA3AF; margin: 4px 0 0 0;">
                        Nu sunt necesare acțiuni corective sau escaladări către comitet.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Tabel reguli evaluate
    st.markdown("#### Matrice Reguli Evaluate (Framework RBI)")
    table_rules = []
    for r in verdict_curent.reguli:
        rb = get_rule_badge_html(r.rezultat)
        table_rules.append(f"""
        <tr>
            <td style="font-weight: 700; font-family: monospace; color: #FAFAFA;">{r.regula_id}</td>
            <td>{rb}</td>
            <td style="color: #E5E7EB;">{r.dovada}</td>
            <td style="color: #9CA3AF; font-size: 0.78rem;">{r.sursa_framework}</td>
        </tr>
        """)

    st.markdown(
        f"""
        <table class="gp-table">
            <thead>
                <tr>
                    <th style="width: 100px;">Regulă</th>
                    <th style="width: 140px;">Rezultat</th>
                    <th>Dovadă Audit</th>
                    <th style="width: 180px;">Sursă Framework</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rules)}
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Tab 2: Traseu Agent (Audit Trail)
# ---------------------------------------------------------------------------

with tab_agent:
    st.markdown("#### Traseul de Decizie al Agentului (Tool Calls & Reasoning)")
    st.caption("Fiecare pas arată tool-ul apelat de agent, motivul / raționamentul și rezultatul primit.")

    for idx, pas in enumerate(verdict_curent.trace, start=1):
        pas_num = pas.get("pas", idx)
        tip = pas.get("tip", "tool")
        actiune = pas.get("actiune") or "final"
        motiv = pas.get("motiv", "Nespecificat")
        ts = pas.get("timestamp", "—")
        arg = pas.get("argumente", {})
        rezultat = pas.get("rezultat", {})

        arg_str = ", ".join([f"{k}='{v}'" for k, v in arg.items()]) if arg else "fără argumente"

        # Stare rezultat
        if isinstance(rezultat, dict):
            gasit = rezultat.get("gasit")
            eroare = rezultat.get("eroare")
            if eroare:
                res_badge = f'<span class="gp-badge gp-badge-alert">Eroare: {eroare}</span>'
            elif gasit is True:
                res_badge = '<span class="gp-badge gp-badge-ok">Succes (gasit=True)</span>'
            elif gasit is False:
                res_badge = '<span class="gp-badge gp-badge-warn">Negăsit (gasit=False)</span>'
            else:
                res_badge = '<span class="gp-badge">Complet</span>'
        else:
            res_badge = f'<span class="gp-badge gp-badge-ok">{rezultat}</span>'

        st.markdown(
            f"""
            <div class="gp-step-box">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; flex-wrap: wrap;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-weight: 700; color: #9CA3AF; font-size: 0.8rem;">Pasul {pas_num}:</span>
                        <span class="gp-pill-tool">{actiune}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        {res_badge}
                        <span style="font-size: 0.72rem; color: #737373;">{ts}</span>
                    </div>
                </div>
                <div style="font-size: 0.85rem; color: #E5E7EB; margin-top: 4px;">
                    <strong style="color: #FDE047;">Raționament:</strong> {motiv}
                </div>
                <div style="font-size: 0.78rem; color: #9CA3AF; margin-top: 2px; font-family: monospace;">
                    Argumente: {arg_str}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander(f"JSON Pasul {pas_num} ({actiune})"):
            st.json(pas)


# ---------------------------------------------------------------------------
# Tab 3: Date Extrase
# ---------------------------------------------------------------------------

with tab_extras:
    st.markdown("#### Date Extrase din Documente")

    if extras_curent:
        col_c1, col_c2 = st.columns([1.1, 0.9])

        with col_c1:
            st.markdown("##### Indicatori DosarExtras")

            l_indicatori = [
                ("CUI Companie", extras_curent.cui),
                ("Suprafață Clădire", extras_curent.suprafata_m2),
                ("Cotă Finanțare Bancă", extras_curent.cota_banca),
                ("Sumă Finanțată", extras_curent.suma_eur),
                ("Dată Aprobare Credit", extras_curent.data_aprobare),
                ("Țară Proiect", extras_curent.tara),
                ("Stadiu Clădire", extras_curent.stadiu_cladire),
                ("Certificat Declarat", extras_curent.nr_certificat_declarat),
            ]

            if extras_curent.epc_clasa:
                l_indicatori.append(("Clasă EPC", extras_curent.epc_clasa))
            if extras_curent.epc_energie_finala:
                l_indicatori.append(("Consum Energie Finală", extras_curent.epc_energie_finala))

            rows_ind = []
            for eticheta, c in l_indicatori:
                if c is None:
                    continue
                v_str = str(c.valoare) if c.valoare is not None else "—"
                inc_pct = int(c.incredere * 100) if c.incredere is not None else 100
                inc_color = "#10B981" if inc_pct >= 70 else "#F59E0B"
                rows_ind.append(f"""
                <tr>
                    <td style="font-weight: 600;">{eticheta}</td>
                    <td style="color: #FDE047; font-weight: bold;">{v_str}</td>
                    <td style="font-size: 0.78rem; color: #9CA3AF;">{c.sursa or '—'}</td>
                    <td style="color: {inc_color}; font-weight: bold; font-size: 0.8rem;">{inc_pct}%</td>
                </tr>
                """)

            st.markdown(
                f"""
                <table class="gp-table">
                    <thead>
                        <tr>
                            <th>Parametru</th>
                            <th>Valoare</th>
                            <th>Sursă Document</th>
                            <th>Încredere</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_ind)}
                    </tbody>
                </table>
                """,
                unsafe_allow_html=True,
            )

        with col_c2:
            st.markdown("##### Chiriași (Filtru GB-X1)")
            if extras_curent.chiriasi:
                rows_ch = []
                for ch in extras_curent.chiriasi:
                    is_fosil = str(ch.caen).startswith(("06", "19", "05", "09"))
                    badg = '<span class="gp-badge gp-badge-alert">Fosil / Exclus</span>' if is_fosil else '<span class="gp-badge gp-badge-ok">Eligibil</span>'
                    rows_ch.append(f"""
                    <tr>
                        <td style="font-weight: 600;">{ch.nume}</td>
                        <td style="font-family: monospace;">{ch.caen}</td>
                        <td>{ch.m2:,.0f} m²</td>
                        <td>{badg}</td>
                    </tr>
                    """)

                st.markdown(
                    f"""
                    <table class="gp-table">
                        <thead>
                            <tr>
                                <th>Nume Chiriaș</th>
                                <th>Cod CAEN</th>
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

            if extras_curent.afirmatii_client:
                st.markdown("##### Declarații Client")
                st.markdown(
                    "".join([f"<li style='font-size: 0.82rem; color: #D1D5DB; margin-bottom: 2px;'>{a}</li>" for a in extras_curent.afirmatii_client]),
                    unsafe_allow_html=True,
                )
    else:
        st.info("Datele DosarExtras nu sunt disponibile pentru acest scenariu.")


# ---------------------------------------------------------------------------
# Tab 4: Documente & Export
# ---------------------------------------------------------------------------

with tab_documente:
    st.markdown("#### Documente Dosar & Export Rezultate")

    col_doc_stg, col_doc_drp = st.columns([1, 1])

    with col_doc_stg:
        st.markdown("##### Fișiere Identificate")
        folder_fizic = Path(cale_dosar_selectat) if cale_dosar_selectat else Path(f"dosare/{verdict_curent.dosar_id}")

        if folder_fizic.exists():
            fisiere = [f for f in folder_fizic.iterdir() if f.is_file() and not f.name.startswith(".")]
            rows_files = []
            for f in sorted(fisiere, key=lambda x: x.name):
                dim_kb = f.stat().st_size / 1024
                ext = f.suffix.upper().replace(".", "")
                rows_files.append(f"""
                <tr>
                    <td style="font-weight: 500;">{f.name}</td>
                    <td><span class="gp-pill-tool">{ext}</span></td>
                    <td style="color: #9CA3AF;">{dim_kb:.1f} KB</td>
                </tr>
                """)

            st.markdown(
                f"""
                <table class="gp-table">
                    <thead>
                        <tr>
                            <th>Nume Fișier</th>
                            <th>Format</th>
                            <th>Mărime</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_files)}
                    </tbody>
                </table>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("Fișierele originale nu sunt prezente pe disc pentru acest scenariu offline.")

    with col_doc_drp:
        st.markdown("##### Export Rezultate")
        json_export = verdict_curent.model_dump_json(indent=2)
        st.download_button(
            label="Descarcă Verdict JSON",
            data=json_export,
            file_name=f"verdict_{verdict_curent.dosar_id}.json",
            mime="application/json",
            use_container_width=True,
        )

        md_report = f"""# RAPORT EVALUARE GREEN BOND — GREENPROOF
Dosar: {verdict_curent.dosar_id}
Verdict: {verdict_curent.verdict}
Cale: {verdict_curent.cale_eligibilitate or 'Niciuna'}
Impact CO2: {verdict_curent.impact_tco2_an or 'N/A'} tCO2/an
Data: {time.strftime('%Y-%m-%d %H:%M:%S')}

Reguli Evaluate:
""" + "\n".join([f"- {r.regula_id} [{r.rezultat}]: {r.dovada} ({r.sursa_framework})" for r in verdict_curent.reguli]) + f"""

Actiuni Recomandate:
""" + ("\n".join([f"- {a}" for a in verdict_curent.actiuni]) if verdict_curent.actiuni else "- Nicio actiune necesara.") + f"""

Audit Trail: {len(verdict_curent.trace)} pasi executati.
"""

        st.download_button(
            label="Descarcă Raport Text / Markdown",
            data=md_report,
            file_name=f"raport_{verdict_curent.dosar_id}.md",
            mime="text/markdown",
            use_container_width=True,
        )
