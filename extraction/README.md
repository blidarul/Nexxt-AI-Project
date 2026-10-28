# Modulul A: Extracție

**Intrare:** folderul unui dosar (PDF-uri). **Ieșire:** `DosarExtras` (vezi `docs/CONTRACTE.md`).

- Modul `mock`: citește `extras_mock.json` din dosar. Toată echipa îl folosește până e gata varianta reală.
- Modul `real`: text din PDF (pdfplumber) + LLM cu ieșire structurată (JSON schema din `DosarExtras`).

**Gata când:** cu `MOD_EXTRACTIE=real`, rezultatul pe fiecare dosar e egal cu `extras_mock.json`
și `run_eval` dă același scor ca în modul mock.
