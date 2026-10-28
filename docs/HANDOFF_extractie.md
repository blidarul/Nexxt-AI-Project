# Predare de lucru: Extractorul (modulul A). Continuă și termină Etapa 3

Ești un agent nou pe acest proiect. Documentul ăsta conține tot ce îți trebuie: contextul, starea curentă,
ce a rămas de făcut, regulile și criteriile de terminare. **Citește-l integral înainte să faci ceva.**

---

## 1. Proiectul în 5 rânduri

Agent AI pentru Raiffeisen Bank: verifică dacă un credit deja aprobat poate intra în portofoliul de credite verzi
al băncii, conform *RBI Sustainability Bond Framework*. Fluxul: **dosar (PDF-uri) → [A] Extractor → `DosarExtras` →
[D] agent orchestrator (LLM cu tools) → [C] motor de reguli → verdict.** Tu lucrezi **doar la A, Extractorul**:
transformă orice PDF-uri dintr-un dosar în date structurate, curățate, cu sursă și încredere, pe care se bazează restul.

## 2. Ce există deja (nu rescrie, extinde)

| Componentă | Fișiere | Stare |
|---|---|---|
| Etapa 1: citire brută | `extraction/pdf_text.py`, `extraction/extrage_brut.py` | ✅ PDF → `dosare/<d>/_brut/*.json` (text pe pagini + tabele) |
| Etapa 2: extracție structurată (clădiri) | `extraction/llm_client.py`, `normalizare.py`, `campuri.yaml`, `clasificare.py`, `cautare.py`, `extragere_campuri.py`, `verificare.py`, `extrage_structurat.py`, `extractor.py`, `compara.py` | ✅ merge pe cele 4 dosare de clădiri din `dosare/` |
| LLM | Featherless (API compatibil OpenAI), configurat din `.env`: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_TEXT`, `LLM_MODEL_VISION`, `LLM_MAX_PARALELE` | ✅ cache în `extraction/.cache/`, retry la 429, eliminare `<think>` |
| Contract | `contracts.py`: `DosarExtras` are acum și `categorie`, `subcategorie`, `indicatori: dict[str, Camp]` | ✅ |
| Reguli (sursa de adevăr) | `rules/cerinte_dosar.yaml`, `rules/*.yaml` (6 categorii + condiții generale), `reference/*.yaml`, `docs/STRUCTURA_DOSAR.md`, `docs/VERIFICARI.md`, `docs/exemplu_dosar_flota.json` | ✅ |

## 3. Unde s-a oprit agentul anterior (VERIFICĂ ÎNTÂI)

Agentul anterior a pornit **Faza 1** a Etapei 3 și a fost întrerupt în timp ce lucra. Concluziile lui:
- niciun cod din `extraction/` nu citea `rules/green_buildings.yaml`, deci nu e nimic de adaptat;
- `campuri.yaml` avea 14 câmpuri (doar clădiri); lipseau **58** câmpuri cerute de `cerinte_dosar.yaml`;
- adăugarea de câmpuri în `campuri.yaml` e aditivă și nu strică nimic.

**Nu știm cât din Faza 1 a apucat să scrie.** Primul tău pas e un audit:
1. `git status` și `git diff --stat`: ce fișiere s-au modificat sau creat față de ultimul commit;
2. câte câmpuri are acum `extraction/campuri.yaml` și care câmpuri din `rules/cerinte_dosar.yaml` lipsesc din el;
3. există `extraction/verifica_catalog.py`? există teste noi? `python -m pytest extraction -q` trece?
4. `normalizare.py` are deja conversii de unități (kWh/100 km, kW, g/mi)?

Arată-mi rezultatul auditului și **ce păstrezi / ce reiei**. Abia apoi continui.

## 4. Decizie importantă: ce câmpuri extrage extractorul

În `rules/*.yaml` apar ~105 nume de câmpuri, mai multe decât în `cerinte_dosar.yaml`. **Nu le extrage pe toate.**
Câmpurile din reguli sunt de trei feluri:

| Fel | Exemple | Cine le produce |
|---|---|---|
| **Extrase din documente** | `capacitate_mw`, `emisii_wltp_gco2_km`, `pue_anualizat`, `vehicule` | **Extractorul (tu)**: exact cele din `cerinte_dosar.yaml` |
| **Calculate** | `luni_de_la_aprobare`, `reducere_ped_pct` (vezi `calcul_ajutator` în reguli), `factor_capacitate` | Motorul de reguli (C), din câmpurile extrase |
| **Din registre externe** | `caen_imprumutat` (ANAF), rating BREEAM din registru, emisii din registrul EEA | Tools (B) |

Deci:
- `campuri.yaml` trebuie să conțină **toate** câmpurile din `cerinte_dosar.yaml`. Testul de sincronizare **pică** dacă lipsește vreunul.
- Pentru câmpurile care apar în `rules/*.yaml` dar nu în `cerinte_dosar.yaml`, testul doar **afișează o listă informativă** (nu pică). Nu le adăuga în catalog.
- Excepție: dacă un câmp calculat are nevoie de intrări care nu sunt în `cerinte_dosar.yaml` (de ex. `reducere_ped_pct` are nevoie de `ped_inainte_kwh_m2` și `ped_dupa_kwh_m2`, care sunt acolo), verifică că intrările există. Dacă lipsește o intrare, spune-mi, nu o adăuga singur în `rules/`.

## 5. Ce mai e de făcut

### Faza 1: catalog, sincronizare, unități
1. **`campuri.yaml` complet** pentru toate câmpurile din `cerinte_dosar.yaml`. Pentru fiecare: `descriere`, `tip`
   (numar | procent | data | text | da_nu | cod_caen | clasa_energetica | lista | categorie), `unitate`,
   `cuvinte_cheie` în română și engleză (cu și fără diacritice), `documente_probabile`, `validare`.
   Pentru liste: coloanele + sinonimele antetelor. Exemplu pentru `vehicule`: marca/make/brand, model,
   combustibil/fuel, bucati/qty/buc., emisii_wltp_gco2_km/CO2 g/km, consum_kwh_km/consum kWh/100km/energy consumption,
   distanta_anuala_km/km/an/annual mileage, vin/nr. înmatriculare, data_marcare_verde, utilizare.
2. **`extraction/verifica_catalog.py`** + test pytest (regulile de la secțiunea 4).
3. **Normalizarea unităților** în `normalizare.py`, cu teste:
   `kWh/100 km`→`kWh/km` (÷100); `Wh/km`→`kWh/km` (÷1000); `kW`→`MW` (÷1000); `GW`→`MW` (×1000);
   `kWh`/`GWh`→`MWh`; `g/mi`→`g/km` (÷1.609); PUE `1,38`→`1.38`; câmpurile `*_pct` și `pondere_*` → între 0 și 1.
   Unitatea originală se păstrează pentru raport.

**Oprește-te după Faza 1 cu un rezumat.**

### Faza 2: clasificare, categorie, extragere țintită
1. **Clasificare extinsă a documentelor** (din conținut, nu din nume), cu tipurile:
   `cerere_finantare`, `decizie_aprobare`, `certificat_constatator`, `beneficiar_real`, `contract_credit`,
   `certificat_sustenabilitate`, `certificat_energetic`, `audit_energetic`, `contract_inchiriere`, `extras_carte_funciara`,
   `deviz_lucrari`, `fisa_tehnica`, `studiu_fezabilitate`, `autorizatie`, `studiu_impact_mediu`, `analiza_ciclu_viata`,
   `raport_pue`, `lista_vehicule`, `certificat_conformitate_vehicul`, `declaratie_utilizare`, `declaratie_furnizor`,
   `factura_energie`, `alt_document`. Plus un fișier YAML de mapare tip → ID-uri din `cerinte_dosar.yaml`
   (ex. `certificat_conformitate_vehicul` → `CT-D2`).
2. **Stabilirea categoriei proiectului** (`extraction/categorie.py`): LLM-ul alege `categorie` și `subcategorie` **doar**
   din valorile permise citite din `rules/*.yaml` (cheile `subcategorii`, `tehnologii`, `tipuri`, `tipuri_proiect`),
   cu citat și încredere. Indicii deterministe: `lista_vehicule` → transport, `raport_pue` → data center etc.
   Sub 0.7 încredere: păstrează 2 candidați, extrage pentru amândoi, scrie-i în raport.
3. **Extragere țintită**: câmpurile `comun` + cele ale categoriei, filtrate după `doar_pentru`. Căutarea în trepte și
   verificarea citatelor din Etapa 2 rămân. Câmpurile noi merg în `DosarExtras.indicatori`, cu cheia **exact**
   egală cu numele din `cerinte_dosar.yaml`. Câmpurile vechi de clădiri se completează în continuare.
4. **Liste din tabele** (`vehicule`, `chiriasi`): întâi parsare deterministă după sinonimele antetelor; LLM doar dacă nu
   există un tabel recognoscibil. Tabelele care continuă pe mai multe pagini se unesc. Rândurile cu același model se
   agregă (`bucati` se adună). Dacă emisiile diferă între listă și CoC, câștigă CoC, iar conflictul ajunge în raport.
5. **Valori da/nu** din text: citat obligatoriu, atenție la negații. Dacă nu e explicit: `null`, nu `false`.

Testează Faza 2 întâi pe `fx_transport_flota` și `fx_data_center` (vezi Faza 3). **Oprește-te cu rezumat.**

### Faza 3: fixtures, OCR, raport de lipsuri, non-regresie
1. **`extraction/test_fixtures/genereaza_fixtures.py`**: PDF-uri sintetice marcate „DOCUMENT SINTETIC”
   (poți refolosi funcțiile din `genereaza_dosare.py`), fiecare cu `expected_campuri.json`:
   | Fixture | Conținut | Testează |
   |---|---|---|
   | `fx_transport_flota` | cerere + listă de vehicule (tabel pe 2 pagini, consum în kWh/100 km) + 2 CoC + declarație de utilizare | categoria, tabel pe 2 pagini, agregare, unități |
   | `fx_hidro_2022` | cerere + fezabilitate (putere în kW, suprafață lac) + autorizație + EIA | kW→MW, an punere în funcțiune, EIA |
   | `fx_data_center` | cerere + raport PUE în **engleză** („annualised PUE: 1,38”) | limbă, virgulă zecimală |
   | `fx_renovare` | cerere + EPC înainte + EPC după + deviz | două documente de același tip |
   | `fx_aluminiu` | cerere + declarație furnizor | procente, tCO2e/t |
   | `fx_scanat` | CoC ca **imagine** (pagină fără text) | OCR (`pypdfium2` + `LLM_MODEL_VISION`) |
   | `fx_incomplet` | transport **fără** CoC | `CT-D2` în `documente_lipsa`; emisii `null`, nu inventate |
   | `fx_ambiguu` | „modernizarea iluminatului și panouri fotovoltaice pe hala de producție” | 2 categorii candidate |
2. **OCR** pentru pagini fără text și pentru imagini `.jpg/.png` din dosar.
3. **Raportul** (`_extras/raport_extractie.json`) adaugă: `categorie_candidati`, `documente_gasite` (tip + ID),
   `documente_lipsa` (ID-uri obligatorii negăsite), `campuri_lipsa` (cu documentul așteptat și regula pentru care
   e necesar), `conversii_unitati`.
4. **Non-regresie**: rezultatul pe cele 4 dosare din `dosare/` rămâne identic (`python -m extraction.compara`).

## 6. Reguli stricte

- Cod **doar în `extraction/`** (și eventual `requirements.txt`).
- **NU modifica**: `contracts.py`, `rules/`, `reference/`, `docs/`, `agent/`, `engine/`, `tools/`, `eval/`,
  fișierele existente din `dosare/` (în afară de `_brut/` și `_extras/`).
- **Nicio listă de câmpuri, documente sau categorii scrisă de mână în cod.** Totul se citește din `rules/*.yaml`
  și `extraction/campuri.yaml`.
- Fără chei API în cod. Totul din `.env`.
- Dacă ai nevoie de o modificare în afara `extraction/` (contract, reguli), **oprește-te și spune-mi**.
- **Nu inventa valori.** Dacă nu e în document: `null` + intrare în `campuri_lipsa`.

## 7. Când e gata (criteriile de acceptare)

1. `python -m extraction.compara` pe cele 4 dosare: același rezultat ca înainte.
2. Fiecare fixture: categoria, subcategoria și câmpurile din `expected_campuri.json` sunt corecte.
3. `fx_incomplet`: lipsurile sunt corecte, nicio valoare inventată.
4. `fx_ambiguu`: 2 candidați, cu încredere sub 0.7.
5. `python -m pytest extraction -q` trece (catalog, unități, normalizare, citate).
6. A doua rulare: 0 apeluri LLM reale (totul din cache).
7. `git status`: modificări doar în `extraction/` (și eventual `requirements.txt`).

## 8. Cum lucrezi

1. Citește documentul ăsta, `rules/cerinte_dosar.yaml`, `docs/STRUCTURA_DOSAR.md` și codul existent din `extraction/`.
2. Fă auditul de la secțiunea 3 și arată-mi-l.
3. Fazele 1 → 2 → 3, **cu oprire și rezumat după fiecare.**
4. La final: tabel cu fiecare fixture (categorie detectată / așteptată, câmpuri corecte / total), un exemplu de
   `raport_extractie.json` și lista fișierelor create sau modificate.
