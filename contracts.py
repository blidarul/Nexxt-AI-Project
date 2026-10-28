"""
CONTRACTELE dintre module. Acesta e singurul fisier pe care TOTI il importa.

Regula de aur: nu schimbati acest fisier fara sa anuntati toata echipa.

    A (extraction)  ->  DosarExtras
    B (tools)       ->  ToolResult
    C (engine)      ->  RezultatRegula, Verdict
    D (agent)       ->  foloseste toate de mai sus + StareDosar
"""
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- A
class Camp(BaseModel):
    """Orice valoare extrasa dintr-un document isi pastreaza sursa (pentru audit)."""
    valoare: Optional[Union[str, float, int]] = None
    sursa: str = ""                 # ex: "01_cerere_finantare.pdf, p.1"
    incredere: float = 1.0          # 0-1; sub 0.7 agentul ar trebui sa verifice sau sa intrebe


class Chirias(BaseModel):
    nume: str
    caen: str
    m2: float


class DosarExtras(BaseModel):
    """Iesirea modulului de EXTRACTIE (A). Intrarea agentului (D) si a motorului (C)."""
    dosar_id: str
    cui: Camp
    suma_eur: Camp
    cota_banca: Camp
    data_aprobare: Camp
    tara: Camp
    adresa_cladire: Camp
    suprafata_m2: Camp
    stadiu_cladire: Camp
    nr_certificat_declarat: Camp
    epc_clasa: Optional[Camp] = None
    epc_energie_finala: Optional[Camp] = None
    epc_suprafata_m2: Optional[Camp] = None
    chiriasi: list[Chirias] = Field(default_factory=list)
    afirmatii_client: list[str] = Field(default_factory=list)
    categorie: Optional[Camp] = None
    subcategorie: Optional[Camp] = None
    indicatori: dict[str, Camp] = Field(default_factory=dict)


# --------------------------------------------------------------------------- B
class ToolResult(BaseModel):
    """Iesirea ORICARUI tool. Un tool nu arunca niciodata exceptii catre agent: intoarce eroare aici."""
    tool: str
    gasit: bool
    date: dict = Field(default_factory=dict)
    sursa: str = ""                 # ex: "ANAF API v9 (cache offline)"
    eroare: Optional[str] = None


# --------------------------------------------------------------------------- C
RezultatTip = Literal["OK", "NU", "SEMNAL", "NEEVALUABIL", "OK_CONDITIONAT"]


class RezultatRegula(BaseModel):
    regula_id: str                  # "GB-01"
    rezultat: RezultatTip
    dovada: str
    sursa_framework: str            # "Framework p.7"


VerdictTip = Literal["ELIGIBIL", "NEELIGIBIL", "EXCEPTIE_ESCALADARE_COMITET", "ELIGIBIL_CU_MONITORIZARE"]


class Verdict(BaseModel):
    """Iesirea finala a sistemului."""
    dosar_id: str
    verdict: VerdictTip
    cale_eligibilitate: Optional[str] = None
    reguli: list[RezultatRegula] = Field(default_factory=list)
    impact_tco2_an: Optional[float] = None
    impact_detalii: dict = Field(default_factory=dict)
    actiuni: list[str] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------- D
class StareDosar(BaseModel):
    """'Memoria de lucru' a agentului pentru un dosar. Toate tool-urile o pot citi si completa."""
    dosar_folder: str
    extras: DosarExtras
    rezultate_tools: dict[str, ToolResult] = Field(default_factory=dict)
    reguli: dict[str, RezultatRegula] = Field(default_factory=dict)
    impact: dict = Field(default_factory=dict)
    actiuni: list[str] = Field(default_factory=list)
    escaladat: bool = False
    trace: list[dict] = Field(default_factory=list)