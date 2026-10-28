# Regulile de eligibilitate (RBI Sustainability Bond Framework, Aug-2025)

Fiecare fișier = o categorie verde. Motorul de reguli (C) le citește; agentul (D) alege categoria.

| Fișier | Categoria | Framework |
|---|---|---|
| `conditii_generale.yaml` | Se aplică ORICĂRUI dosar + reguli la nivel de portofoliu | p. 6, 18–19, 23, 25–26 |
| `green_buildings.yaml` | Clădiri noi/existente, renovări, măsuri individuale | p. 7–8 |
| `renewable_energy.yaml` | Eolian, solar, hidro, geotermal, biomasă, hidrogen, termoficare | p. 8–10 |
| `energy_efficiency.yaml` | Industrie, LED, stocare, rețele, fibră, data centere | p. 10–11 |
| `clean_transportation.yaml` | Vehicule, camioane, trenuri, infrastructură | p. 11–13 |
| `pollution_prevention.yaml` | Reciclare, colectare deșeuri, gaz de depozit | p. 13–14 |
| `circular_economy.yaml` | Produse eco-eficiente, aluminiu reciclat, RVM | p. 14–15 |

## Formatul unei reguli

```yaml
- id: RE-HIDRO-01                 # unic; apare în verdict și în trace
  nume: "Densitate de putere"     # scurt, pentru UI
  sursa: "p. 9, nota 16"          # pagina din Framework (pentru audit)
  tip: prag | lista | da_nu | excludere | oricare | toate
  ...                             # câmpurile specifice tipului (vezi exemplele)
  daca_lipseste: NEEVALUABIL      # ce se întâmplă dacă lipsește câmpul din dosar
```

Tipuri:
- **prag**: compară un câmp numeric (`camp`, `operator`, `valoare`). Operatori: `<`, `<=`, `>`, `>=`, `==`.
- **lista**: câmpul trebuie să fie (sau să nu fie) într-o listă de valori.
- **da_nu**: câmpul trebuie să aibă o anumită valoare booleană.
- **excludere**: dacă e adevărată → rezultatul e `NU` (sau `SEMNAL` dacă e un caz de judecată).
- **oricare** / **toate**: combină alte condiții (SAU / ȘI).

`daca_lipseste` poate fi: `NEEVALUABIL` (agentul cere date), `NU`, sau `SEMNAL` (escaladare).
Regula de aur: **dacă datele lipsesc, nu presupunem că dosarul trece.**
