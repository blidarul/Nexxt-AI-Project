# Green Proof: interfața de demo

O singură pagină (HTML/CSS/JS în `ui/static/`, fără build) peste un server FastAPI (`ui/server.py`).
Interfața nu decide eligibilitatea: verdictul vine din `agent.orchestrator.proceseaza_dosar`, datele extrase
din `dosare/<id>/_extras`, iar legătura regulă -> câmpuri din `rules/cerinte_dosar.yaml`.

```bash
python -m ui                      # pornește serverul pe http://127.0.0.1:8000/ și deschide browserul
python -m ui --fara-browser --port 8765
python -m ui --mod-extractie mock # extras_mock.json în loc de datele extrase din PDF-uri (implicit: real)
```

## Pagina

Trei coloane: filtrele (cu numărul de dosare) | lista dosarelor (apare după alegerea unui filtru și se strânge
după selectarea unui dosar) | dosarul, parcurs în 3 pași:
1. **Fișiere**: documentele dosarului și cele lipsă; un clic deschide fișierul în panou (✕ sau Esc îl închide).
2. **Raport** („Generează raportul” rulează agentul): recomandarea, motivul, impactul și trei secțiuni pliabile,
   „Reguli verificate”, „Date extrase”, „Pașii agentului”. Fiecare regulă se desfășoară cu dovada completă și
   trimiterea la pagina din document.
3. **Decizie** („Ia decizia”): Aprobă / Respinge / Intervenție umană; comentariul apare doar unde e obligatoriu,
   iar o decizie diferită de recomandarea agentului se confirmă.

Resetarea deciziilor și modurile de rulare sunt în meniul ⋯ din stânga jos. Stilul: „achromatic ledger” din
skill-ul `design-taste-frontend`, în negru + galben (galben doar pe butonul principal al pasului curent);
fonturile Geist sunt locale (`static/fonts`, licență OFL), deci pagina merge și fără internet.

## API

| Metodă | Cale | Ce face |
|---|---|---|
| GET | `/api/stare` | numele produsului și modurile (`MOD_EXTRACTIE`, `MOD_TOOLS`, `MOD_AGENT`) |
| GET | `/api/dosare` | dosarele din `dosare/`, cu sumarul, verdictul salvat și statusul deciziei |
| GET | `/api/dosare/{id}` | documentele (cu clasificarea), câmpurile extrase cu sursa (fișier, pagină), lipsurile, rezultatul salvat, decizia |
| POST | `/api/dosare/{id}/evaluare` | rulează agentul și salvează rezultatul; dacă agentul nu poate rula, întoarce ultimul rezultat salvat (`din_salvare: true`, `salvat_la`) |
| GET | `/api/dosare/{id}/rezultat` | ultimul rezultat salvat (404 dacă nu există) |
| GET | `/api/dosare/{id}/fisiere/{cale}` | PDF / JSON din folderul dosarului, pentru previzualizare (`inline`) |
| GET | `/api/decizii` | istoricul deciziilor (ultima pe dosar e cea curentă) |
| POST | `/api/dosare/{id}/decizie` | `{decizie: aprobat\|respins\|interventie, comentariu, confirmat}` |
| DELETE | `/api/decizii` | reset: șterge deciziile (rezultatele agentului rămân) |

Rezultatul conține `recomandare` (verdictul tradus în decizia recomandată: ELIGIBIL / ELIGIBIL_CU_MONITORIZARE ->
aprobat, NEELIGIBIL -> respins, EXCEPTIE_ESCALADARE_COMITET -> intervenție) și `dovezi`: pentru fiecare regulă,
câmpurile care o susțin, cu fișierul și pagina din care au fost extrase.

Reguli pentru decizie (verificate pe server):
- se poate decide doar după ce soluția agentului a fost deschisă (există un rezultat salvat), altfel 409;
- „Respinge” și „Intervenție umană” cer comentariu, altfel 422;
- o decizie diferită de recomandarea agentului cere `confirmat: true` (altfel 409 cu `necesita_confirmare`)
  și se înregistrează cu `difera_de_agent: true`.

Fișierele se servesc doar din folderul dosarului cerut: căile cu `../`, căile absolute, folderele interne
și fișierele de evaluare (`expected.json`, `extras_mock.json`) primesc 404.

## Date

- `ui/data/rezultate/<id>.json`: ultimul rezultat al agentului pentru fiecare dosar (inclus în git, ca demo-ul
  să meargă și fără agent); se rescrie la fiecare evaluare.
- `ui/data/decizii.json`: deciziile analistului (nu intră în git).

Teste: `python -m pytest ui -q`.
