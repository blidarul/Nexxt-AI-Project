"""Evaluarea performanței agentului pe toate dosarele de test și de reguli."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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
            cale_asteptata.startswith(cale_obtinuta)
            or cale_obtinuta.startswith(cale_asteptata[:5])
            or cale_asteptata.split()[0] in cale_obtinuta
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
            cuvinte_cheie = [c.lower() for c in act.split() if len(c) > 4][:2]
            if not any(k in actiuni_obtinute_text for k in cuvinte_cheie):
                erori.append(f"Acțiune așteptată lipsă: '{act}'")

    return erori


def gaseste_foldere_dosare(surse: list[Path | str]) -> list[Path]:
    """Descoperă toate directoarele de dosare cu expected.json din sursele specificate."""
    gasite: list[Path] = []
    for s in surse:
        p = Path(s)
        if not p.exists():
            continue
        if p.is_dir() and (p / "expected.json").exists():
            gasite.append(p)
        elif p.is_dir():
            for sub in sorted(p.iterdir()):
                if sub.is_dir() and (sub / "expected.json").exists():
                    gasite.append(sub)
    return gasite


def _proceseaza_un_dosar(folder: Path) -> dict[str, Any]:
    """Evaluează un singur dosar și returnează datele de sumar și eventualele erori."""
    cale_expected = folder / "expected.json"
    with open(cale_expected, "r", encoding="utf-8") as f:
        asteptat = json.load(f)

    try:
        verdict = proceseaza_dosar(str(folder))
        erori = compara_verdict_cu_asteptat(verdict, asteptat)
        return {
            "nume_dosar": folder.name,
            "asteptat": asteptat,
            "verdict": verdict,
            "erori": erori,
            "status": "PASS" if not erori else "FAIL",
            "exceptie": None,
        }
    except Exception as exc:
        return {
            "nume_dosar": folder.name,
            "asteptat": asteptat,
            "verdict": None,
            "erori": [str(exc)],
            "status": "FAIL",
            "exceptie": exc,
        }


def ruleaza_evaluare(
    dosare_dir: Path | str | list[Path | str] | None = None,
    mod_agent: str | None = None,
    workers: int = 4,
) -> int:
    """Rulează procesarea și evaluarea pe toate dosarele găsite.

    Parametri:
        dosare_dir: director sau listă de directoare. Implicit ["dosare", "eval/dosare_reguli"].
        mod_agent: "scriptat" sau "llm". Dacă este specificat, setează variabila MOD_AGENT.
        workers: număr de fire paralele de execuție (default: 4).
    """
    if mod_agent:
        os.environ["MOD_AGENT"] = mod_agent

    surse: list[Path | str]
    if dosare_dir is None:
        surse = ["dosare", "eval/dosare_reguli"]
    elif isinstance(dosare_dir, (str, Path)):
        surse = [dosare_dir]
    else:
        surse = list(dosare_dir)

    foldere_dosare = gaseste_foldere_dosare(surse)
    if not foldere_dosare:
        print(f"Nu s-au găsit dosare cu expected.json în sursele: {surse}")
        return 1

    mod_curent = os.environ.get("MOD_AGENT", "scriptat")
    print("\n" + "=" * 125)
    print(f"EVALUARE MOTOR & AGENT (Mod: {mod_curent.upper()}, Workers: {workers}) | Total dosare: {len(foldere_dosare)}")
    print("=" * 125)
    header = (
        f"{'DOSAR':<38} | {'VERDICT ASTEPTAT':<16} | {'VERDICT REAL':<16} | "
        f"{'CALE ELIGIBILITATE':<30} | {'CO2 (t/an)':<10} | {'STATUS':<6}"
    )
    print(header)
    print("-" * 125)

    esecuri = 0

    if workers > 1 and len(foldere_dosare) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            rezultate = list(executor.map(_proceseaza_un_dosar, foldere_dosare))
    else:
        rezultate = [_proceseaza_un_dosar(f) for f in foldere_dosare]

    for item in rezultate:
        nume_dosar = item["nume_dosar"]
        asteptat = item["asteptat"]
        verdict = item["verdict"]
        erori = item["erori"]
        status = item["status"]

        if verdict is not None:
            v_ast = str(asteptat.get("verdict", "-"))
            v_real = str(verdict.verdict)
            cale_text = str(verdict.cale_eligibilitate or "-")
            if len(cale_text) > 30:
                cale_text = cale_text[:27] + "..."
            co2_text = str(verdict.impact_tco2_an) if verdict.impact_tco2_an is not None else "-"

            line = (
                f"{nume_dosar:<38} | {v_ast:<16} | {v_real:<16} | "
                f"{cale_text:<30} | {co2_text:<10} | {status:<6}"
            )
            print(line)

            if erori:
                esecuri += 1
                for err in erori:
                    print(f"   [!] {err}")
        else:
            esecuri += 1
            print(f"{nume_dosar:<38} | {'-':<16} | {'EROARE':<16} | {'-':<30} | {'-':<10} | FAIL")
            print(f"   [!] Excepție în timpul procesării: {item['exceptie']}")

    print("=" * 125)
    total = len(foldere_dosare)
    trecute = total - esecuri
    procent = (trecute / total) * 100 if total > 0 else 0
    print(f"Rezultat ({mod_curent.upper()}): {trecute}/{total} dosare validate cu succes ({procent:.1f}%).")

    if esecuri > 0:
        print(f"Evaluare EȘUATĂ: {esecuri} dosare cu neconcordanțe.\n")
        return 1

    print("Evaluare REUȘITĂ: toate dosarele corespund specificațiilor din expected.json.\n")
    return 0


def main() -> int:
    """Punct de intrare CLI pentru modulul de evaluare."""
    parser = argparse.ArgumentParser(description="Evaluarea performanței motorului și agentului pe toate dosarele.")
    parser.add_argument(
        "--mod",
        choices=["scriptat", "llm", "ambele"],
        default="scriptat",
        help="Modul de rulare al planificatorului agent: 'scriptat', 'llm' sau 'ambele' (default: scriptat).",
    )
    parser.add_argument(
        "--dosare",
        nargs="*",
        default=None,
        help="Căi către directoare de dosare (implicit: 'dosare' și 'eval/dosare_reguli').",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Număr de fire paralele de execuție (default: 4).",
    )
    args = parser.parse_args()

    if args.mod == "ambele":
        print("\n" + "#" * 125)
        print("RULARE COMPARATIVĂ DUALĂ: SCRIPTAT vs LLM")
        print("#" * 125)
        cod_scriptat = ruleaza_evaluare(dosare_dir=args.dosare, mod_agent="scriptat", workers=args.workers)
        print("\n")
        cod_llm = ruleaza_evaluare(dosare_dir=args.dosare, mod_agent="llm", workers=args.workers)

        print("\n" + "=" * 60)
        print("RAPORT FINAL DUAL:")
        print(f"  Planificator Scriptat: {'REUȘIT' if cod_scriptat == 0 else 'EȘUAT'}")
        print(f"  Planificator LLM:      {'REUȘIT' if cod_llm == 0 else 'EȘUAT'}")
        print("=" * 60 + "\n")
        return 0 if (cod_scriptat == 0 and cod_llm == 0) else 1

    return ruleaza_evaluare(dosare_dir=args.dosare, mod_agent=args.mod, workers=args.workers)


if __name__ == "__main__":
    sys.exit(main())
