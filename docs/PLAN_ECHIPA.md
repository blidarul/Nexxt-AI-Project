# Planul de lucru pe 2 ramuri (2 persoane)

## Regula care face merge-ul să meargă fără probleme

**Fiecare lucrează în ALTE foldere.** Git face conflict doar când doi oameni schimbă aceleași linii din același fișier.
Dacă folderele nu se suprapun, merge-ul e automat.

| Persoana | Ramura | Foldere proprii (doar el le modifică) |
|---|---|---|
| **Persoana A (Alex)** | `feat/extractor-tools-ui` | `extraction/`, `tools/`, `ui/`, `dosare/*/_brut/`, `dosare/*/_extras/` |
| **Persoana B (colegul)** | `feat/motor-agent` | `engine/`, `agent/`, `eval/`, `rules/`, `reference/` |
| **Comune: înghețate** | doar prin Etapa 0 sau un PR mic, anunțat | `contracts.py`, `registry.py`, `config.py`, `requirements.txt`, `.gitignore`, `.gitattributes`, `docs/` |

Dacă unul are nevoie de o schimbare în folderul celuilalt: **nu o face**, îi scrie ce îi trebuie.
Dacă e nevoie de o schimbare comună (de ex. în `contracts.py`): un PR mic separat în `main`, anunțat, iar celălalt face pull imediat.

## Cum comunică cele două părți (fără să depindă una de alta)

```
dosar (PDF) ──► [A] extractor ──► dosare/<d>/_extras/dosar_extras.json   (DosarExtras)
                                  dosare/<d>/_extras/raport_extractie.json (lipsuri, conflicte, candidați)
                                              │
                                              ▼
              [B] agent + motor de reguli ──► Verdict  ──► [A] UI (afișare)
                       ▲
                       └── tools (A): verifica_firma, cauta_certificat, cauta_emisii_vehicul, factor_emisie_tara
```

- **B nu așteaptă după A:** lucrează pe fișierele `_extras/` care există deja în repo și pe `extras_mock.json`.
- **A nu așteaptă după B:** tools-urile se testează singure (`ToolResult`), iar UI-ul se face pe un `Verdict` salvat în JSON.
- Legătura e făcută de contracte (`contracts.py`) și de registrul de tools (`registry.py`), care nu se schimbă.

## Interfețele stabilite de acum (ca să nu așteptați unul după altul)

Tools noi pe care le face A și le cheamă agentul lui B. **Numele și formatul nu se mai schimbă:**

| Tool | Intrare | `ToolResult.date` |
|---|---|---|
| `cauta_emisii_vehicul` | `marca: str`, `model: str` | `{"emisii_wltp_gco2_km": float, "combustibil": str, "an_date": int}` |
| `factor_emisie_tara` | `tara: str`, `an: int \| None` | `{"kgco2_kwh": float, "an": int, "tip": "proxy"}` |

Până le termină A, B folosește valori de rezervă din `reference/` (marcate `proxy`).

Fișierele produse de extractor (A), citite de agent (B):
- `_extras/dosar_extras.json`: `DosarExtras` (cu `categorie`, `subcategorie`, `indicatori`)
- `_extras/raport_extractie.json`: cheile `categorie_candidati`, `documente_gasite`, `documente_lipsa`,
  `campuri_lipsa`, `conflicte`. Ajung în agent prin `StareDosar.raport_extractie`.

Fișierul citit de UI (A), produs de agent (B): un `Verdict` (din `contracts.py`), salvat ca JSON.

## Etapele

### Etapa 0: stabilizare (doar Persoana A, înainte de împărțire)
Pe ramura de integrare `integration/refined-rules-complete-implementation`:
1. readuce cele 6 teste șterse;
2. adaugă `.gitattributes` (oprește zgomotul CRLF / LF dintre Windows și restul);
3. modificările comune de contract (`StareDosar.raport_extractie`);
4. PR în `main` + merge. Ramura `extractie-edyra` se **retrage**: nu se mai unește, testele ei au fost recuperate la pasul 1.

Prompt: `docs/prompts/prompt_etapa0_stabilizare.md`.

### Etapa 1: lucru în paralel
Amândoi pornesc din `main`, după Etapa 0:
```
git checkout main
git pull
git checkout -b feat/extractor-tools-ui     (A)   /   git checkout -b feat/motor-agent   (B)
```
Prompturi: `docs/prompts/prompt_A_extractor_tools_ui.md` și `docs/prompts/prompt_B_motor_agent.md`.

**De 2 ori pe zi (sau după fiecare PR al celuilalt), fiecare își aduce `main` în ramura lui:**
```
git fetch origin
git merge origin/main
python -m pytest -q
```
Așa conflictele, dacă apar, sunt mici și apar devreme.

### Etapa 2: integrare
1. A deschide PR-ul lui în `main` → B îl verifică → merge.
2. B face `git merge origin/main` în ramura lui, rulează testele și `python -m eval.run_eval` pe toate dosarele → PR → A îl verifică → merge.
3. Pe `main`, împreună: `python -m eval.run_eval` cap-coadă + UI-ul pe 3 dosare de demo.

## Checklist înainte de orice PR
- [ ] `git fetch origin && git merge origin/main` fără conflicte
- [ ] `python -m pytest -q` trece
- [ ] `git diff --stat origin/main` arată modificări **doar** în folderele mele
- [ ] niciun fișier `.env` sau cheie în commit
- [ ] descrierea PR-ului: ce s-a schimbat + cum se testează

## Dacă totuși apare un conflict
În VS Code, fișierul cu conflict arată blocuri **Current Change** / **Incoming Change**.
Dacă fișierul e în folderul tău: alegi tu. Dacă e al celuilalt sau comun: **nu ghici**, rezolvați-l împreună.
Apoi `git add <fișier>`, `git commit`, rulezi din nou testele.
