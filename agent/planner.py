"""Planificatorul agentului: decide următorul pas în mod deterministic sau via LLM."""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from contracts import StareDosar, ToolResult

logger = logging.getLogger(__name__)


class Decizie(BaseModel):
    """Decizia luată de planificator la fiecare pas."""
    tip: Literal["tool", "final"]
    nume: Optional[str] = None
    argumente: dict[str, Any] = Field(default_factory=dict)
    motiv: str = ""


class PlanificatorScriptat:
    """Planificator deterministic ghidat de starea curentă a dosarului.

    Urmează fluxul de verificare prevăzut în arhitectură:
    1. Verificare firmă (ANAF)
    2. Verificare condiții generale (G-01, G-02, G-04)
    3. Căutare certificat verde (BREEAM)
    4. Evaluare căi eligibilitate (GB-01, apoi GB-02/GB-03 dacă e cazul)
    5. Verificare chiriași (GB-X1)
    6. Acțiuni necesare (escaladare/cereri client)
    7. Calcul impact CO2
    8. Decizie finală
    """

    def pas_urmator(self, stare: StareDosar, ultimul_rezultat: ToolResult | None = None) -> Decizie:
        # 1. Verificare firmă prin ANAF dacă nu s-a rulat încă
        if "verifica_firma" not in stare.rezultate_tools:
            cui_val = str(stare.extras.cui.valoare or "").strip()
            return Decizie(
                tip="tool",
                nume="verifica_firma",
                argumente={"cui": cui_val},
                motiv=f"Verificare date identificare firmă și cod CAEN pentru CUI {cui_val} în registrul ANAF",
            )

        # 2. Evaluare condiții generale
        if "evalueaza_conditii_generale" not in stare.rezultate_tools:
            return Decizie(
                tip="tool",
                nume="evalueaza_conditii_generale",
                argumente={},
                motiv="Evaluare condiții generale G-01 (țară), G-02 (sector exclus), G-04 (fereastră 24 luni)",
            )

        # 3. Căutare certificat verde dacă există număr declarat
        if "cauta_certificat" not in stare.rezultate_tools:
            if stare.extras.nr_certificat_declarat and stare.extras.nr_certificat_declarat.valoare:
                nr_cert = str(stare.extras.nr_certificat_declarat.valoare).strip()
                return Decizie(
                    tip="tool",
                    nume="cauta_certificat",
                    argumente={"nr_certificat": nr_cert},
                    motiv=f"Căutare certificat verde declarat '{nr_cert}' în registrul BREEAM",
                )

        # 4. Evaluare calea GB-01
        if "GB-01" not in stare.reguli:
            return Decizie(
                tip="tool",
                nume="evalueaza_cale",
                argumente={"cale_id": "GB-01"},
                motiv="Evaluare cale principală GB-01 (certificare verde internațională)",
            )

        # 5. Căi alternative dacă GB-01 nu a trecut
        reg_gb01 = stare.reguli.get("GB-01")
        if reg_gb01 and reg_gb01.rezultat == "NU":
            if "GB-02" not in stare.reguli:
                return Decizie(
                    tip="tool",
                    nume="evalueaza_cale",
                    argumente={"cale_id": "GB-02"},
                    motiv="Calea GB-01 nu a fost îndeplinită; încercare cale alternativă GB-02 (top 15% național)",
                )
            if "GB-03" not in stare.reguli:
                return Decizie(
                    tip="tool",
                    nume="evalueaza_cale",
                    argumente={"cale_id": "GB-03"},
                    motiv="Calea GB-02 este neevaluabilă; încercare cale alternativă GB-03 (EPC clasa A)",
                )

        # 6. Verificare chiriași
        if "verifica_chiriasi" not in stare.rezultate_tools:
            return Decizie(
                tip="tool",
                nume="verifica_chiriasi",
                argumente={},
                motiv="Verificare activități chiriași și listă de semnal (excludere GB-X1)",
            )

        # 7. Caz semnal chiriaș combustibili fosili (ex: dosar 02)
        gb_x1 = stare.reguli.get("GB-X1")
        if gb_x1 and gb_x1.rezultat == "SEMNAL":
            if not stare.escaladat:
                return Decizie(
                    tip="tool",
                    nume="escaladeaza",
                    argumente={"motiv": "Escaladare la Sustainability Bond Committee cu dovezile de mai sus"},
                    motiv="Semnal de excludere conform GB-X1 – necesită escaladare către comitet",
                )
            if not any("operational" in a.lower() or "chirias" in a.lower() for a in stare.actiuni):
                return Decizie(
                    tip="tool",
                    nume="cere_date_client",
                    argumente={
                        "ce_lipseste": "Intrebare catre client: spatiul chiriasului e folosit operational pentru extractie sau doar ca birou administrativ?",
                        "motiv": "Clarificare utilizare spatiu chirias combustibili fosili",
                    },
                    motiv="Solicitare clarificări suplimentare de la client privind activitatea chiriașului",
                )
            return Decizie(
                tip="final",
                motiv="Verificări complete: dosarul prezintă semnal de excludere și a fost escaladat către comitet",
            )

        # 8. Caz clădire în construcție (ex: dosar 04)
        stadiu = str(stare.extras.stadiu_cladire.valoare or "").lower()
        if (reg_gb01 and reg_gb01.rezultat == "OK_CONDITIONAT") or ("construc" in stadiu):
            if not any("monitorizare" in a.lower() for a in stare.actiuni):
                stare.actiuni.append(
                    "Marcare pentru monitorizare: verificare stadiu 'Final' in registrul BREEAM dupa finalizare (2027)"
                )
            if not any("receptie" in a.lower() or "energetic" in a.lower() for a in stare.actiuni):
                return Decizie(
                    tip="tool",
                    nume="cere_date_client",
                    argumente={
                        "ce_lipseste": "Cerere catre client: certificat energetic dupa receptie",
                        "motiv": "Clădire în construcție – certificat intermediar",
                    },
                    motiv="Solicitare certificat energetic după recepție",
                )
            return Decizie(
                tip="final",
                motiv="Verificări complete: clădire în construcție aprobată condiționat cu monitorizare",
            )

        # 9. Calcul impact CO2 pentru clădiri finalizate
        if "calculeaza_co2" not in stare.rezultate_tools:
            return Decizie(
                tip="tool",
                nume="calculeaza_co2",
                argumente={},
                motiv="Calcul economie de emisii CO2 conform metodologiei RBI",
            )

        # 10. Finalizare buclă
        return Decizie(
            tip="final",
            motiv="Toate etapele de verificare și evaluare au fost finalizate cu succes",
        )


class PlanificatorLLM:
    """Planificator bazat pe LLM.

    TODO: Implementare completă a planificatorului LLM folosind tool calling
    prin schema_pentru_llm() și clientul LLM când mediul și dependențele
    de suport sunt configurate complet.
    """

    def __init__(self) -> None:
        pass

    def pas_urmator(self, stare: StareDosar, ultimul_rezultat: ToolResult | None = None) -> Decizie:
        raise NotImplementedError(
            "PlanificatorLLM nu este încă activat. "
            "Folosiți MOD_AGENT=scriptat pentru fluxul deterministic funcțional."
        )
