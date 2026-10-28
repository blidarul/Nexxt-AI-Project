# Persoana A, ramura `feat/extractor-tools-ui`: extractor final + tools + interfața de demo

## Context
Proiect: agent care verifică dacă un credit aprobat poate intra în portofoliul verde RBI.
Citește întâi: `docs/PLAN_ECHIPA.md` (cine ce face, interfețele, regulile git), `docs/STRUCTURA_DOSAR.md`,
`docs/VERIFICARI.md`, `contracts.py`, `registry.py`.

**Folderele tale:** `extraction/`, `tools/`, `ui/` și `dosare/*/_brut/`, `dosare/*/_extras/`.
**NU modifica:** `engine/`, `agent/`, `eval/`, `rules/`, `reference/`, `contracts.py`, `registry.py`, `config.py`, `docs/`.
Dacă ai nevoie de o schimbare acolo, **oprește-te și spune-mi**: o cer colegului sau facem un PR comun.

Lucrează pe 3 părți, **cu oprire și rezumat după fiecare.** Commit după fiecare pas care merge.

---

## Partea 1: extractorul, reparațiile rămase

1. **Dosarele `dosar3`–`dosar5` cu extractorul real:** rulează cu `force_reload=True` și compară cu `extras_mock.json`.
   Fiecare diferență trebuie explicată (cauza) și reparată în extractor, nu în mock. Excepția: când mock-ul e greșit.
   Atunci arată-mi dovada din PDF și aștept decizia mea. După aceea, reconstruiește snapshot-ul de non-regresie
   din rezultatele reale.
2. **Fallback-ul de chiriași** se bazează pe **conținut** (tipul `contract_inchiriere` dat de clasificare), nu pe numele
   fișierului. Un chiriaș fără cod CAEN **nu** primește `caen=""`: rămâne în listă cu `caen: null` și apare în
   `campuri_lipsa` (motiv: `caen_lipsa_chirias`), ca regula GB-X1 să știe că nu poate verifica acel chiriaș.
3. **Tipuri noi în `tipuri_documente.yaml`**, cu cuvinte cheie RO/EN: `raspuns_anaf`, `nota_tehnica`,
   `raport_taxonomie_ue`, `raport_etanseitate`, `contract_ppa_verde`, `declaratie_mediu_produs` (EPD).
   Mapează-le la ID-urile din `rules/cerinte_dosar.yaml` unde se potrivesc. Unde nu există ID, lasă lista goală
   (sunt documente utile, dar necerute).
4. **Ghicirea tipului din numele fișierului** (`extrage_brut.py`) rămâne doar ca **indiciu**. În raport scrie ambele
   (`tip_din_nume`, `tip_din_continut`); decide conținutul. Adaugă un test cu un fișier cu nume înșelător
   (de ex. un CPE salvat ca `scan_0034.pdf`).
5. **`data_aprobare`:** căutarea rămâne în D-02, D-05 **și** cererea de finanțare, dar doar cu cuvinte cheie precise
   („data aprobării”, „aprobat la”, „approval date”, „data deciziei”). Fără cuvântul generic „data”.
   Adaugă un test: o cerere care conține „Data cererii: …” și o declarație datată nu trebuie să producă `data_aprobare`.
6. **`fx_ambiguu`:** testul trece dacă există **cel puțin 2 candidați**, încrederea maximă e **sub 0.7** și
   `energy_efficiency` sau `renewable_energy` e printre candidați. Nu forța o pereche exactă. Scopul fixture-ului
   e detectarea ambiguității.

**Oprește-te cu rezumatul** (`compara` pe toate dosarele, fixture-urile, `pytest`).

---

## Partea 2: tools noi (`tools/`)

Interfețele sunt fixate în `docs/PLAN_ECHIPA.md`. **Nu le schimba:** agentul colegului le folosește deja.

Întâi un **audit** al tool-urilor existente (`verifica_firma`, `cauta_certificat`): fiecare întoarce **mereu**
`ToolResult` (și la date proaste, și la erori), are mod offline și mod online. Raportează ce lipsește și repară.

1. **`cauta_emisii_vehicul(marca, model)`**
   - **Offline:** citește `tools/data/emisii_vehicule.csv`. Conține modelele din fixture-uri (sintetice, marcate ca
     atare în coloana `sursa`) și un eșantion mic de modele reale din datele EEA.
   - **Script `tools/data/descarca_eea.py`:** descarcă datele EEA „CO2 emissions from new passenger cars”, păstrează
     coloanele marcă, denumire comercială, combustibil și emisii WLTP, agregă pe (marcă, model) cu mediana, și scrie
     CSV-ul. Dacă descărcarea nu merge (rețea), scriptul dă o eroare clară. **Nu inventa valori „reale”.**
   - Potrivirea numelui de model e tolerantă (majuscule, spații, cratime). Dacă există mai multe potriviri,
     întoarce-le pe toate în `date["candidati"]`.
   - Modelul negăsit: `gasit=False` și `eroare` explicită.
2. **`factor_emisie_tara(tara, an)`**
   - **Offline:** `tools/data/intensitate_carbon.csv` (țară, an, gCO2e/kWh).
   - **Script `tools/data/descarca_ember.py`:** descarcă CSV-ul Our World in Data
     (`https://ourworldindata.org/grapher/carbon-intensity-electricity.csv`) și păstrează țările din Anexa B a Framework-ului.
   - Fără an: ultimul an disponibil. Numele țării se acceptă în română și engleză (România / Romania).
   - Întoarce `kgco2_kwh` (= gCO2e/kWh ÷ 1000) și `tip: "proxy"` (RBI folosește Enerdata, care e plătit).
3. Ambele se înregistrează cu `@tool` din `registry.py` și au teste de contract: `ToolResult` la orice intrare,
   inclusiv argumente greșite.

**Oprește-te cu rezumatul.**

---

## Partea 3: interfața de demo (`ui/app.py`, Streamlit)

Publicul e **juriul** (Raiffeisen). Trebuie să se vadă clar că e un **agent care decide pașii**, nu un `if/else`.

1. **Stânga:** lista dosarelor (din `dosare/` + fixture-uri) și un buton „Analizează”.
2. **Secțiunea 1, documentele:** fiecare fișier cu tipul detectat; documentele lipsă evidențiate (din raport).
3. **Secțiunea 2, datele extrase:** tabel câmp / valoare / sursă (fișier, pagină) / încredere (sub 0.7 evidențiată);
   conflictele și citatele reconstituite marcate. Flota ca tabel separat.
4. **Secțiunea 3, traseul agentului:** fiecare pas ca un card: acțiune, **de ce** (motivul), rezultat, sursă.
5. **Secțiunea 4, verdictul:** mare, colorat (verde / roșu / galben / albastru). Regulile cu ID, rezultat, dovadă și
   pagina din Framework. Impactul CO2 cu pașii calculului. Acțiunile (cereri către client, escaladare).
6. **Modul demo:** dacă agentul colegului nu e încă integrat, UI-ul citește un `Verdict` salvat în
   `ui/exemple/<dosar>.json`. Scrie 3 exemple de mână, conform `contracts.Verdict`: unul ELIGIBIL, unul EXCEPȚIE,
   unul NEELIGIBIL. După integrare, butonul cheamă `agent.orchestrator.proceseaza_dosar(folder)`.
7. Rulează offline (fără internet), cu cache.

Rulare: `streamlit run ui/app.py`. Adaugă `streamlit` în `requirements.txt` și spune-mi (fișierul e comun).

**Oprește-te cu rezumatul și cu 3 capturi de ecran** (sau descrierea fiecărei secțiuni).

---

## La final
- `git fetch origin && git merge origin/main`, apoi `python -m pytest -q` trece.
- `git diff --stat origin/main`: modificări doar în folderele tale (+ `requirements.txt`, anunțat).
- **Nu face push.** Îl fac eu după verificare.
