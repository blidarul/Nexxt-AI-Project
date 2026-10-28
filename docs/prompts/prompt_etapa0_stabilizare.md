# Etapa 0: stabilizarea ramurii de integrare (Persoana A)

## Context
Ramura curentă: `integration/refined-rules-complete-implementation`. Conține arhitectura agentului și extractorul
(Etapele 1–3). Auditul anterior a găsit probleme care trebuie rezolvate **înainte** ca echipa să se împartă pe 2 ramuri.
Citește `docs/PLAN_ECHIPA.md` pentru planul complet.

**Fă doar ce scrie aici.** Restul problemelor din extractor se rezolvă în Etapa 1, pe altă ramură.

## Pași

### 1. Readu testele șterse
Recuperează din ramura `extractie-edyra` cele 6 teste șterse (fără să faci merge cu ramura):
eroarea clară fără cheie API, cele 2 teste ale simulatorului offline (doar la cerere explicită, nu scrie în cache),
reîncercarea la răspuns fără cheile cerute, verificarea citatului din tabele markdown și tot `test_normalizare_unitati.py`.
Folosește `git checkout extractie-edyra -- <fișier>` sau copiază testele. **Dacă un test pică, nu-l modifica ca să treacă.**
Arată-mi de ce pică: e posibil să fi dispărut un comportament cerut, și atunci se repară codul.

### 2. `.gitattributes`
Pune în rădăcină fișierul `.gitattributes` (conținutul e mai jos), apoi normalizează:
```
git add --renormalize .
git status
```
Fă un commit **separat**, doar cu asta: `Normalizare line endings (.gitattributes)`.
```
* text=auto eol=lf
*.pdf binary
*.png binary
*.jpg binary
*.jpeg binary
*.ttf binary
*.zip binary
```

### 3. Contractul comun
În `contracts.py`, în `StareDosar`, adaugă:
```python
    raport_extractie: dict = Field(default_factory=dict)
```
(lipsuri de documente și câmpuri, conflicte, candidați de categorie: agentul are nevoie de ele).
Verifică că `Camp.valoare` acceptă `bool`, `int`, `float`, `str`, `list`, `dict` (cu `bool` primul) și că există testul pentru asta.
Commit separat: `Contracte: StareDosar.raport_extractie`.

### 4. Verificare finală
- `python -m pytest -q` (tot repo-ul, nu doar `extraction`): trece complet.
- `python -m extraction.compara`: arată-mi rezultatul. Dosarele `dosar3`–`dosar5` vor fi regenerate cu extractorul real în Etapa 1, deci aici doar le raportezi.
- `git log --oneline -10` și `git status` curat.

**Nu face push și nu deschide PR.** Le fac eu după ce verific.

## Raport final
Lista testelor readuse (și dacă au trecut din prima), commit-urile făcute, rezultatul `pytest`.
