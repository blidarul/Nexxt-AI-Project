"""Interfața de prezentare și audit GreenProof pentru evaluarea portofoliului Green Bond RBI.

Aplicație Streamlit cu temă dark (GreenProof), conformă cu designul Lovable,
integrată complet cu extractorul, registry-ul de tool-uri și motorul de reguli.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import streamlit as st

from contracts import Camp, Chirias, DosarExtras, RezultatRegula, Verdict
from agent.orchestrator import proceseaza_dosar


# ---------------------------------------------------------------------------
# Configurare Pagină & Stiluri CSS (Design GreenProof)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="GreenProof — Evaluator Green Bond RBI",
    page_icon="🌿",
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
    background-color: #171717;
    border-right: 1px solid #282828;
}

/* Header GreenProof */
.gp-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    background: #181818;
    border-radius: 12px;
    border: 1px solid #2E2E2E;
    margin-bottom: 24px;
}

.gp-logo-box {
    display: flex;
    align-items: center;
    gap: 12px;
}

.gp-logo-icon {
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    background-color: #FDE047;
    color: #171717;
    border-radius: 8px;
    font-size: 20px;
    font-weight: bold;
}

.gp-title {
    font-size: 1.35rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #FAFAFA;
    margin: 0;
}

.gp-subtitle {
    font-size: 0.8rem;
    color: #9CA3AF;
    margin: 0;
}

.gp-badge-meta {
    font-size: 0.75rem;
    background-color: #242424;
    color: #E5E7EB;
    border: 1px solid #383838;
    padding: 4px 10px;
    border-radius: 9999px;
    font-weight: 500;
}

/* Carduri & Containere */
.gp-card {
    background: #1A1A1A;
    border: 1px solid #2B2B2B;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 18px;
}

.gp-card-hero {
    background: linear-gradient(180deg, #1E1E1E 0%, #171717 100%);
    border: 1px solid #333333;
    border-radius: 14px;
    padding: 24px;
    margin-bottom: 22px;
}

/* Status Badges */
.gp-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 9999px;
    font-size: 0.85rem;
    font-weight: 700;
    letter-spacing: 0.02em;
}

.gp-badge-lg {
    font-size: 1.05rem;
    padding: 8px 18px;
}

.gp-badge-ok {
    background-color: rgba(16, 185, 129, 0.15);
    color: #10B981;
    border: 1px solid rgba(16, 185, 129, 0.35);
}

.gp-badge-warn {
    background-color: rgba(245, 158, 11, 0.15);
    color: #F59E0B;
    border: 1px solid rgba(245, 158, 11, 0.35);
}

.gp-badge-alert {
    background-color: rgba(239, 68, 68, 0.15);
    color: #EF4444;
    border: 1px solid rgba(239, 68, 68, 0.35);
}

.gp-badge-info {
    background-color: rgba(6, 182, 212, 0.15);
    color: #06B6D4;
    border: 1px solid rgba(6, 182, 212, 0.35);
}

/* Metrics Grid */
.gp-metrics-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
    margin-top: 18px;
}

.gp-metric-box {
    background: #212121;
    border: 1px solid #2E2E2E;
    border-radius: 10px;
    padding: 14px 16px;
}

.gp-metric-val {
    font-size: 1.35rem;
    font-weight: 700;
    color: #FFFFFF;
    margin-top: 4px;
}

.gp-metric-lbl {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #9CA3AF;
}

/* Timeline Stepper */
.gp-timeline-step {
    border-left: 2px solid #333333;
    padding-left: 20px;
    position: relative;
    margin-bottom: 22px;
}

.gp-timeline-bullet {
    position: absolute;
    left: -11px;
    top: 2px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #FDE047;
    color: #171717;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: bold;
}

.gp-timeline-content {
    background: #1C1C1C;
    border: 1px solid #2E2E2E;
    border-radius: 10px;
    padding: 14px 16px;
}

.gp-pill-tool {
    display: inline-block;
    background: #262626;
    color: #FDE047;
    border: 1px solid #3D3D3D;
    font-family: monospace;
    font-size: 0.78rem;
    padding: 3px 8px;
    border-radius: 6px;
}

/* Tabele Personalizate */
.gp-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    font-size: 0.88rem;
}

.gp-table th {
    text-align: left;
    padding: 10px 12px;
    background: #212121;
    color: #A3A3A3;
    font-weight: 600;
    border-bottom: 1px solid #333333;
    text-transform: uppercase;
    font-size: 0.72rem;
    letter-spacing: 0.04em;
}

.gp-table td {
    padding: 12px;
    border-bottom: 1px solid #262626;
    color: #E5E7EB;
    vertical-align: top;
}

.gp-table tr:hover {
    background-color: #1E1E1E;
}

/* Streamlit Native Adjustments */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid #2B2B2B;
}

.stTabs [data-baseweb="tab"] {
    background-color: transparent;
    border-radius: 8px 8px 0 0;
    color: #9CA3AF;
    font-weight: 600;
    padding: 10px 16px;
}

.stTabs [aria-selected="true"] {
    color: #FDE047 !important;
    border-bottom: 2px solid #FDE047 !important;
}

button[kind="primary"] {
    background-color: #FDE047 !important;
    color: #171717 !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
}

button[kind="secondary"] {
    background-color: #222222 !important;
    color: #FAFAFA !important;
    border: 1px solid #333333 !important;
    border-radius: 8px !important;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers Încărcare & Date
# ---------------------------------------------------------------------------

@st.cache_data
def incarca_catalog_dosare() -> dict[str, dict[str, str]]:
    """Încarcă metadatele dosarelor disponibile din dosare/index.csv."""
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
    """Descoperă scenariile demo offline disponibile în ui/exemple/."""
    demo_dict: dict[str, Path] = {}
    p = Path("ui/exemple")
    if p.exists():
        for json_file in sorted(p.glob("*.json")):
            demo_dict[json_file.stem] = json_file
    return demo_dict


def citeste_extras_sigur(folder_cale: str) -> Optional[DosarExtras]:
    """Încearcă extragerea directă prin modulul de extracție sau din extras_mock.json."""
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
    """Returnează elementul HTML pentru badge-ul de verdict conform Lovable design."""
    if verdict_tip == "ELIGIBIL":
        return '<span class="gp-badge gp-badge-lg gp-badge-ok">● ELIGIBIL GREEN BOND</span>'
    elif verdict_tip == "EXCEPTIE_ESCALADARE_COMITET":
        return '<span class="gp-badge gp-badge-lg gp-badge-warn">▲ REVIZUIRE — ESCALADARE COMITET</span>'
    elif verdict_tip == "ELIGIBIL_CU_MONITORIZARE":
        return '<span class="gp-badge gp-badge-lg gp-badge-info">◆ ELIGIBIL CU MONITORIZARE</span>'
    elif verdict_tip == "NEELIGIBIL":
        return '<span class="gp-badge gp-badge-lg gp-badge-alert">✕ NEELIGIBIL</span>'
    return f'<span class="gp-badge gp-badge-lg">{verdict_tip}</span>'


def get_rule_badge_html(rezultat: str) -> str:
    """Badge compact pentru tabelul de reguli."""
    if rezultat == "OK":
        return '<span class="gp-badge gp-badge-ok">✓ OK</span>'
    elif rezultat == "SEMNAL":
        return '<span class="gp-badge gp-badge-warn">⚠ SEMNAL</span>'
    elif rezultat == "NU":
        return '<span class="gp-badge gp-badge-alert">✕ REFUZAT</span>'
    elif rezultat == "OK_CONDITIONAT":
        return '<span class="gp-badge gp-badge-info">◆ CONDIȚIONAT</span>'
    return f'<span class="gp-badge">{rezultat}</span>'


# ---------------------------------------------------------------------------
# Bara Laterală (Sidebar) - Navigare & Încărcare Dosar
# ---------------------------------------------------------------------------

catalog = incarca_catalog_dosare()
demo_scenarii = incarca_exemple_demo()

with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 14px;">
            <div style="width: 32px; height: 32px; border-radius: 8px; background: #FDE047; display: grid; place-items: center; color: #171717; font-weight: bold; font-size: 18px;">🌿</div>
            <div>
                <h2 style="font-size: 1.25rem; font-weight: 700; margin: 0; color: #FAFAFA;">GreenProof</h2>
                <p style="font-size: 0.72rem; color: #9CA3AF; margin: 0;">Motor Inteligent de Audit Green Bond</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### 📂 Selectare Dosar")

    sursa_optiune = st.radio(
        "Sursă date:",
        ["📁 Dosare Portofoliu (Bancă)", "⚡ Scenarii Demo Offline", "📤 Încărcare Dosar Nou"],
        index=0,
    )

    cale_dosar_selectat: Optional[str] = None
    demo_json_selectat: Optional[Path] = None
    dosar_eticheta = ""

    if sursa_optiune == "📁 Dosare Portofoliu (Bancă)":
        lista_dosare = list(catalog.keys()) if catalog else ["dosar_01_complet_eligibil"]
        def_fmt = lambda d: f"{d} — {catalog[d]['descriere'][:38]}..." if d in catalog and catalog[d]['descriere'] else d
        dosar_ales = st.selectbox("Alege dosarul din sistem:", lista_dosare, format_func=def_fmt)
        cale_dosar_selectat = str(Path("dosare") / dosar_ales)
        dosar_eticheta = dosar_ales

        if dosar_ales in catalog:
            st.info(f"**Descriere:** {catalog[dosar_ales]['descriere']}\n\n*Verdict așteptat de referință:* `{catalog[dosar_ales]['verdict_asteptat']}`")

    elif sursa_optiune == "⚡ Scenarii Demo Offline":
        scenarii_nume = list(demo_scenarii.keys())
        demo_etichete = {
            "dosar_eligibil": "✅ Dosar 01: Eligibil Complet (BREEAM Excellent Final)",
            "dosar_exceptie": "⚠️ Dosar 02: Semnal Excepție (Chiriaș Combustibili Fosili)",
            "dosar_neeligibil": "❌ Demo 03: Neeligibil (Renovare < 30% reducere consum)",
        }
        scenariu_ales = st.selectbox(
            "Alege scenariul demonstrativ:",
            scenarii_nume,
            format_func=lambda s: demo_etichete.get(s, s),
        )
        demo_json_selectat = demo_scenarii[scenariu_ales]
        dosar_eticheta = scenariu_ales

    else:
        st.markdown("Încarcă documentele dosarului sau o arhivă `.zip`:")
        fisier_incarcat = st.file_uploader(
            "Trage sau alege fișiere (ZIP sau PDF-uri)",
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
            dosar_eticheta = f"Upload: {fisier_incarcat.name}"
            st.success(f"Dosar încărcat cu succes: `{fisier_incarcat.name}`")

    st.markdown("---")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        btn_analizeaza = st.button("🚀 Analizează", type="primary", use_container_width=True)
    with col_btn2:
        btn_batch = st.button("⚡ Tot Lotul", type="secondary", use_container_width=True)

    st.markdown(
        """
        <div style="background: #1F1F1F; border: 1px solid #2B2B2B; border-radius: 8px; padding: 12px; margin-top: 20px; font-size: 0.75rem; color: #9CA3AF;">
            <strong style="color: #FAFAFA;">RBI Framework v2025</strong><br>
            • Criterii Green Buildings (GB-01 – GB-04)<br>
            • Filtre de excludere & CAEN (G-02, GB-X1)<br>
            • Metodologie emisie CO₂ Ember & Discodata<br>
            • Validare automată ANAF & Registru BREEAM
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Zona Principală: Header GreenProof
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="gp-header">
        <div class="gp-logo-box">
            <div class="gp-logo-icon">🌿</div>
            <div>
                <h1 class="gp-title">GreenProof</h1>
                <p class="gp-subtitle">Raiffeisen Bank Romania — Evaluare Automată Portofoliu Green Bond</p>
            </div>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
            <span class="gp-badge-meta">Framework 2025</span>
            <span class="gp-badge-meta">Agent Autonom v2.4</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cazul 1: Rulare în Masă (Evaluarea Tuturor Dosarelor din Portofoliu)
# ---------------------------------------------------------------------------

if btn_batch:
    st.subheader("⚡ Raport Evaluare în Masă — Toate Dosarele")
    st.caption("Execută procesarea automată completă prin agent pentru fiecare dosar din catalog.")

    dosare_de_evaluat = list(catalog.keys())
    progres_bar = st.progress(0.0)
    status_text = st.empty()

    rezultate_batch: list[dict[str, Any]] = []
    co2_total = 0.0
    start_time = time.time()

    for idx, d_nume in enumerate(dosare_de_evaluat):
        status_text.text(f"Se analizează dosarul {idx+1}/{len(dosare_de_evaluat)}: {d_nume}...")
        cale_f = str(Path("dosare") / d_nume)
        try:
            verdict_obj = proceseaza_dosar(cale_f)
            tco2 = verdict_obj.impact_tco2_an or 0.0
            co2_total += tco2
            rezultate_batch.append({
                "Dosar": d_nume,
                "Verdict Obținut": verdict_obj.verdict,
                "Cale Eligibilitate": verdict_obj.cale_eligibilitate or "—",
                "Economie CO₂ (t/an)": f"{tco2:,.1f}" if tco2 > 0 else "—",
                "Pași Agent": len(verdict_obj.trace),
                "Reguli Evaluate": len(verdict_obj.reguli),
                "Așteptat": catalog.get(d_nume, {}).get("verdict_asteptat", "—"),
            })
        except Exception as err:
            rezultate_batch.append({
                "Dosar": d_nume,
                "Verdict Obținut": "EROARE",
                "Cale Eligibilitate": str(err),
                "Economie CO₂ (t/an)": "—",
                "Pași Agent": 0,
                "Reguli Evaluate": 0,
                "Așteptat": catalog.get(d_nume, {}).get("verdict_asteptat", "—"),
            })
        progres_bar.progress((idx + 1) / len(dosare_de_evaluat))

    durata = time.time() - start_time
    status_text.empty()
    progres_bar.empty()

    # Sumar metrici lot
    total_dosare = len(rezultate_batch)
    eligibile = sum(1 for r in rezultate_batch if r["Verdict Obținut"] == "ELIGIBIL")
    escaladate = sum(1 for r in rezultate_batch if r["Verdict Obținut"] == "EXCEPTIE_ESCALADARE_COMITET")
    monitorizare = sum(1 for r in rezultate_batch if r["Verdict Obținut"] == "ELIGIBIL_CU_MONITORIZARE")
    neeligibile = sum(1 for r in rezultate_batch if r["Verdict Obținut"] == "NEELIGIBIL")

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Dosare", total_dosare)
    with col2:
        st.metric("Eligibile", eligibile, delta=f"{eligibile/total_dosare*100:.0f}%")
    with col3:
        st.metric("Monitorizare", monitorizare)
    with col4:
        st.metric("Escaladate", escaladate)
    with col5:
        st.metric("Total CO₂ Economisit", f"{co2_total:,.1f} t/an")

    st.markdown("#### Tabel Sinoptic Portofoliu")

    table_rows = []
    for r in rezultate_batch:
        vb = get_verdict_badge_html(r["Verdict Obținut"])
        table_rows.append(f"""
        <tr>
            <td style="font-weight: 600; color: #FAFAFA;">{r['Dosar']}</td>
            <td>{vb}</td>
            <td style="color: #9CA3AF; font-size: 0.8rem;">{r['Cale Eligibilitate']}</td>
            <td style="font-weight: bold; color: #FDE047;">{r['Economie CO₂ (t/an)']}</td>
            <td>{r['Pași Agent']} pași</td>
            <td style="color: #A3A3A3;">{r['Așteptat']}</td>
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
                    <th>CO₂ Economisit</th>
                    <th>Audit Agent</th>
                    <th>Referință Așteptată</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
        <div style="margin-top: 10px; font-size: 0.8rem; color: #9CA3AF;">Procesare încheiată în {durata:.2f} secunde.</div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# ---------------------------------------------------------------------------
# Cazul 2: Analiză Dosar Individual (Activ implicit sau la cerere)
# ---------------------------------------------------------------------------

verdict_curent: Optional[Verdict] = None
extras_curent: Optional[DosarExtras] = None

# Determinăm sursa datelor
if demo_json_selectat and demo_json_selectat.exists():
    try:
        date_demo = json.loads(demo_json_selectat.read_text(encoding="utf-8"))
        verdict_curent = Verdict(**date_demo)
        # Dacă există un dosar fizic asociat în dosare/, încercăm să aducem extras
        if Path(f"dosare/{verdict_curent.dosar_id}").exists():
            extras_curent = citeste_extras_sigur(f"dosare/{verdict_curent.dosar_id}")
    except Exception as err:
        st.error(f"Eroare la încărcarea scenariului demo: {err}")
elif cale_dosar_selectat:
    try:
        with st.spinner("Agentul GreenProof analizează documentele și execută regulile de conformitate..."):
            verdict_curent = proceseaza_dosar(cale_dosar_selectat)
            extras_curent = citeste_extras_sigur(cale_dosar_selectat)
    except Exception as err:
        st.error(f"Eroare la procesarea dosarului '{cale_dosar_selectat}': {err}")

if not verdict_curent:
    st.warning("Vă rugăm să selectați un dosar din meniul lateral și să apăsați pe 'Analizează'.")
    st.stop()


# ---------------------------------------------------------------------------
# Hero Banner — Sinteză & Decizie GreenProof
# ---------------------------------------------------------------------------

dosar_id_display = verdict_curent.dosar_id
verdict_badge = get_verdict_badge_html(verdict_curent.verdict)
impact_str = f"{verdict_curent.impact_tco2_an:,.1f} tCO₂/an" if verdict_curent.impact_tco2_an else "Neatribuit"
cale_str = verdict_curent.cale_eligibilitate or "Nicio cale validată"
reguli_count = len(verdict_curent.reguli)
trace_count = len(verdict_curent.trace)

# Obținem CUI-ul dacă avem extras
cui_display = extras_curent.cui.valoare if extras_curent and extras_curent.cui else "—"

st.markdown(
    f"""
    <div class="gp-card-hero">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 14px;">
            <div>
                <span style="font-size: 0.72rem; text-transform: uppercase; color: #9CA3AF; letter-spacing: 0.08em; font-weight: 600;">Dosar de Finanțare</span>
                <h2 style="font-size: 1.6rem; font-weight: 800; color: #FFFFFF; margin: 2px 0 6px 0;">{dosar_id_display}</h2>
                <div style="font-size: 0.85rem; color: #9CA3AF;">
                    CUI Companie: <strong style="color: #E5E7EB;">{cui_display}</strong> &nbsp;•&nbsp; 
                    Cale Evaluată: <strong style="color: #FDE047;">{cale_str}</strong>
                </div>
            </div>
            <div>
                {verdict_badge}
            </div>
        </div>
        <div class="gp-metrics-row">
            <div class="gp-metric-box">
                <div class="gp-metric-lbl">Impact Climatic CO₂</div>
                <div class="gp-metric-val" style="color: #FDE047;">{impact_str}</div>
            </div>
            <div class="gp-metric-box">
                <div class="gp-metric-lbl">Reguli Evaluate</div>
                <div class="gp-metric-val">{reguli_count} <span style="font-size: 0.8rem; color: #9CA3AF; font-weight: normal;">criterii RBI</span></div>
            </div>
            <div class="gp-metric-box">
                <div class="gp-metric-lbl">Traseu Audit Agent</div>
                <div class="gp-metric-val">{trace_count} <span style="font-size: 0.8rem; color: #9CA3AF; font-weight: normal;">pași verificați</span></div>
            </div>
            <div class="gp-metric-box">
                <div class="gp-metric-lbl">Stare Portofoliu</div>
                <div class="gp-metric-val" style="font-size: 1.05rem; padding-top: 4px;">{verdict_curent.verdict}</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cele 4 Tab-uri de Navigare și Audit Detaliat
# ---------------------------------------------------------------------------

tab_reguli, tab_agent, tab_extras, tab_documente = st.tabs([
    "⚖️ Verdict & Reguli RBI",
    "🤖 Traseul Agentului (Audit)",
    "📊 Date Extrase & Flotă",
    "📁 Documente & Raport",
])


# ---------------------------------------------------------------------------
# Tab 1: Verdict & Reguli RBI (Criterii, Impact CO2, Acțiuni)
# ---------------------------------------------------------------------------

with tab_reguli:
    col_stg, col_drp = st.columns([1.1, 0.9])

    with col_stg:
        st.markdown("#### 🌿 Calculul Economiei de Emisii CO₂")
        if verdict_curent.impact_tco2_an is not None:
            detalii = verdict_curent.impact_detalii
            formula = detalii.get("formula", "(baseline - consum) x suprafata x cota_banca x factor_emisie")
            sursa_rep = detalii.get("sursa", "Metodologie RBI Green Bond")
            pasi_calcul = detalii.get("pasi", [])
            atentie = detalii.get("atentie", "")

            pasi_html = "".join([f"<li style='margin-bottom: 4px;'>{p}</li>" for p in pasi_calcul])

            st.markdown(
                f"""
                <div class="gp-card">
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-size: 0.75rem; text-transform: uppercase; color: #9CA3AF;">Economie Totală Alocată Băncii</span>
                        <span style="font-size: 0.75rem; color: #9CA3AF;">{sursa_rep}</span>
                    </div>
                    <div style="font-size: 2.2rem; font-weight: 800; color: #FDE047; margin: 8px 0;">
                        {verdict_curent.impact_tco2_an:,.1f} <span style="font-size: 1rem; color: #E5E7EB; font-weight: normal;">tCO₂ / an</span>
                    </div>
                    <div style="background: #242424; padding: 10px 12px; border-radius: 6px; font-family: monospace; font-size: 0.8rem; color: #E5E7EB; margin-bottom: 12px; border: 1px solid #333333;">
                        Formula: {formula}
                    </div>
                    <div style="font-size: 0.85rem; color: #D1D5DB;">
                        <strong>Etapele de calcul determinist:</strong>
                        <ul style="padding-left: 20px; margin-top: 6px;">
                            {pasi_html}
                        </ul>
                    </div>
                    {f'<div style="margin-top: 8px; font-size: 0.75rem; color: #9CA3AF; font-style: italic;">ℹ️ {atentie}</div>' if atentie else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="gp-card" style="border-left: 4px solid #F59E0B;">
                    <h4 style="margin: 0 0 6px 0; color: #F59E0B; font-size: 1rem;">Calcul de Impact Indisponibil sau Blocat</h4>
                    <p style="font-size: 0.85rem; color: #D1D5DB; margin: 0;">
                        Emisiile de CO₂ nu sunt alocate în portofoliul Green Bond fie din cauza unui semnal de excludere ce necesită decizia Comitetului de Sustenabilitate, fie din cauza neîndeplinirii cerințelor minime de performanță energetică.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_drp:
        st.markdown("#### 📋 Acțiuni Necesare & Recomandări")
        if verdict_curent.actiuni:
            actiuni_items = "".join([
                f"""
                <div style="background: rgba(245, 158, 11, 0.08); border-left: 3px solid #F59E0B; padding: 10px 14px; border-radius: 4px; margin-bottom: 8px; font-size: 0.85rem; color: #F3F4F6;">
                    {act}
                </div>
                """
                for act in verdict_curent.actiuni
            ])
            st.markdown(f'<div class="gp-card">{actiuni_items}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                """
                <div class="gp-card" style="border-left: 4px solid #10B981;">
                    <div style="display: flex; align-items: center; gap: 8px; color: #10B981; font-weight: 600;">
                        ✓ Conformitate Totală
                    </div>
                    <p style="font-size: 0.85rem; color: #9CA3AF; margin: 6px 0 0 0;">
                        Nu sunt necesare măsuri de escaladare sau clarificări adiționale de la client. Dosarul este validat conform Cadrului RBI.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Tabelul complet al regulilor evaluate
    st.markdown("#### ⚖️ Matricea Criteriilor din Cadrul Green Bond RBI")
    table_rules = []
    for r in verdict_curent.reguli:
        rb = get_rule_badge_html(r.rezultat)
        table_rules.append(f"""
        <tr>
            <td style="font-weight: 700; color: #FAFAFA; font-family: monospace;">{r.regula_id}</td>
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
                    <th style="width: 120px;">Criteriu</th>
                    <th style="width: 140px;">Rezultat</th>
                    <th>Dovadă Audit & Fapte Identificate</th>
                    <th style="width: 170px;">Sursă Cadru RBI</th>
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
# Tab 2: Traseul Agentului (Audit Trace Stepper)
# ---------------------------------------------------------------------------

with tab_agent:
    st.markdown("#### 🤖 Jurnal de Decizie Pas cu Pas (Agent Reasoning & Tool Calls)")
    st.caption("Fiecare acțiune autonomă a agentului este auditată cu timestamp, parametri, raționament explicat și răspuns obținut.")

    for idx, pas in enumerate(verdict_curent.trace, start=1):
        pas_num = pas.get("pas", idx)
        tip = pas.get("tip", "tool")
        actiune = pas.get("actiune") or "Finalizare Verdict"
        motiv = pas.get("motiv", "Nespecificat")
        ts = pas.get("timestamp", "—")
        arg = pas.get("argumente", {})
        rezultat = pas.get("rezultat", {})

        arg_str = ", ".join([f"{k}='{v}'" for k, v in arg.items()]) if arg else "fără argumente"

        # Determinare stare rezultat
        if isinstance(rezultat, dict):
            gasit = rezultat.get("gasit")
            eroare = rezultat.get("eroare")
            if eroare:
                res_badge = f'<span class="gp-badge gp-badge-alert">Eroare: {eroare}</span>'
            elif gasit is True:
                res_badge = '<span class="gp-badge gp-badge-ok">✓ Răspuns Valid</span>'
            elif gasit is False:
                res_badge = '<span class="gp-badge gp-badge-warn">Nu a fost găsit</span>'
            else:
                res_badge = '<span class="gp-badge">Complet</span>'
        else:
            res_badge = f'<span class="gp-badge gp-badge-ok">✓ {rezultat}</span>'

        st.markdown(
            f"""
            <div class="gp-timeline-step">
                <div class="gp-timeline-bullet">{pas_num}</div>
                <div class="gp-timeline-content">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="gp-pill-tool">🛠️ {actiune}</span>
                            <span style="font-size: 0.75rem; color: #9CA3AF;">tip: {tip}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            {res_badge}
                            <span style="font-size: 0.72rem; color: #737373;">{ts}</span>
                        </div>
                    </div>
                    <div style="font-size: 0.88rem; color: #E5E7EB; margin-top: 4px;">
                        <strong style="color: #FDE047;">💡 Raționament:</strong> {motiv}
                    </div>
                    <div style="font-size: 0.78rem; color: #9CA3AF; margin-top: 4px; font-family: monospace;">
                        Parametri: {arg_str}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander(f"Inspectează JSON Pasul {pas_num} ({actiune})"):
            st.json(pas)


# ---------------------------------------------------------------------------
# Tab 3: Date Extrase & Flotă
# ---------------------------------------------------------------------------

with tab_extras:
    st.markdown("#### 📊 Date Structurate Extrase din Dosar (Contract DosarExtras)")

    if extras_curent:
        col_c1, col_c2 = st.columns([1.1, 0.9])

        with col_c1:
            st.markdown("##### Indicatori Cheie Identificați")

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
                    <td style="font-weight: 600; color: #FAFAFA;">{eticheta}</td>
                    <td style="color: #FDE047; font-weight: bold;">{v_str}</td>
                    <td style="font-size: 0.78rem; color: #9CA3AF;">{c.sursa or '—'}</td>
                    <td>
                        <span style="color: {inc_color}; font-weight: bold; font-size: 0.8rem;">{inc_pct}%</span>
                        {'<span class="gp-badge gp-badge-warn" style="font-size: 0.65rem; padding: 2px 6px;">Verificare</span>' if inc_pct < 70 else ''}
                    </td>
                </tr>
                """)

            st.markdown(
                f"""
                <table class="gp-table">
                    <thead>
                        <tr>
                            <th>Parametru</th>
                            <th>Valoare Extrasă</th>
                            <th>Sursă Document</th>
                            <th>Încredere AI</th>
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
            st.markdown("##### Chiriași & Analiză Sectorială (Excluderi GB-X1)")
            if extras_curent.chiriasi:
                rows_ch = []
                for ch in extras_curent.chiriasi:
                    is_fosil = str(ch.caen).startswith(("06", "19", "05", "09"))
                    badg = '<span class="gp-badge gp-badge-alert">Fosil / Exclus</span>' if is_fosil else '<span class="gp-badge gp-badge-ok">Eligibil</span>'
                    rows_ch.append(f"""
                    <tr>
                        <td style="font-weight: 600; color: #FAFAFA;">{ch.nume}</td>
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
                st.info("Nu există chiriași raportați în dosar (utilizare unică sau clădire proprie).")

            if extras_curent.afirmatii_client:
                st.markdown("##### Afirmații & Declarații Client")
                st.markdown(
                    "".join([f"<li style='font-size: 0.85rem; color: #D1D5DB; margin-bottom: 4px;'>{a}</li>" for a in extras_curent.afirmatii_client]),
                    unsafe_allow_html=True,
                )
    else:
        st.info("Datele DosarExtras nu sunt disponibile direct pentru acest scenariu sau dosarul rulează în mod mock offline.")


# ---------------------------------------------------------------------------
# Tab 4: Documente & Raport (Manifest Fișiere & Export)
# ---------------------------------------------------------------------------

with tab_documente:
    st.markdown("#### 📁 Documentele Dosarului & Generare Raport Final")

    col_doc_stg, col_doc_drp = st.columns([1, 1])

    with col_doc_stg:
        st.markdown("##### Fișiere Identificate în Dosar")
        folder_fizic = Path(cale_dosar_selectat) if cale_dosar_selectat else Path(f"dosare/{verdict_curent.dosar_id}")

        if folder_fizic.exists():
            fisiere = [f for f in folder_fizic.iterdir() if f.is_file() and not f.name.startswith(".")]
            rows_files = []
            for f in sorted(fisiere, key=lambda x: x.name):
                dim_kb = f.stat().st_size / 1024
                ext = f.suffix.upper().replace(".", "")
                ext_badge = '<span class="gp-pill-tool">PDF</span>' if ext == "PDF" else f'<span class="gp-pill-tool">{ext}</span>'
                rows_files.append(f"""
                <tr>
                    <td style="font-weight: 500; color: #FAFAFA;">{f.name}</td>
                    <td>{ext_badge}</td>
                    <td style="color: #9CA3AF;">{dim_kb:.1f} KB</td>
                    <td><span class="gp-badge gp-badge-ok">Procesat</span></td>
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
                            <th>Status Extracție</th>
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
            st.info("Fișierele fizice originale nu sunt prezente pe disc pentru acest scenariu demonstrativ.")

    with col_doc_drp:
        st.markdown("##### Descarcă Raportul de Audit")
        st.markdown(
            """
            <div class="gp-card">
                <div style="font-size: 0.9rem; font-weight: 600; color: #FAFAFA; margin-bottom: 6px;">
                    Raport Oficial de Conformitate GreenProof
                </div>
                <p style="font-size: 0.8rem; color: #9CA3AF; margin-bottom: 14px;">
                    Pachetul conține verdictul complet structurat conform contractului Pydantic, traseul de decizie și lista de recomandări pentru Comitetul de Sustenabilitate.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        json_export = verdict_curent.model_dump_json(indent=2)
        st.download_button(
            label="💾 Descarcă Verdict JSON (Audit Trail)",
            data=json_export,
            file_name=f"verdict_{verdict_curent.dosar_id}.json",
            mime="application/json",
            use_container_width=True,
        )

        md_report = f"""# RAPORT DE CONFORMITATE GREEN BOND — GREENPROOF
**Dosar:** {verdict_curent.dosar_id}
**Verdict Final:** {verdict_curent.verdict}
**Cale de Eligibilitate:** {verdict_curent.cale_eligibilitate or 'Niciuna'}
**Impact CO2:** {verdict_curent.impact_tco2_an or 'N/A'} tCO2/an
**Data Raportării:** {time.strftime('%Y-%m-%d %H:%M:%S')}

## Criterii Verificate:
""" + "\n".join([f"- **{r.regula_id}** [{r.rezultat}]: {r.dovada} ({r.sursa_framework})" for r in verdict_curent.reguli]) + f"""

## Acțiuni Recomandate:
""" + ("\n".join([f"- {a}" for a in verdict_curent.actiuni]) if verdict_curent.actiuni else "- Nicio acțiune necesară. Dosar conform.") + f"""

## Traseul Agentului (Audit Trail):
Total pași executați: {len(verdict_curent.trace)}
"""

        st.download_button(
            label="📄 Descarcă Raport Sumar (Markdown / Text)",
            data=md_report,
            file_name=f"raport_{verdict_curent.dosar_id}.md",
            mime="text/markdown",
            use_container_width=True,
        )
