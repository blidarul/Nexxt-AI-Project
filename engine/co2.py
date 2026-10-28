# PROPRIETAR: C
# SCOP: Calculul economiei de CO2.
#
# INTERFATA (ce folosesc ceilalti):
#   @tool("calculeaza_co2") -> ToolResult cu rezultat_tco2_an si pasi
#
# DE FACUT:
#   [ ] Formula: (baseline - energie_finala) x suprafata x cota_banca x factor_emisie
#   [ ] Fara calcul pentru cladiri in constructie (Impact Report p.18)
#   [ ] Verificare de plauzibilitate fata de 37 tCO2 / mil. EUR
