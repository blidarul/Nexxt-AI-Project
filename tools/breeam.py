# PROPRIETAR: B
# SCOP: Tool cauta_certificat: certificatul in registrul public BREEAM.
#
# INTERFATA (ce folosesc ceilalti):
#   @tool("cauta_certificat") (nr_certificat) -> ToolResult cu rating, stage, town, certificate_no
#
# DE FACUT:
#   [ ] Mod offline din dosare/*/02_registru_breeam.json
#   [ ] Mod online: cautare pe tools.breeam.com, cu pauze, salvare in cache
#   [ ] Certificat inexistent -> gasit=False
