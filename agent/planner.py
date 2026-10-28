# PROPRIETAR: D
# SCOP: Decide pasul urmator.
#
# INTERFATA (ce folosesc ceilalti):
#   pas_urmator(stare, ultimul_rezultat) -> Decizie(tip='tool'|'final', nume, argumente, motiv)
#
# DE FACUT:
#   [ ] PlanificatorScriptat (reguli simple, fara LLM)
#   [ ] PlanificatorLLM (tool calling cu schema_pentru_llm())
#   [ ] Fiecare pas are un 'motiv' afisat in trace
