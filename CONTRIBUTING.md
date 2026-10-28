# Reguli de lucru în echipă

## Flux git (fiecare membru)

1. `git checkout main` și `git pull`: porniți mereu de la ultima versiune.
2. `git checkout -b <ramura-ta>`: o ramură per sarcină (ex: `extractie-llm`, `tool-anaf`).
3. Lucrați **doar în folderul vostru**.
4. `git add .`, `git commit -m "mesaj clar"`, `git push -u origin <ramura-ta>`.
5. Pe GitHub: **Pull Request** către `main`. Un coleg se uită, apoi merge.

## Reguli

- `main` trebuie să meargă mereu. Merge doar dacă `pytest` și `run_eval` trec.
- **`contracts.py` nu se modifică fără acordul echipei.**
- **Niciodată chei API în git.** Ele stau în `.env`, care e în `.gitignore`.
- Commit-uri mici și dese, nu unul uriaș la final.
- Sincronizare de 5 minute la fiecare 3–4 ore: ce merge, ce nu, de ce ai nevoie.
