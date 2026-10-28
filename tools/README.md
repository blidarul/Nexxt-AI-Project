# Modulul B: Tools pentru surse externe

Fiecare tool se înregistrează cu `@tool`, primește `(intrare, stare)` și întoarce **mereu** `ToolResult`.

| Tool | Sursă reală | Mod offline |
|---|---|---|
| `verifica_firma(cui)` | API ANAF PlatitorTvaRest (v9) | `dosare/*/05_raspuns_anaf.json` |
| `cauta_certificat(nr_certificat)` | tools.breeam.com (scraping politicos) | `dosare/*/02_registru_breeam.json` |

**Gata când:** ambele moduri merg, iar cu internetul oprit demo-ul rulează identic.
