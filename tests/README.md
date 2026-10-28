# Teste de contract (toți)

Verifică faptul că fiecare modul respectă `docs/CONTRACTE.md`: extractorul întoarce `DosarExtras`,
fiecare tool întoarce `ToolResult` **chiar și cu argumente greșite**, pipeline-ul întoarce `Verdict`.
Rulare: `python -m pytest -q`. Trebuie să treacă înainte de orice merge în `main`.
