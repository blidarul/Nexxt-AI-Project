# GreenProof — Interfața de Demo și Audit (Streamlit)

Interfață modernă cu temă dark (GreenProof), inspirată din designul Lovable, pentru auditul dosarelor de credit conform Cadrului Green Bond RBI 2025.

## Funcționalități Cheie
- **Branding GreenProof & Paletă Dark**: Culori contrastante (`#121212`, `#1A1A1A`, `#FDE047` galben Raiffeisen, badge-uri semantice).
- **Selector Flexibil de Dosare**:
  - Dosare reale din bancă (`dosare/` cu metadate din `dosare/index.csv`).
  - Scenarii demonstrative offline (`ui/exemple/dosar_eligibil.json`, `dosar_exceptie.json`, `dosar_neeligibil.json`).
  - Drag-and-drop pentru încărcarea de arhive `.zip` sau fișiere `.pdf`.
- **Hero Banner & KPI-uri**: Dosar ID, CUI, Verdict mare colorat, Impact CO₂, Reguli evaluate, Pași agent.
- **Cele 4 Tab-uri de Audit**:
  1. `⚖️ Verdict & Reguli RBI`: Calcul impact CO₂ cu formulă și pași detaliați, acțiuni de escaladare / întrebări client, tabel criterii cu dovadă și pagină din cadru.
  2. `🤖 Traseul Agentului (Audit)`: Timeline vizual pas cu pas (stepper) cu tool-ul apelat, raționamentul agentului (*De ce*), argumente, răspuns și JSON tehnic expandabil.
  3. `📊 Date Extrase & Flotă`: Indicatori extrași din dosar cu scor de încredere (evidențiere sub 70%) și tabel chiriași cu filtrare pe coduri CAEN excluse (GB-X1).
  4. `📁 Documente & Raport`: Manifest fișiere dosar și butoane de export raport (JSON și Markdown).
- **Evaluare în Masă (Batch Runner)**: Buton pentru rularea evaluării pe tot portofoliul de dosare cu bară de progres și tabel sinoptic.

## Lansare Aplicație
```bash
streamlit run ui/app.py
```
