"""Script CLI pentru rularea agentului pe un singur dosar și afișarea traseului pas cu pas."""

from __future__ import annotations

import sys
from agent.orchestrator import proceseaza_dosar


def main() -> None:
    if len(sys.argv) < 2:
        print("Utilizare: python run.py dosare/<nume_dosar>")
        sys.exit(1)

    folder = sys.argv[1]
    verdict = proceseaza_dosar(folder)

    print("\n" + "=" * 80)
    print(f"REZULTAT PROCESARE DOSAR: {verdict.dosar_id}")
    print("=" * 80)
    print(f"VERDICT: {verdict.verdict}")
    print(f"CALE ELIGIBILITATE: {verdict.cale_eligibilitate or '-'}")
    if verdict.impact_tco2_an is not None:
        print(f"IMPACT ESTIMAT: {verdict.impact_tco2_an} tCO2/an")

    print("\nTRASEU (TRACE):")
    for t in verdict.trace:
        pas = t.get("pas")
        tip = t.get("tip")
        actiune = t.get("actiune") or "-"
        motiv = t.get("motiv") or ""
        rezultat = t.get("rezultat")
        print(f"  [Pas {pas}] ({tip}) {actiune}")
        if motiv:
            print(f"     Motiv: {motiv}")
        if rezultat:
            print(f"     Rezultat: {rezultat}")

    if verdict.actiuni:
        print("\nACȚIUNI / RECOMANDĂRI:")
        for a in verdict.actiuni:
            print(f"  - {a}")

    print("\nREGULI EVALUATE:")
    for r in verdict.reguli:
        print(f"  [{r.rezultat}] {r.regula_id}: {r.dovada}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
