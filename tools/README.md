# Tools pentru surse externe

Fiecare tool se înregistrează cu `@tool`, primește `(intrare, stare)` și întoarce **mereu** `ToolResult`:
argumentele greșite, rețeaua căzută sau orice excepție devin `gasit=False` + `eroare` (vezi `tools/_comun.py`).

Modul se alege cu `MOD_TOOLS` din `.env`: `offline` (implicit, pentru demo) sau `online`.
În modul online, răspunsurile se păstrează în `tools/cache/` (nu intră în git); dacă sursa nu răspunde,
tool-ul folosește cache-ul, apoi datele offline, și scrie asta în `sursa`.

| Tool | Intrare | `ToolResult.date` | Online | Offline |
|---|---|---|---|---|
| `verifica_firma` | `cui` (cu sau fără `RO`) | `date_generale` (cu `cod_CAEN`), `stare_inactiv` | API ANAF PlatitorTvaRest v9 | `05_raspuns_anaf.json` din dosar, apoi fișa ANAF în PDF |
| `cauta_certificat` | `nr_certificat` | `rating`, `score_pct`, `stage`, `certificate_no`, `building_name`, ... | tools.breeam.com (căutare după număr) | `02_registru_breeam.json` din dosar, apoi certificatul în PDF |
| `cauta_emisii_vehicul` | `marca`, `model` | `emisii_wltp_gco2_km`, `combustibil`, `an_date` (+ `candidati`, `sintetic`) | EEA Discodata | `data/emisii_vehicule.csv` |
| `factor_emisie_tara` | `tara` (RO / EN / ISO3), `an` opțional | `kgco2_kwh`, `an`, `tip: "proxy"` (+ `gco2e_kwh`, `an_cerut`) | CSV Our World in Data (Ember) | `data/intensitate_carbon.csv` |

Reguli de interpretare pentru agent:
- **Datele din PDF-ul clientului** (când lipsește răspunsul registrului) au `date["verificat_in_registru"] = False`:
  nu sunt o confirmare independentă.
- **`cauta_emisii_vehicul` cu mai multe potriviri:** `gasit=True`, `date["ambiguu"]=True`, valorile principale
  `None`, iar modelele în `date["candidati"]`. Agentul alege (ex. după combustibil) sau cere precizări.
  Rândurile cu `sintetic: True` sunt modelele din fixture-uri, nu date EEA.
- **`factor_emisie_tara` cu un an încă nepublicat:** se folosește cel mai recent an anterior (`an` ≠ `an_cerut`).
  Valoarea e un proxy public; RBI folosește Enerdata.

## Datele offline
- `data/intensitate_carbon.csv`: `python -m tools.data.descarca_ember` (țările din Anexa B, din `rules/conditii_generale.yaml`;
  corespondența RO/EN/ISO3 în `data/tari.yaml`).
- `data/emisii_vehicule.csv`: `python -m tools.data.descarca_eea`, sau, dacă API-ul EEA refuză cererea,
  `python -m tools.data.descarca_eea --din-fisier <CSV descărcat de pe EEA Datahub>`.
  Agregă pe (marcă, model, combustibil) cu mediana emisiilor WLTP; rândurile `SINTETIC` (fixture-uri) se păstrează.
  Combustibilul rămâne separat pentru că mediana unui model care are și plug-in (~25 g/km) și diesel (~170 g/km)
  nu descrie nicio versiune. Plug-in-ul se recunoaște după autonomia electrică (EEA pune hibridele simple și
  plug-in la același `Ft` și `Fm`). Grafiile mărcii se unifică, marca se scoate din model („TOYOTA COROLLA” → „COROLLA”),
  iar denumirile alternative din sursă („VOLKSWAGEN, VW”) intră în coloana `alias_marca`.
  Fișierul inclus: înmatriculările din România 2025 (EEA, 155.921 de mașini), cele mai înmatriculate 500 de grupuri (98%).
  Fișierul EEA e mare (zeci de milioane de rânduri): se citește direct din `.zip`, în flux, doar coloanele necesare,
  cu memorie constantă (~600.000 rânduri/s, deci un an de date în sub un minut). Opțiuni: `--tara RO` (doar
  înmatriculările din România), `--max-randuri N` (probă rapidă), `--top N` (câte modele se păstrează, implicit 300).

Teste: `python -m pytest tools -q` (rețeaua e simulată, nu e nevoie de internet).
