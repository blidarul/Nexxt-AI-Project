# PROPRIETAR: B
# SCOP: Tool verifica_firma: date despre firma din ANAF.
#
# INTERFATA (ce folosesc ceilalti):
#   @tool("verifica_firma") (cui) -> ToolResult cu date_generale (denumire, adresa, cod_CAEN) si stare_inactiv
#
# DE FACUT:
#   [ ] Mod offline din dosare/*/05_raspuns_anaf.json
#   [ ] Mod online: POST la API-ul ANAF v9, salvare in tools/cache/
#   [ ] CUI negasit -> ToolResult(gasit=False, eroare=...)
