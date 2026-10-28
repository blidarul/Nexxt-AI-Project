# PROPRIETAR: D (cu acordul echipei)
# SCOP: 'Priza' prin care se leaga modulele: fiecare modul isi inregistreaza functiile ca tools.
#
# INTERFATA (ce folosesc ceilalti):
#   @tool(nume, descriere, ModelInput)   decorator folosit de A/B/C/D
#   apeleaza(nume, argumente, stare) -> ToolResult   singurul mod in care agentul cheama un tool
#   schema_pentru_llm() -> lista de tools in format JSON schema pentru LLM
#
# DE FACUT:
#   [ ] Decoratorul @tool si dictionarul TOOLS
#   [ ] apeleaza(): valideaza intrarea, prinde ORICE eroare si o intoarce ca ToolResult
#   [ ] schema_pentru_llm() din model_json_schema() al pydantic
