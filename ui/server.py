"""Server REST API FastAPI pentru interfața Lovable GreenProof.

Expune pipeline-ul de analiză Green Bond:
- GET  /api/dosare
- POST /api/analizeaza
- POST /api/analizeaza-upload
- POST /api/batch-eval
- POST /api/analyze-folder (compatibilitate Lovable)
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, List, Optional

# Asigură accesul la rădăcina proiectului
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from contracts import DosarExtras, Verdict
from agent.orchestrator import proceseaza_dosar


app = FastAPI(
    title="GreenProof API",
    description="API pentru analiza dosarelor Green Bond Raiffeisen Bank Romania",
    version="1.0.0",
)

# Permite apeluri cross-origin (CORS) de la Lovable (localhost:5173, localhost:3000 sau domenii Lovable)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Modele Pydantic pentru Request / Response
# ---------------------------------------------------------------------------

class DosarCatalogItem(BaseModel):
    id: str
    descriere: str
    verdict_asteptat: str


class AnalizeazaRequest(BaseModel):
    dosar_id: str


class AnalyzeFolderJsonRequest(BaseModel):
    folderId: str
    options: Optional[dict[str, Any]] = None


class BatchResultItem(BaseModel):
    dosar_id: str
    verdict: str
    cale_eligibilitate: Optional[str] = None
    impact_tco2_an: Optional[float] = None
    pasi_agent: int
    reguli_evaluate: int
    verdict_asteptat: str


class AnalizaResponse(BaseModel):
    verdict: Verdict
    extras: Optional[DosarExtras] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _citeste_catalog() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    csv_path = ROOT_DIR / "dosare" / "index.csv"
    if csv_path.exists():
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d_id = row.get("dosar", "").strip()
                if d_id:
                    catalog[d_id] = {
                        "descriere": row.get("descriere", ""),
                        "verdict_asteptat": row.get("verdict_asteptat", ""),
                    }
    return catalog


def _citeste_extras(folder_cale: str) -> Optional[DosarExtras]:
    cale = Path(folder_cale)
    if not cale.exists():
        return None
    try:
        from extraction.extractor import extrage
        return extrage(folder_cale)
    except Exception:
        mock_file = cale / "extras_mock.json"
        if mock_file.exists():
            try:
                date = json.loads(mock_file.read_text(encoding="utf-8"))
                return DosarExtras(**date)
            except Exception:
                return None
    return None


def _proceseaza_folder_sau_demo(dosar_id_or_cale: str) -> AnalizaResponse:
    target = dosar_id_or_cale.strip()

    # 1. Verificare folder în dosare/
    cale_folder = ROOT_DIR / "dosare" / target
    if cale_folder.exists() and cale_folder.is_dir():
        v = proceseaza_dosar(str(cale_folder))
        e = _citeste_extras(str(cale_folder))
        return AnalizaResponse(verdict=v, extras=e)

    # 2. Verificare dacă este calea directă
    cale_directa = Path(target)
    if cale_directa.exists() and cale_directa.is_dir():
        v = proceseaza_dosar(str(cale_directa))
        e = _citeste_extras(str(cale_directa))
        return AnalizaResponse(verdict=v, extras=e)

    # 3. Verificare dacă este un demo offline din ui/exemple/
    demo_file = ROOT_DIR / "ui" / "exemple" / f"{target}.json"
    if not demo_file.exists():
        demo_file = ROOT_DIR / "ui" / "exemple" / target

    if demo_file.exists() and demo_file.is_file():
        date_demo = json.loads(demo_file.read_text(encoding="utf-8"))
        v = Verdict(**date_demo)
        e = _citeste_extras(str(ROOT_DIR / "dosare" / v.dosar_id))
        return AnalizaResponse(verdict=v, extras=e)

    raise HTTPException(status_code=404, detail=f"Dosarul '{target}' nu a fost găsit în dosare/ sau ui/exemple/.")


# ---------------------------------------------------------------------------
# Endpoint-uri API
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "GreenProof API",
        "status": "online",
        "docs": "/docs",
        "endpoints": [
            "GET /api/dosare",
            "POST /api/analizeaza",
            "POST /api/analizeaza-upload",
            "POST /api/batch-eval",
            "POST /api/analyze-folder",
        ],
    }


@app.get("/api/dosare", response_model=List[DosarCatalogItem])
def get_dosare():
    """Returnează lista dosarelor de credit disponibile în bancă."""
    catalog = _citeste_catalog()
    items: list[DosarCatalogItem] = []

    # Din index.csv
    for d_id, info in catalog.items():
        items.append(
            DosarCatalogItem(
                id=d_id,
                descriere=info.get("descriere", ""),
                verdict_asteptat=info.get("verdict_asteptat", ""),
            )
        )

    # Dacă index.csv este gol, adăugăm folderele fizice din dosare/
    if not items:
        dosare_dir = ROOT_DIR / "dosare"
        if dosare_dir.exists():
            for f in sorted(dosare_dir.iterdir()):
                if f.is_dir() and not f.name.startswith("."):
                    items.append(
                        DosarCatalogItem(
                            id=f.name,
                            descriere=f"Dosar {f.name}",
                            verdict_asteptat="—",
                        )
                    )

    return items


@app.post("/api/analizeaza", response_model=AnalizaResponse)
def analizeaza_dosar(req: AnalizeazaRequest):
    """Analizează un dosar după ID sau cale și întoarce Verdictul complet și datele extrase."""
    return _proceseaza_folder_sau_demo(req.dosar_id)


@app.post("/api/analyze-folder")
def analyze_folder_alias(req: AnalyzeFolderJsonRequest):
    """Alias compatibil cu ruta nativă Lovable `POST /api/analyze-folder`."""
    res = _proceseaza_folder_sau_demo(req.folderId)
    # Returnăm atât payload-ul nou cât și câmpurile generice dacă Lovable le cere
    v = res.verdict
    status_map = {
        "ELIGIBIL": "compliant",
        "ELIGIBIL_CU_MONITORIZARE": "compliant",
        "EXCEPTIE_ESCALADARE_COMITET": "review",
        "NEELIGIBIL": "non_compliant",
    }
    return {
        "analysisId": f"analysis_{v.dosar_id}_{int(time.time())}",
        "folderName": v.dosar_id,
        "status": status_map.get(v.verdict, "review"),
        "score": 100 if v.verdict == "ELIGIBIL" else (75 if v.verdict == "ELIGIBIL_CU_MONITORIZARE" else (50 if v.verdict == "EXCEPTIE_ESCALADARE_COMITET" else 0)),
        "summary": f"Verdict: {v.verdict} | Cale: {v.cale_eligibilitate or 'Niciuna'} | CO2: {v.impact_tco2_an or 'N/A'} t/an",
        "verdict": v.model_dump(),
        "extras": res.extras.model_dump() if res.extras else None,
        "processedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.post("/api/analizeaza-upload", response_model=AnalizaResponse)
async def analizeaza_upload(files: List[UploadFile] = File(...)):
    """Încarcă fișiere sau arhivă ZIP pentru un dosar nou și le analizează direct."""
    if not files:
        raise HTTPException(status_code=400, detail="Nu a fost transmis niciun fișier.")

    temp_dir = Path(tempfile.gettempdir()) / "greenproof_api_uploads" / f"upload_{int(time.time() * 1000)}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        for f in files:
            file_dest = temp_dir / (f.filename or "uploaded_file")
            file_dest.parent.mkdir(parents=True, exist_ok=True)
            content = await f.read()
            file_dest.write_bytes(content)

            # Dacă este ZIP, dezarhivează automat
            if file_dest.suffix.lower() == ".zip":
                with zipfile.ZipFile(file_dest) as z:
                    z.extractall(temp_dir)

        return _proceseaza_folder_sau_demo(str(temp_dir))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Eroare procesare fișiere încărcate: {err}")


@app.post("/api/batch-eval", response_model=List[BatchResultItem])
@app.get("/api/batch-eval", response_model=List[BatchResultItem])
def evalueaza_tot_lotul():
    """Evaluează în masă toate dosarele din bancă și returnează sinteza completă."""
    catalog = _citeste_catalog()
    rezultate: list[BatchResultItem] = []

    for d_id, info in catalog.items():
        cale_f = ROOT_DIR / "dosare" / d_id
        if not cale_f.exists():
            continue
        try:
            v = proceseaza_dosar(str(cale_f))
            rezultate.append(
                BatchResultItem(
                    dosar_id=d_id,
                    verdict=v.verdict,
                    cale_eligibilitate=v.cale_eligibilitate,
                    impact_tco2_an=v.impact_tco2_an,
                    pasi_agent=len(v.trace),
                    reguli_evaluate=len(v.reguli),
                    verdict_asteptat=info.get("verdict_asteptat", "—"),
                )
            )
        except Exception as err:
            rezultate.append(
                BatchResultItem(
                    dosar_id=d_id,
                    verdict="EROARE",
                    cale_eligibilitate=str(err),
                    impact_tco2_an=None,
                    pasi_agent=0,
                    reguli_evaluate=0,
                    verdict_asteptat=info.get("verdict_asteptat", "—"),
                )
            )

    return rezultate


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ui.server:app", host="0.0.0.0", port=8000, reload=True)

