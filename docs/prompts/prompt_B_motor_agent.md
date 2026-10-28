# Persoana B, ramura `feat/motor-agent`: motorul de reguli + agentul + evaluarea

## Context
Proiect: agent care verifică dacă un credit aprobat poate intra în portofoliul verde RBI (*RBI Sustainability Bond Framework*).
Citește întâi: `docs/PLAN_ECHIPA.md` (cine ce face, interfețele, regulile git), `docs/VERIFICARI.md`,
`docs/STRUCTURA_DOSAR.md`, `rules/*.yaml`, `reference/*.yaml`, `contracts.py`, `registry.py`.

**Folderele tale:** `engine/`, `agent/`, `eval/`, `rules/`, `reference/`.
**NU modifica:** `extraction/`, `tools/`, `ui/`, `dosare/`, `contracts.py`, `registry.py`, `config.py`, `docs/`.
Dacă ai nevoie de o schimbare acolo, **oprește-te și spune-mi**.

**Principiul de bază: verdictul îl dă CODUL (din reguli YAML), nu LLM-ul. LLM-ul decide doar drumul:**
ce verifică, în ce ordine, ce cale alternativă încearcă, când cere date sau escaladează.

Lucrează pe 4 părți, **cu oprire și rezumat după fiecare.** Commit după fiecare pas care merge.

---

## Partea 0: audit (fără cod)
Compară ce există în `engine/` și `agent/` cu fluxul din `docs/STRUCTURA_DOSAR.md`, secțiunea 6, și cu
`docs/VERIFICARI.md`. Fă un tabel cu statusul fiecărui element (există / parțial / lipsește):
- categoriile din `rules/` evaluate: green_buildings, renewable_energy, energy_efficiency, clean_transportation,
  pollution_prevention, circular_economy, conditii_generale;
- tipurile de reguli suportate: `prag`, `lista`, `lista_cu_ordine`, `da_nu`, `excludere`, `oricare`, `toate`,
  `prag_dependent_de_data`, `aplica_daca`, `daca_lipseste`, `doar_pentru`;
- plauzibilitatea (`reference/plauzibilitate.yaml`, cu severitate);
- impactul pe categorii (`reference/metodologie_impact.yaml`);
- tools: `stabileste_categoria`, `verifica_completitudine`, `evalueaza_categoria`, `verifica_plauzibilitate`,
  `calculeaza_impact`, `cere_date_client`, `escaladeaza`;
- planificatorul LLM (Featherless) și planificatorul scriptat;
- `eval/run_eval.py` pe toate dosarele.

**Oprește-te cu tabelul.** Nu scrie cod până nu confirm.

---

## Partea 1: motorul de reguli generic (`engine/`)

1. **Un singur evaluator** care citește **orice** fișier din `rules/` și suportă toate tipurile de mai sus.
   Fără cod separat per categorie: o regulă nouă în YAML trebuie să meargă fără modificări de cod.
   Valorile vin din `DosarExtras` (câmpurile vechi + `indicatori`), din rezultatele tool-urilor și din câmpurile calculate.
2. **Câmpurile calculate** (le calculează motorul, nu extractorul): `luni_de_la_aprobare`, `reducere_ped_pct`,
   `imbunatatire_eficienta_pct`, `densitate_putere_w_m2` (când lipsește, din putere ÷ suprafață), `factor_capacitate`,
   `ped_fata_de_nzeb`. Fiecare păstrează formula în dovadă.
3. **Câmpurile da/nu** se compară cu `True`/`False` (Python), nu cu 1/0. `Camp.valoare` poate fi acum `bool`.
4. **Liste (vehicule):** regula se aplică **pe fiecare element**. Rezultatul regulii conține lista elementelor care
   trec și a celor care pică. Dacă doar o parte trec: rezultatul e `NU` pentru elementele respective, verdictul
   rămâne determinat de restul, iar în `impact_detalii["pondere_eligibila"]` + `actiuni` se scrie partea eligibilă
   (pro-rata, Framework p. 19).
5. **Grandfathering (G-05):** pragurile dependente de dată se evaluează la `data_marcare_verde`, iar dacă lipsește,
   la `data_aprobare` + SEMNAL informativ.
6. **`daca_lipseste`:** `NEEVALUABIL` → agentul cere date; nu se presupune niciodată că dosarul trece.
7. **Plauzibilitatea:** severitate `blocant` → SEMNAL care duce la EXCEPȚIE; `informativ` → doar acțiune.
8. **Impactul** pe fiecare categorie, după `reference/metodologie_impact.yaml`, cu pașii calculului păstrați.
   Factorul de emisie vine din tool-ul `factor_emisie_tara` (făcut de colegul A). Până există, folosește valoarea
   de rezervă din `reference/`, marcată `proxy`.
9. **`decide_verdict`:** condiție generală NU → NEELIGIBIL; SEMNAL blocant sau escaladare → EXCEPTIE_ESCALADARE_COMITET;
   regulă obligatorie NU → NEELIGIBIL; o cale OK → ELIGIBIL; o cale OK_CONDITIONAT → ELIGIBIL_CU_MONITORIZARE;
   NEEVALUABIL pe toate căile → EXCEPȚIE, cu cererea de date.

Teste: câte un test pentru fiecare tip de regulă + cazurile din `docs/VERIFICARI.md`, secțiunea 6.
**Oprește-te cu rezumatul.**

---

## Partea 2: agentul (`agent/`)

1. **Tools noi** (cu `@tool` din `registry.py`; întorc mereu `ToolResult`):
   - `stabileste_categoria`: folosește `extras.categorie`. Dacă `raport_extractie.categorie_candidati` are 2 candidați
     cu încredere sub 0.7, agentul alege cu motivare **sau** escaladează. Nu reclasifică de la zero.
   - `verifica_completitudine`: din `StareDosar.raport_extractie` (`documente_lipsa`, `campuri_lipsa`) și
     `rules/cerinte_dosar.yaml` → lista de lipsuri, fiecare cu documentul și regula pentru care e necesar.
   - `evalueaza_categoria(categorie)`, `verifica_plauzibilitate`, `calculeaza_impact(categorie)`: apelează motorul.
2. **Fluxul** (în promptul de sistem): condiții generale → categoria → completitudine (lipsește ceva obligatoriu →
   `cere_date_client`) → regulile categoriei (căi alternative) → excluderi → plauzibilitate → impact → final.
3. **`PlanificatorLLM` pe Featherless:** biblioteca `openai`, `base_url` și cheia din `.env` (aceleași variabile ca
   extractorul: `LLM_BASE_URL`, `LLM_API_KEY` sau `FEATHERLESS_API_KEY`, `LLM_MODEL_TEXT`). Model cu tool calling
   nativ: `Qwen/Qwen3-32B`. Tools în format OpenAI (`"type": "function"`), generate din `registry.schema_pentru_llm()`.
   Elimină blocurile `<think>...</think>`. Limită de pași. La eroare de API sau la un răspuns invalid: reîncercare,
   apoi **trecere automată la planificatorul scriptat**, notată în trace.
4. **Trace-ul:** fiecare pas are acțiunea, argumentele, **motivul** (textul LLM-ului) și rezultatul rezumat.
   Asta se afișează în UI.
5. Agentul primește `raport_extractie` în `StareDosar` și îl folosește (conflicte, încredere mică → reverificare
   sau cerere de date).

**Oprește-te cu rezumatul și trace-ul complet pe un dosar de transport și unul de clădire.**

---

## Partea 3: evaluarea (`eval/`)

1. **Dosare de reguli fără PDF-uri** în `eval/dosare_reguli/<caz>/`: doar `extras_mock.json` + `raport_extractie.json`
   (opțional) + `expected.json`. Câte unul pentru fiecare caz din `docs/VERIFICARI.md`, secțiunea 6, plus câte un caz
   ELIGIBIL pentru fiecare categorie. Așa testezi motorul fără să depinzi de extractor.
2. `python -m eval.run_eval` rulează pe `dosare/` (cu `_extras` reale) **și** pe `eval/dosare_reguli/`, cu tabelul
   verdict așteptat / obținut / cale / CO2 și scorul total.
3. Rulare de două ori: cu planificatorul scriptat (determinist) și cu cel LLM. Raportează ambele scoruri.

**Oprește-te cu rezumatul.**

---

## La final
- `git fetch origin && git merge origin/main`, apoi `python -m pytest -q` trece.
- `git diff --stat origin/main`: modificări doar în folderele tale.
- **Nu face push.** Îl face colegul tău după verificare.
