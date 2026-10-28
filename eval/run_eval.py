"""Evaluarea performanței agentului pe toate dosarele de test."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from agent.orchestrator import proceseaza_dosar
from contracts import Verdict

logger = logging.getLogger(__name__)


def compara_verdict_cu_asteptat(verdict: Verdict, asteptat: dict[str, Any]) -> list[str]:
    """Compară verdictul obținut cu specificația din expected.json.

    Întoarce o listă de neconcordanțe (goală dacă totul este corect).
    """
    erori: list[str] = []

    # 1. Verificare verdict tip
    verdict_asteptat = asteptat.get("verdict")
    if verdict.verdict != verdict_asteptat:
        erori.append(
            f"Verdict diferit: obținut '{verdict.verdict}', așteptat '{verdict_asteptat}'"
        )

    # 2. Verificare cale de eligibilitate
    cale_asteptata = asteptat.get("cale_eligibilitate")
    if cale_asteptata:
        cale_obtinuta = verdict.cale_eligibilitate or ""
        # Verificare potrivire exactă sau prefix comun
        if cale_obtinuta != cale_asteptata and not (
            cale_asteptata.startswith(cale_obtinuta) or cale_obtinuta.startswith(cale_asteptata[:5])
        ):
            erori.append(
                f"Cale eligibilitate nepotrivită: obținut '{cale_obtinuta}', așteptat '{cale_asteptata}'"
            )

    # 3. Verificare reguli evaluate
    reguli_asteptate = asteptat.get("reguli", [])
    reguli_obtinute_map = {r.regula_id: r for r in verdict.reguli}

    for r_ast in reguli_asteptate:
        r_id = r_ast.get("id") or r_ast.get("regula_id")
        rez_ast = r_ast.get("rezultat")

        if r_id not in reguli_obtinute_map:
            erori.append(f"Regula '{r_id}' nu a fost evaluată (așteptat rezultat '{rez_ast}')")
        else:
            rez_obt = reguli_obtinute_map[r_id].rezultat
            if rez_obt != rez_ast:
                erori.append(
                    f"Regula '{r_id}': rezultat obținut '{rez_obt}', așteptat '{rez_ast}'"
                )

    # 4. Verificare impact CO2
    impact_ast = asteptat.get("impact")
    if isinstance(impact_ast, dict) and "rezultat_tco2_an" in impact_ast:
        tco2_ast = float(impact_ast["rezultat_tco2_an"])
        if verdict.impact_tco2_an is None:
            erori.append(f"Impact CO2 necalculat (așteptat {tco2_ast} tCO2/an)")
        elif round(float(verdict.impact_tco2_an), 1) != round(tco2_ast, 1):
            erori.append(
                f"Impact CO2 diferit: obținut {verdict.impact_tco2_an}, așteptat {tco2_ast}"
            )
    elif isinstance(impact_ast, str) and "nu se calculeaza" in impact_ast.lower():
        if verdict.impact_tco2_an is not None:
            erori.append(
                f"Impact CO2 nu trebuia calculat, dar are valoarea {verdict.impact_tco2_an}"
            )

    # 5. Verificare acțiuni
    actiuni_asteptate = asteptat.get("actiuni", [])
    if actiuni_asteptate:
        actiuni_obtinute_text = " ".join(verdict.actiuni).lower()
        for act in actiuni_asteptate:
            # Verificăm că cel puțin un cuvânt cheie important este menționat în acțiuni
            cuvinte_cheie = [c.lower() for c in act.split() if len(c) > 4][:2]
            if not any(k in actiuni_obtinute_text for k in cuvinte_cheie):
                erori.append(f"Acțiune așteptată lipsă: '{act}'")

    return erori


def ruleaza_evaluare(dosare_dir: Path | str = "dosare") -> int:
    """Rulează procesarea și evaluarea pe toate dosarele găsite."""
    cale_dosare = Path(dosare_dir)
    if not cale_dosare.exists():
        print(f"Eroare: Directorul {cale_dosare} nu există.")
        return 1

    foldere_dosare = sorted([
        f for f in cale_dosare.iterdir()
        if f.is_dir() and (f / "expected.json").exists()
    ])

    if not foldere_dosare:
        print(f"Nu s-au găsit dosare cu expected.json în {cale_dosare}.")
        return 1

    print("\n" + "=" * 90)
    print(f"{'DOSAR':<40} | {'VERDICT ASTEPTAT':<15} | {'VERDICT REAL':<15} | {'STATUS':<8}")
    print("=" * 90)

    esecuri = 0

    for folder in foldere_dosare:
        nume_dosar = folder.name
        cale_expected = folder / "expected.json"

        with open(cale_expected, "r", encoding="utf-8") as f:
            asteptat = json.load(f)

        try:
            verdict = proceseaza_dosar(str(folder))
            erori = compara_verdict_cu_asteptat(verdict, asteptat)
            status = "PASS" if not erori else "FAIL"
            v_ast = str(asteptat.get("verdict", "-"))
            v_real = str(verdict.verdict)

            print(f"{nume_dosar:<40} | {v_ast:<15} | {v_real:<15} | {status:<8}")

            if erori:
                esecuri += 1
                for err in erori:
                    print(f"   [!] {err}")
        except Exception as exc:
            esecuri += 1
            print(f"{nume_dosar:<40} | {'-':<15} | {'EROARE':<15} | FAIL")
            print(f"   [!] Excepție în timpul procesării: {exc}")

    print("=" * 90)
    total = len(foldere_dosare)
    trecute = total - esecuri
    print(f"Rezultat final: {trecute}/{total} dosare validate cu succes.")

    if esecuri > 0:
        print(f"Evaluare EȘUATĂ: {esecuri} dosare cu neconcordanțe.\n")
        return 1

    print("Evaluare REUȘITĂ: toate dosarele corespund specificațiilor din expected.json.\n")
    return 0


if __name__ == "__main__":
    cod = ruleaza_evaluare()
    sys.exit(cod)
