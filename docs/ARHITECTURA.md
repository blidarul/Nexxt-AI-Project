# Arhitectura

```
 PDF-uri ──► [A] extrage() ──► DosarExtras
                                   │
                                   ▼
                              StareDosar  ◄── memoria comună a dosarului
                                   │
          ┌────────────────────────┴──────────────────────┐
          │  BUCLA AGENTULUI (D)                          │
          │   1. planificatorul decide: „ce fac acum?”    │
          │   2. registry.apeleaza(tool, argumente)       │──► B: verifica_firma, cauta_certificat
          │   3. rezultatul intră în StareDosar + trace   │──► C: evalueaza_conditii_generale, evalueaza_cale,
          │   4. repetă până la „final”                   │       verifica_chiriasi, calculeaza_co2
          └────────────────────────┬──────────────────────┘──► D: cere_date_client, escaladeaza
                                   ▼
                     [C] decide_verdict(stare) ──► Verdict + dovezi + trace
```

## Principii

1. **Verdictul îl dă codul** (motorul de reguli, din YAML), nu LLM-ul. LLM-ul alege drumul:
   ce verifică, în ce ordine, ce cale alternativă încearcă, când escaladează.
2. **Agentul nu importă modulele.** Le cheamă prin registru, după nume.
3. **Fiecare modul are variantă mock** care merge din prima oră. Se comută din `.env`.
4. **Un tool nu aruncă niciodată excepții către agent**: întoarce `ToolResult` cu `eroare`.
5. **Totul are sursă**: fiecare valoare extrasă și fiecare regulă păstrează fișierul/pagina.

## Căile de eligibilitate (Framework p. 7)

GB-01 certificare (BREEAM ≥ Excellent etc.) **SAU** GB-02 top 15% național **SAU**
GB-03 EPC clasa A **SAU** GB-04 energie primară cu 10% sub NZEB.
Ajunge să treacă una. Agentul le încearcă pe rând.
