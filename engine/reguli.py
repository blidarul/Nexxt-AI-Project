# PROPRIETAR: C
# SCOP: Evaluarea regulilor din rules/green_buildings.yaml.
#
# INTERFATA (ce folosesc ceilalti):
#   @tool("evalueaza_conditii_generale")
#   @tool("evalueaza_cale") (cale_id: GB-01..GB-04)
#   @tool("verifica_chiriasi")
#   fiecare scrie RezultatRegula in stare.reguli
#
# DE FACUT:
#   [ ] Citirea YAML
#   [ ] G-01, G-02 (lista CAEN pentru Anexa A), G-04
#   [ ] GB-01 (rating + stadiu Interim/Final), GB-03, GB-02/GB-04 NEEVALUABIL
#   [ ] GB-X1 cu ponderea chiriasului
