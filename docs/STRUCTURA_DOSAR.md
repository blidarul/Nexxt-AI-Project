# Structura dosarului complet (acoperă tot Framework-ul RBI)

## 0. Ideea de bază

Un credit nu „aplică pentru bani verzi”. E aprobat normal, apoi banca verifică dacă poate intra în
portofoliul verde. Dosarul complet = **tot ce îi trebuie băncii ca să dovedească asta unui auditor**.

Orice dosar, de orice tip, are aceeași formă:

```
DOSAR = PARTEA A (comună, mereu aceeași)
      + PARTEA B (modulul categoriei: clădire / regenerabile / eficiență / transport / poluare / circular)
      + PARTEA C (date pentru impact: consum, producție, flotă)
      + PARTEA D (afirmațiile clientului, pentru verificarea anti-greenwashing)
```

Agentul citește A, **decide categoria**, apoi știe exact ce trebuie să găsească în B și C.
Lista completă, citită automat de agent, e în `rules/cerinte_dosar.yaml`.

## 1. Partea A: comună (orice dosar)

| Document | Ce dovedește | Câmpuri extrase | Regula |
|---|---|---|---|
| Cererea de finanțare | cine, ce, câți bani, ce declară | CUI, țară, sumă, categorie, descrierea proiectului, afirmații | G-01, categoria |
| Decizia de aprobare | a trecut procesul standard, când | aprobat, data aprobării, data marcării ca verde | G-03, G-04, G-05 |
| Certificat constatator ONRC | ce activitate are firma | CAEN | G-02 |
| Declarația beneficiarului real | cine controlează firma | beneficiari | KYC |
| Contract de credit / term sheet | partea băncii | cota băncii | impact |

## 2. Partea B: modulul categoriei. Ce trebuie să îndeplinească firma

### B1. Green Buildings
| Tip proiect | Documente | Trebuie să îndeplinească (ajunge UNA pe linie unde scrie „sau”) |
|---|---|---|
| Clădire nouă / existentă | certificat BREEAM/LEED/..., **sau** EPC; contracte de închiriere; carte funciară | BREEAM ≥ Excellent **sau** LEED/DGNB/ÖGNI ≥ Gold **sau** EDGE cu ≥30% economie **sau** EPC clasa A **sau** top 15% național **sau** ≥10% sub NZEB; **și** fără chiriași din sectorul fosil |
| Renovare | EPC/audit înainte **și** după; devizul lucrărilor | energie primară sau emisii **−30%** față de înainte, în **≤ 3 ani**; finanțare doar pentru renovare |
| Pompă de căldură | fișa tehnică | agent frigorific **GWP ≤ 675** + sistem de management |
| Stație de încărcare | fișa tehnică | **în clădire**, nu parcare independentă |
| Stocare / micro-CHP / recuperator | fișa tehnică | legat de regenerabile; recuperatorul **nu** pe sistem fosil |

### B2. Renewable Energy
| Tehnologie | Documente | Trebuie să îndeplinească |
|---|---|---|
| Eolian onshore, fotovoltaic | fezabilitate, autorizație, producție | eligibile ca tehnologie |
| Solar concentrat | fișă tehnică | **≥ 85%** electricitate din solar |
| Hidro până în 2020 | fezabilitate, autorizație | fir de apă fără rezervor **sau** densitate **> 5 W/m²** **sau** emisii **< 100 g/kWh** |
| Hidro după 2020 | idem | fir de apă fără rezervor **sau** densitate **> 10 W/m²** **sau** emisii **< 50 g/kWh** |
| Hidro nou | **EIA** | fără risc semnificativ |
| Geotermal | **LCA** | **< 100 gCO2/kWh** pe ciclu de viață |
| Biomasă din deșeuri | **LCA** + contracte materie primă | **< 100 gCO2e/kWh**; doar reziduuri, nămol, biodeșeuri; fără ulei de palmier non-RSPO |
| Hidrogen | fișă tehnică | electroliză cu energie regenerabilă |
| Termoficare | fișă tehnică | rețea **> 50%** din regenerabile / căldură reziduală |

### B3. Energy Efficiency
| Tip | Documente | Trebuie să îndeplinească |
|---|---|---|
| Industrie | audit înainte + după | **≥ 30%** mai eficient **sau** tehnologie BAT; **nu** oțel/ciment/rafinare; **nu** echipamente fosile |
| LED, echipamente | fișă tehnică, consum înainte/după | eligibil; consumul e necesar pentru impact |
| Stocare (BESS, pile de combustie) | fișă tehnică | integrată cu regenerabile |
| Rețele, smart grid | fișă tehnică | nu dedicate centralelor fosile |
| Fibră optică | proiect | înlocuiește rețele energointensive (atenție: nu e aliniată cu Taxonomia UE) |
| Data center | raport PUE anual | **PUE < 1.5** |

### B4. Clean Transportation: aici intră flota
| Tip | Documente | Trebuie să îndeplinească (emisii WLTP) |
|---|---|---|
| Autoturisme, utilitare | **lista vehiculelor** + **CoC** pe model | **≤ 50 g/km** dacă marcat până în 31.12.2025; **0 g/km** din 01.01.2026 |
| Camioane | idem + declarație de utilizare | **≤ 25 g/km**; nu transportă combustibili fosili |
| Trenuri de pasageri | fișă tehnică | **≤ 50 gCO2e/pasager-km** |
| Trenuri de marfă, autocare | fișă tehnică | **≤ 25 gCO2/tonă-km** |
| Utilaje (macarale, excavatoare) | fișă tehnică | doar electrice |
| Infrastructură | proiect | fără drumuri, parcări, stații de carburant fosil |

**Anexa flotă (obligatorie pentru vehicule)**, câte un rând per model:

| marca | model | combustibil | bucăți | emisii WLTP (g/km) | consum (kWh/km) | VIN / nr. înmatriculare | data marcării | km/an | utilizare |
|---|---|---|---|---|---|---|---|---|---|

Din ea agentul: (1) verifică pragul **per model** față de data marcării, (2) confirmă emisiile în registrul EEA,
(3) calculează CO2 evitat cu formula RBI. Exemplu complet: `docs/exemplu_dosar_flota.json`.

### B5. Pollution Prevention
| Tip | Trebuie să îndeplinească |
|---|---|
| Reciclare | fără reciclare chimică a plasticului; deșeuri electronice doar cu plan de gestionare; segregare la sursă |
| Colectare | deșeuri nepericuloase separate; vehicule **zero emisii sau hibride** |
| Gaz de depozit | captare **≥ 75%**, fără ardere la flacără |

### B6. Circular Economy
| Tip | Trebuie să îndeplinească |
|---|---|
| Aluminiu | **≥ 90%** reciclat **sau** (≥ 75% reciclat **și** aluminiu primar **< 2.5 tCO2e/t**) |
| Materiale bio | certificare de aprovizionare sustenabilă (ex. RSB) |
| General | fără plastic virgin |

## 3. Partea C: date pentru impact (CO2 și energie)

| Categorie | Ce date trebuie în dosar | Ce calculăm |
|---|---|---|
| Clădiri | energie finală (kWh/m²), suprafață | MWh economisiți, tCO2 evitate |
| Regenerabile | capacitate (MW), producție anuală (MWh) | tCO2 evitate; plus verificarea factorului de capacitate |
| Eficiență | consum înainte/după (MWh); gospodării sau contoare | MWh economisiți, tCO2 evitate |
| Transport | flota: consum kWh/km, emisii, km/an | tCO2 evitate per vehicul și total |
| Poluare | tone reciclate/an, MWh produși | tone, MWh |
| Circular | tone materie primă economisite | tone, tCO2 |

Formulele sunt în `reference/metodologie_impact.yaml`.

## 4. Partea D: afirmațiile clientului

Tot ce afirmă clientul despre „verde” („100% zero emisii”, „consumăm cu 60% mai puțin”) se extrage separat
și se confruntă cu cifrele (verificarea PL-03). O afirmație nesusținută **nu** schimbă eligibilitatea,
dar apare ca acțiune în verdict: e exact detectarea de greenwashing.

## 5. Proiecte mixte

Un credit poate finanța mai multe lucruri: o clădire **plus** panouri pe acoperiș **plus** stații de încărcare.
Framework-ul permite atunci doar **partea eligibilă** (pro-rata, p. 19).

Pentru hackathon: **un dosar = o categorie** (varianta de bază). Extensie, dacă rămâne timp: o listă de
`componente`, fiecare cu categoria, suma și indicatorii ei. Agentul evaluează fiecare componentă,
iar suma eligibilă = suma componentelor eligibile. E o modificare de contract, deci decizie de echipă.

## 6. Cum folosește agentul structura asta (orice dosar)

```
1. citește Partea A                 → verifică condițiile generale (G-01…G-05)
2. stabileste_categoria             → categorie + subcategorie (LLM, din descrierea proiectului)
3. verifica_completitudine          → compară ce s-a extras cu rules/cerinte_dosar.yaml
      lipsește ceva obligatoriu?    → cere_date_client (cu lista exactă și regula pentru care e nevoie)
4. evalueaza_categoria              → regulile din rules/<categorie>.yaml (căi alternative, excluderi)
5. verifica_plauzibilitate          → reference/plauzibilitate.yaml (blocant / informativ)
6. calculeaza_impact                → reference/metodologie_impact.yaml
7. decide_verdict                   → ELIGIBIL / NEELIGIBIL / EXCEPȚIE / ELIGIBIL CU MONITORIZARE
```

Pasul 3 face sistemul să meargă pe **orice** dosar: dacă ai pus un dosar de transport fără CoC, agentul nu
crapă și nu ghicește. Spune exact: „lipsește CT-D2 (certificatele de conformitate), necesar pentru CT-03”.
