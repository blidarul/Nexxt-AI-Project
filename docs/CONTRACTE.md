# Contractele dintre module

Se transcriu în `contracts.py` (pydantic) în ora 0. După aceea nu se schimbă fără acordul echipei.

## Camp (orice valoare extrasă)
| câmp | tip | exemplu |
|---|---|---|
| valoare | text / număr / gol | `20000` |
| sursa | text | `"01_cerere_finantare.pdf, p.1"` |
| incredere | număr 0–1 | `0.95` |

## DosarExtras (iese din A)
| câmp | tip | sursa în dosar |
|---|---|---|
| dosar_id | text | numele folderului |
| cui, suma_eur, cota_banca, data_aprobare | Camp | cererea de finanțare |
| tara, adresa_cladire, suprafata_m2, stadiu_cladire | Camp | cererea de finanțare |
| nr_certificat_declarat | Camp | cererea de finanțare |
| epc_clasa, epc_energie_finala, epc_suprafata_m2 | Camp, opțional | certificatul energetic |
| chiriasi | listă de Chirias (nume, caen, m2) | contractele de închiriere |
| afirmatii_client | listă de texte | cererea de finanțare |

Exemplu complet: `dosare/*/extras_mock.json`.

## ToolResult (iese din orice tool)
| câmp | tip | exemplu |
|---|---|---|
| tool | text | `"verifica_firma"` |
| gasit | da/nu | `true` |
| date | dicționar | răspunsul sursei |
| sursa | text | `"ANAF (cache offline)"` |
| eroare | text, opțional | `"CUI negăsit"` |

## RezultatRegula (iese din C)
| câmp | tip | valori |
|---|---|---|
| regula_id | text | `G-01`, `G-02`, `G-04`, `GB-01`…`GB-04`, `GB-X1` |
| rezultat | una din | `OK`, `NU`, `SEMNAL`, `NEEVALUABIL`, `OK_CONDITIONAT` |
| dovada | text | `"BREEAM Very Good sub pragul Excellent"` |
| sursa_framework | text | `"Framework p.7"` |

## Verdict (ieșirea finală)
| câmp | tip |
|---|---|
| dosar_id | text |
| verdict | `ELIGIBIL`, `NEELIGIBIL`, `EXCEPTIE_ESCALADARE_COMITET`, `ELIGIBIL_CU_MONITORIZARE` |
| cale_eligibilitate | `GB-01`…`GB-04` sau gol |
| reguli | listă de RezultatRegula |
| impact_tco2_an | număr sau gol |
| actiuni | listă de texte (cereri către client, escaladări) |
| trace | listă de pași (pas, acțiune, motiv, rezultat) |

## StareDosar (memoria de lucru, D)
`dosar_folder`, `extras` (DosarExtras), `rezultate_tools`, `reguli`, `impact`, `actiuni`, `escaladat`, `trace`.

## Forma unui tool
`functie(intrare: ModelPydantic, stare: StareDosar) -> ToolResult`, înregistrată cu `@tool(...)`.
