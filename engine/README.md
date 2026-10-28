# Modulul C: Motorul de reguli

Aici se iau deciziile, **determinist**, pe baza `rules/green_buildings.yaml`.

| Tool / funcție | Ce face |
|---|---|
| `evalueaza_conditii_generale` | G-01 țară (Anexa B), G-02 sector + firmă activă (Anexa A), G-04 fereastra de 24 luni |
| `evalueaza_cale(cale_id)` | GB-01 certificare, GB-02 top 15%, GB-03 EPC clasa A, GB-04 NZEB |
| `verifica_chiriasi` | GB-X1: chiriași din sectorul fosil (nota 6) |
| `calculeaza_co2` | formula RBI (Impact Report p. 22), cu pașii păstrați |
| `decide_verdict(stare)` | verdictul final din rezultatele regulilor |
