# Verificările sistemului: toate categoriile verzi

Până acum sistemul verifica doar clădirile. Framework-ul RBI are **6 categorii verzi**, fiecare cu
praguri de emisii, de energie și cu excluderi. Documentul ăsta spune ce se verifică, ce date trebuie
extrase pentru asta, ce se schimbă în arhitectură și cine ce face.

## 1. Cele trei niveluri de verificare

| Nivel | Ce întreabă | Unde e scris | Rezultat posibil |
|---|---|---|---|
| **1. Eligibilitate** | Proiectul respectă pragurile din Framework? (ex. ≤ 50 gCO2/km, PUE < 1.5, ≥ 30% economie) | `rules/*.yaml` | OK / NU / NEEVALUABIL / OK_CONDITIONAT |
| **2. Plauzibilitate** | Cifrele declarate sunt credibile și consistente între documente și registre? | `reference/plauzibilitate.yaml` | OK / SEMNAL |
| **3. Impact** | Cât CO2 și câtă energie se economisesc, după metodologia RBI? | `reference/metodologie_impact.yaml` | tCO2e/an, MWh/an |

Nivelul 1 vine din Framework. Nivelul 2 e **al nostru** (anti-greenwashing, erori de unități).
Nivelul 3 vine din Impact Report, cu surse publice în locul celor plătite (marcate „proxy”).

## 2. Verificările pe categorii: emisii și energie

### Green Buildings (p. 7–8)
| Ce se verifică | Prag | Regula |
|---|---|---|
| Certificare | BREEAM ≥ Excellent, LEED/DGNB/ÖGNI ≥ Gold, EDGE Basic **cu ≥ 30% economie** | GB-01 |
| Clasa energetică | EPC ≥ A | GB-03 |
| Energie primară | ≥ 10% sub pragul NZEB național | GB-04 |
| **Renovare: energie sau emisii** | **reducere ≥ 30% față de înainte, în ≤ 3 ani** | GB-R1, GB-R3 |
| Pompe de căldură | agent frigorific **GWP ≤ 675** + sistem de management | GB-M2, GB-M3 |
| Stații de încărcare | nu în parcări independente | GB-M1 |
| Recuperatoare de căldură | nu pentru sisteme pe combustibili fosili | GB-M6 |

### Renewable Energy (p. 8–10)
| Ce se verifică | Prag | Regula |
|---|---|---|
| Solar concentrat | ≥ 85% electricitate din solar | RE-02 |
| **Hidro (până în 2020)** | densitate > 5 W/m² **sau** emisii directe < 100 gCO2e/kWh | RE-03b |
| **Hidro (după 2020)** | densitate > 10 W/m² **sau** emisii directe < 50 gCO2e/kWh | RE-03c |
| Hidro nou | studiu de impact de mediu fără risc semnificativ | RE-04 |
| **Geotermal** | emisii pe ciclu de viață **< 100 gCO2/kWh** | RE-05 |
| **Biomasă din deșeuri** | emisii pe ciclu de viață **< 100 gCO2e/kWh** + materie primă permisă | RE-06, RE-07 |
| Hidrogen | doar electroliză cu energie regenerabilă | RE-08 |
| Termoficare | rețea alimentată **> 50%** din regenerabile/căldură reziduală | RE-10 |

### Energy Efficiency (p. 10–11)
| Ce se verifică | Prag | Regula |
|---|---|---|
| **Eficiență industrială** | **≥ 30% îmbunătățire** sau tehnologie BAT | EE-01 |
| Stocare | integrată cu surse regenerabile | EE-03 |
| Rețele | nu dedicate conectării centralelor fosile | EE-04 |
| **Data centere** | **PUE anualizat < 1.5** | EE-07 |
| Excludere | echipamente fosile / industrie grea (oțel, ciment, rafinare) | EE-X1 |

### Clean Transportation (p. 11–13)
| Ce se verifică | Prag (WLTP) | Regula |
|---|---|---|
| **Autoturisme, utilitare** | **≤ 50 gCO2/km până în dec. 2025; 0 g/km din ian. 2026** (după data marcării) | CT-03 |
| **Camioane** | **≤ 25 gCO2/km** | CT-04 |
| **Trenuri de pasageri** | **≤ 50 gCO2e/pasager-km** | CT-05 |
| **Trenuri de marfă, autocare** | **≤ 25 gCO2/tonă-km** | CT-06 |
| Vehicule non-rutiere | doar electrice | CT-08 |
| Infrastructură | fără drumuri, parcări, stații de carburant fosil | CT-10 |
| Excludere | vehicule dedicate transportului de combustibili fosili | CT-X1 |

### Pollution Prevention (p. 13–14)
| Ce se verifică | Prag | Regula |
|---|---|---|
| **Gaz de depozit** | **eficiență de captare ≥ 75%**, fără ardere la flacără | PP-06 |
| Vehicule de colectare | doar zero emisii sau hibride | PP-04 |
| Reciclare | fără reciclare chimică a plasticului | PP-01 |

### Circular Economy (p. 14–15)
| Ce se verifică | Prag | Regula |
|---|---|---|
| **Aluminiu** | **≥ 90% reciclat**, sau ≥ 75% reciclat **și** aluminiu primar **< 2.5 tCO2e/t** | CE-03 |
| Excludere | plastic virgin | CE-X1 |

### Toate categoriile (p. 6, 18–19, 23, 25–26)
Țară eligibilă (G-01), sector neexclus (G-02), proces standard de credit (G-03), ≤ 24 luni (G-04),
**pragurile se aplică la data marcării** (G-05, grandfathering).
La nivel de portofoliu: R&D ≤ 10% (P-01), pure player > 90% din cifra de afaceri (P-02), acoperirea obligațiunilor (P-04).

## 3. Ce trebuie extras în plus (pentru A)

Fiecare câmp nou se adaugă în `extraction/campuri.yaml`, cu cuvinte cheie în română și engleză.

| Categorie | Câmpuri noi (unitate) | Documente unde se găsesc de obicei |
|---|---|---|
| comun | `categorie`, `subcategorie`/`tehnologie`/`tip`, `descriere_proiect`, `data_marcare_verde` | cererea de finanțare |
| clădiri – renovare | `ped_inainte_kwh_m2`, `ped_dupa_kwh_m2`, `reducere_emisii_pct`, `ani_pana_la_reducere`, `tip_masura`, `gwp_agent_frigorific` | EPC înainte/după, audit energetic, fișa tehnică |
| regenerabile | `capacitate_mw`, `productie_anuala_mwh`, `an_punere_functiune`, `densitate_putere_w_m2` (sau `putere_instalata_w` + `suprafata_lac_m2`), `emisii_directe_gco2e_kwh`, `emisii_ciclu_viata_gco2_kwh`, `materie_prima`, `eia_concluzie` | studiu de fezabilitate, autorizație, EIA, LCA |
| eficiență | `consum_inainte_mwh`, `consum_dupa_mwh`, `imbunatatire_eficienta_pct`, `tehnologie_bat`, `pue_anualizat`, `industrie_beneficiar`, `nr_gospodarii`, `nr_contoare` | audit energetic, raport de măsurare PUE |
| transport | `model_vehicul`, `nr_vehicule`, `emisii_wltp_gco2_km`, `combustibil`, `consum_kwh_km`, `distanta_anuala_km`, `emisii_gco2e_pkm`, `emisii_gco2_tkm`, `transporta_combustibili_fosili` | certificat de conformitate (CoC), ofertă, fișa vehiculului |
| poluare | `eficienta_captare_pct`, `utilizare_gaz`, `propulsie_vehicule_colectare`, `reciclare_chimica_plastic` | studiu tehnic, autorizație de mediu |
| circular | `pondere_aluminiu_reciclat`, `intensitate_carbon_aluminiu_primar_tco2e_t`, `foloseste_plastic_virgin` | declarații furnizori, certificate de produs |

## 4. Modificarea de contract necesară (decizie de echipă)

`DosarExtras` are acum doar câmpuri pentru clădiri. Ca să nu adăugăm 50 de câmpuri, propunerea e:

```python
class DosarExtras(BaseModel):
    ...                                      # câmpurile existente rămân (compatibilitate)
    categorie: Optional[Camp] = None         # green_buildings | renewable_energy | ...
    subcategorie: Optional[Camp] = None      # renovare | hidro | autoturism_sau_utilitara | ...
    indicatori: dict[str, Camp] = Field(default_factory=dict)
    #   ex: {"emisii_wltp_gco2_km": Camp(valoare=0, sursa="CoC.pdf, p.1"), "nr_vehicule": Camp(valoare=10, ...)}
```

Numele cheilor din `indicatori` sunt **exact** numele câmpurilor din `rules/*.yaml`. Așa motorul de reguli
citește orice câmp nou fără să se schimbe contractul din nou.

## 5. Ce se schimbă în fluxul agentului

```
înainte:  firmă → condiții generale → certificat → căi GB-01..04 → chiriași → CO2
acum:     firmă → condiții generale → CATEGORIA → regulile categoriei (cu căile alternative)
          → excluderile categoriei → PLAUZIBILITATE → IMPACT
```

Tools noi:
| Tool | Cine | Ce face |
|---|---|---|
| `stabileste_categoria` | D (LLM) | Decide categoria și subcategoria din descrierea proiectului. Dacă e ambiguu, cere date (ex. „fibră optică” = eficiență energetică, dar nu e aliniată cu Taxonomia UE). |
| `evalueaza_categoria(categorie)` | C | Rulează regulile din `rules/<categorie>.yaml` și întoarce câte un `RezultatRegula` per regulă. |
| `verifica_plauzibilitate` | C | Rulează `reference/plauzibilitate.yaml`; rezultatele sunt doar OK/SEMNAL. |
| `calculeaza_impact(categorie)` | C | Formula din `reference/metodologie_impact.yaml`, cu pașii păstrați. |
| `cauta_emisii_vehicul(model)` | B | Emisiile WLTP oficiale din datele EEA. |
| `factor_emisie_tara(tara, an)` | B | Intensitatea carbon a rețelei (Ember / Our World in Data). |

`decide_verdict` rămâne la fel: condiție generală NU → NEELIGIBIL; SEMNAL → EXCEPȚIE;
regulă obligatorie NU → NEELIGIBIL; cale OK → ELIGIBIL; cale OK_CONDITIONAT → ELIGIBIL_CU_MONITORIZARE.

## 6. Dosare de test noi (pentru C)

| Dosar | Ce testează | Verdict așteptat |
|---|---|---|
| Flotă: 10 hibride la 45 g/km, marcate în **2025** | grandfathering | ELIGIBIL |
| Aceeași flotă, marcată în **2026** | pragul 0 g/km | NEELIGIBIL (CT-03) |
| Camion electric declarat 0 g/km, în EEA apare diesel | registru vs. declarație | EXCEPȚIE (PL-02) |
| Hidrocentrală pusă în funcțiune în 2022, 7 W/m², emisii necunoscute | pragul după 2020 | NEELIGIBIL (RE-03c) |
| Parc solar 10 MW care declară 40.000 MWh/an | factor de capacitate 46% | EXCEPȚIE (PL-20) |
| Data center cu PUE 1.38 | prag PUE | ELIGIBIL |
| Fabrică de ciment: modernizare a cuptorului (−35% energie) | excludere industrie grea | NEELIGIBIL (EE-X1) |
| Renovare: EPC 210 → 160 kWh/m² (−24%) | prag 30% | NEELIGIBIL (GB-R1) |
| Profile de aluminiu: 80% reciclat, primar 2.1 tCO2e/t | calea a doua CE-03 | ELIGIBIL |
| Pompe de căldură cu R410A (GWP ≈ 2088) | GWP > 675 | NEELIGIBIL (GB-M2) |

## 7. Cine ce face

- **A (extracție):** câmpurile din secțiunea 3 în `campuri.yaml` + extragerea lor în `indicatori`.
- **B (tools):** `cauta_emisii_vehicul` (EEA) și `factor_emisie_tara` (Ember), cu cache offline.
- **C (motor):** un evaluator generic care citește orice `rules/*.yaml` (tipurile: prag, lista, da_nu, excludere,
  oricare, toate, prag_dependent_de_data), plauzibilitatea, impactul, plus dosarele din secțiunea 6.
- **D (agent):** `stabileste_categoria` + actualizarea promptului de sistem cu noul flux.
- **Toți:** decizia despre modificarea de contract din secțiunea 4, **înainte** ca A și C să înceapă.
