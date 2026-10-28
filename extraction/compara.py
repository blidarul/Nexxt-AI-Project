"""Modul pentru compararea automată a rezultatelor extractorului cu extras_mock.json.

Compară câmp cu câmp:
- valorile numerice exact (cu toleranță epsilon pentru zecimale)
- valorile text aproximativ (fără diacritice, case-insensitive, similaritate de caractere)
- afișează un tabel cu rezultatele și discrepanțele găsite.
"""

from difflib import SequenceMatcher
import json
from pathlib import Path
import sys
from typing import Any, Optional
import unicodedata

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def normalizeaza_text_comparare(text: Optional[str]) -> str:
    """Normalizează textul pentru comparare aproximativă (minuscul, fără diacritice, fără punctuație)."""
    if text is None:
        return ""
    text_str = str(text).strip().lower()
    # Elimină diacritice
    nfkd = unicodedata.normalize("NFKD", text_str)
    fara_diacritice = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Elimină caractere non-alfanumerice de început/sfârșit
    return fara_diacritice.strip(" .,-;:\"'()[]{}")


def sunt_egale_aproximativ_text(t1: Any, t2: Any, prag_similaritate: float = 0.8) -> bool:
    """Verifică dacă două texte sunt egale aproximativ."""
    if t1 is None and t2 is None:
        return True
    if t1 is None or t2 is None:
        return False

    s1 = normalizeaza_text_comparare(str(t1))
    s2 = normalizeaza_text_comparare(str(t2))

    if s1 == s2:
        return True

    # Dacă unul este inclus în celălalt (ex: 'Cluj-Napoca' vs 'ICluj-Napoca')
    if s1 in s2 or s2 in s1:
        return True

    ratio = SequenceMatcher(None, s1, s2).ratio()
    return ratio >= prag_similaritate


def sunt_egale_valori(v1: Any, v2: Any) -> bool:
    """Compară două valori: numeric exact, text aproximativ, boolean exact."""
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False

    # Boolean
    if isinstance(v1, bool) or isinstance(v2, bool):
        return v1 is v2

    # Numeric (int, float)
    if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
        return abs(float(v1) - float(v2)) < 1e-4

    # Text / String
    return sunt_egale_aproximativ_text(v1, v2)


def extrage_valoare_camp(obiect_camp: Any) -> Any:
    """Extrage valoarea brută dintr-un nod de tip Camp (dict cu cheia 'valoare') sau valoare directă."""
    if isinstance(obiect_camp, dict) and "valoare" in obiect_camp:
        return obiect_camp["valoare"]
    return obiect_camp


def compara_dosar(
    cale_mock: Path,
    cale_extras: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compară un dosar extras cu mock-ul corespunzător.

    Returnează:
        (potriviri, diferente)
    """
    with open(cale_mock, "r", encoding="utf-8") as f:
        date_mock = json.load(f)

    with open(cale_extras, "r", encoding="utf-8") as f:
        date_extras = json.load(f)

    potriviri = []
    diferente = []

    # Câmpuri scalare
    campuri_scalare = [
        "cui", "suma_eur", "cota_banca", "data_aprobare", "tara",
        "adresa_cladire", "suprafata_m2", "stadiu_cladire",
        "nr_certificat_declarat", "epc_clasa", "epc_energie_finala", "epc_suprafata_m2"
    ]

    for camp in campuri_scalare:
        if camp not in date_mock:
            continue

        val_mock = extrage_valoare_camp(date_mock.get(camp))
        val_extras = extrage_valoare_camp(date_extras.get(camp))

        egal = sunt_egale_valori(val_mock, val_extras)
        inregistrare = {
            "camp": camp,
            "mock": val_mock,
            "extras": val_extras,
            "egal": egal,
        }

        if egal:
            potriviri.append(inregistrare)
        else:
            diferente.append(inregistrare)

    # Chiriași
    if "chiriasi" in date_mock:
        chiriasi_mock = date_mock["chiriasi"] or []
        chiriasi_extras = date_extras.get("chiriasi") or []
        egal_ch = len(chiriasi_mock) == len(chiriasi_extras)
        # Dacă numărul coincide, comparăm numele și m2
        if egal_ch and chiriasi_mock:
            for cm, ce in zip(chiriasi_mock, chiriasi_extras):
                if not (sunt_egale_aproximativ_text(cm.get("nume"), ce.get("nume")) and
                        sunt_egale_valori(cm.get("m2"), ce.get("m2"))):
                    egal_ch = False
                    break

        inr_ch = {
            "camp": "chiriasi (total)",
            "mock": f"{len(chiriasi_mock)} chiriași",
            "extras": f"{len(chiriasi_extras)} chiriași",
            "egal": egal_ch,
        }
        if egal_ch:
            potriviri.append(inr_ch)
        else:
            diferente.append(inr_ch)

    return potriviri, diferente


def ruleaza_comparatie(dosare_specificate: Optional[list[Path]] = None) -> int:
    """Execută compararea pe toate dosarele găsite."""
    radacina = Path(__file__).resolve().parent.parent

    if dosare_specificate:
        dosare = dosare_specificate
    else:
        cale_dosare = radacina / "dosare"
        dosare = sorted([
            p for p in cale_dosare.iterdir()
            if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("_")
        ])

    print("=" * 80)
    print(f"{'DOSAR':<35} | {'CÂMP':<22} | {'MOCK':<15} | {'EXTRAS':<15} | {'STATUS'}")
    print("=" * 80)

    total_diferente = 0

    for d in dosare:
        mock_file = d / "extras_mock.json"
        extras_file = d / "_extras" / "dosar_extras.json"

        if not mock_file.exists():
            print(f"[{d.name}] extras_mock.json lipsește!")
            continue
        if not extras_file.exists():
            print(f"[{d.name}] _extras/dosar_extras.json lipsește!")
            continue

        potriviri, diferente = compara_dosar(mock_file, extras_file)
        total_diferente += len(diferente)

        for item in potriviri:
            mock_str = str(item["mock"])[:14]
            ext_str = str(item["extras"])[:14]
            # print potriviri opțional sau doar pe scurt
            pass

        if not diferente:
            print(f"{d.name:<35} | {'(toate câmpurile)':<22} | {'-':<15} | {'-':<15} | OK ({len(potriviri)} potriviri)")
        else:
            for item in diferente:
                mock_str = str(item["mock"])[:14]
                ext_str = str(item["extras"])[:14]
                print(f"{d.name:<35} | {item['camp']:<22} | {mock_str:<15} | {ext_str:<15} | DIFERIT")

    print("=" * 80)
    print(f"Rezumat: {len(dosare)} dosare analizate, {total_diferente} diferențe găsite.")
    print("=" * 80)
    return total_diferente


def main() -> None:
    """Punct de intrare CLI pentru compara.py."""
    args = [Path(a).resolve() for a in sys.argv[1:]] if len(sys.argv) > 1 else None
    diffs = ruleaza_comparatie(args)
    # Ieșim cu 0 pentru a permite utilizarea ca utilitar de raportare
    sys.exit(0)


if __name__ == "__main__":
    main()
