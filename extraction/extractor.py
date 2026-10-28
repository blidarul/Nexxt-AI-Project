# PROPRIETAR: A
# SCOP: Transforma PDF-urile unui dosar in DosarExtras.
#
# INTERFATA (ce folosesc ceilalti):
#   extrage(folder_dosar) -> DosarExtras
#
# DE FACUT:
#   [ ] Modul mock: citeste extras_mock.json
#   [ ] Text din PDF (pdfplumber)
#   [ ] Apel LLM per document, cu JSON schema din DosarExtras, cu sursa + incredere pe fiecare camp
#   [ ] Unificarea rezultatelor intr-un singur DosarExtras
#   [ ] Comparatie automata cu extras_mock.json pe toate dosarele
