# Green Loan Eligibility Agent

Agent AI care verifică dacă un credit **deja aprobat** poate intra în portofoliul de credite verzi
al băncii, conform *RBI Sustainability Bond Framework*. Calculează CO2-ul economisit și escaladează
la om doar cazurile ambigue, cu dovezile pregătite.

Challenge: nexxt VibeHack × Raiffeisen Bank, „AI for Operational Efficiency”.

## Structura

| Folder | Ce conține | Proprietar |
|---|---|---|
| `contracts.py`, `registry.py`, `config.py` | Interfețele comune și „priza” de tools | **toată echipa** (ora 0) |
| `extraction/` | PDF → date structurate (LLM) | **A** |
| `tools/` | ANAF, registrul BREEAM, cache offline | **B** |
| `engine/` | Reguli din YAML, calcul CO2, verdict | **C** |
| `eval/`, `dosare/`, `rules/`, `reference/` | Date de test, reguli, evaluare | **C** |
| `agent/` | Bucla agentului, planificatorul (LLM), acțiuni | **D** |
| `ui/` | Interfața de demo (Streamlit) | **D** |
| `docs/` | Arhitectură, contracte | toți |
| `tests/` | Teste de contract | toți |

Detalii: `docs/ARHITECTURA.md`, `docs/CONTRACTE.md`. Reguli de lucru în git: `CONTRIBUTING.md`.

## Pornire (după ce codul există)

```
pip install -r requirements.txt
copy .env.example .env        # apoi completați cheile
python -m eval.run_eval       # scorul pe toate dosarele
python -m pytest -q           # testele de contract
```
