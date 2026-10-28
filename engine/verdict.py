# PROPRIETAR: C
# SCOP: Verdictul final, din rezultatele regulilor.
#
# INTERFATA (ce folosesc ceilalti):
#   decide_verdict(stare) -> Verdict
#
# DE FACUT:
#   [ ] Conditie generala NU -> NEELIGIBIL
#   [ ] SEMNAL sau escaladare -> EXCEPTIE_ESCALADARE_COMITET
#   [ ] O cale OK -> ELIGIBIL
#   [ ] O cale OK_CONDITIONAT -> ELIGIBIL_CU_MONITORIZARE
#   [ ] Altfel -> NEELIGIBIL
