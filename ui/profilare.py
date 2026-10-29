"""Profilare pentru o generare de raport (PROFILARE=1 în .env): timpul pe etape, fiecare apel LLM, fiecare tool.

Nu modifică logica: se agață din exterior de funcțiile existente (extracție, planificator, registry, verdict, raport)
și de clientul HTTP folosit de biblioteca openai, ca să prindă și reîncercările ei interne și erorile 429.
Fiecare generare scrie un JSON în ui/data/profil/.

    from ui import profilare
    profilare.activeaza()                       # o singură dată, idempotent
    with profilare.sesiune("dosar2", folder):    # o generare
        ...
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

RADACINA = Path(__file__).resolve().parent.parent
FOLDER_PROFIL = Path(__file__).resolve().parent / "data" / "profil"
_THINK = re.compile(r"<think>(.*?)(?:</think>|$)", re.DOTALL)

_lock = threading.Lock()
_activ = False
_sesiune: Optional[dict[str, Any]] = None
_stiva = threading.local()


def activata() -> bool:
    return os.getenv("PROFILARE", "").strip().lower() in ("1", "true", "da", "yes")


# ---------------------------------------------------------------- evenimente

def _adauga(tip: str, **date: Any) -> None:
    with _lock:
        if _sesiune is not None:
            _sesiune["evenimente"].append({"tip": tip, "t": round(time.perf_counter() - _sesiune["_t0"], 4), **date})


def _parinte() -> Optional[str]:
    stiva = getattr(_stiva, "etape", [])
    return stiva[-1] if stiva else None


def _modul_apelant() -> str:
    """Primul modul din proiect care a cerut apelul LLM (nu openai, nu llm_client, nu profilarea)."""
    for cadru in inspect.stack()[2:]:
        modul = cadru.frame.f_globals.get("__name__", "")
        if modul.split(".")[0] in ("extraction", "agent", "tools", "engine", "ui") and modul not in (
            "extraction.llm_client", __name__,
        ):
            return f"{modul}.{cadru.function}"
    return "?"


def _infasoara(obiect: Any, nume: str, eticheta: str, detalii: Optional[Callable[..., dict]] = None,
               inainte: Optional[Callable[..., dict]] = None) -> None:
    original = getattr(obiect, nume)
    if getattr(original, "_profilat", False):
        return

    @functools.wraps(original)
    def invelis(*args: Any, **kwargs: Any) -> Any:
        if _sesiune is None:
            return original(*args, **kwargs)
        stiva = _stiva.__dict__.setdefault("etape", [])
        parinte = stiva[-1] if stiva else None
        stiva.append(eticheta)
        stare_inainte = {}
        if inainte is not None:
            try:
                stare_inainte = inainte(args, kwargs) or {}
            except Exception as exc:  # noqa: BLE001
                stare_inainte = {"inainte_eroare": str(exc)[:200]}
        t0 = time.perf_counter()
        eroare = None
        rezultat = None
        try:
            rezultat = original(*args, **kwargs)
            return rezultat
        except Exception as exc:
            eroare = f"{type(exc).__name__}: {exc}"[:300]
            raise
        finally:
            stiva.pop()
            extra = {}
            if detalii is not None:
                try:
                    extra = detalii(args, kwargs, rezultat) or {}
                except Exception as exc:  # noqa: BLE001 - profilarea nu strică niciodată fluxul
                    extra = {"detalii_eroare": str(exc)[:200]}
            _adauga("etapa", etapa=eticheta, parinte=parinte, durata_s=round(time.perf_counter() - t0, 4),
                    eroare=eroare, **stare_inainte, **extra)

    invelis._profilat = True  # type: ignore[attr-defined]
    setattr(obiect, nume, invelis)


# ---------------------------------------------------------------- LLM

def _tokeni_think(text: str, tokeni_iesire: Optional[int]) -> dict[str, Any]:
    think = "".join(_THINK.findall(text or ""))
    total = len(text or "")
    estimat = round(tokeni_iesire * len(think) / total) if tokeni_iesire and total else None
    return {"caractere_iesire": total, "caractere_think": len(think), "tokeni_think_estimati": estimat}


def _agata_llm() -> None:
    from openai.resources.chat import completions

    original = completions.Completions.create
    if getattr(original, "_profilat", False):
        return

    @functools.wraps(original)
    def create(self: Any, *args: Any, **kwargs: Any) -> Any:
        if _sesiune is None:
            return original(self, *args, **kwargs)
        mesaje = kwargs.get("messages") or []
        caractere_intrare = sum(len(json.dumps(m.get("content"), ensure_ascii=False)) for m in mesaje)
        caractere_tools = len(json.dumps(kwargs.get("tools") or [], ensure_ascii=False))
        baza = {
            "modul": _modul_apelant(), "etapa": _parinte(), "model": kwargs.get("model"),
            "nr_mesaje": len(mesaje), "caractere_intrare": caractere_intrare, "caractere_scheme_tools": caractere_tools,
            "max_tokens": kwargs.get("max_tokens"), "timeout": kwargs.get("timeout"),
            "json_mode": "response_format" in kwargs,
        }
        t0 = time.perf_counter()
        try:
            raspuns = original(self, *args, **kwargs)
        except Exception as exc:
            _adauga("llm", sursa="real", durata_s=round(time.perf_counter() - t0, 3), eroare=f"{type(exc).__name__}: {exc}"[:300],
                    status=getattr(exc, "status_code", None), **baza)
            raise
        usage = getattr(raspuns, "usage", None)
        mesaj = raspuns.choices[0].message if getattr(raspuns, "choices", None) else None
        continut = (getattr(mesaj, "content", None) or "") if mesaj else ""
        rationament = getattr(mesaj, "reasoning_content", None) or getattr(mesaj, "reasoning", None) or ""
        tokeni_iesire = getattr(usage, "completion_tokens", None)
        _adauga(
            "llm", sursa="real", durata_s=round(time.perf_counter() - t0, 3), eroare=None,
            tokeni_intrare=getattr(usage, "prompt_tokens", None), tokeni_iesire=tokeni_iesire,
            finish_reason=raspuns.choices[0].finish_reason if getattr(raspuns, "choices", None) else None,
            tool_calls=len(getattr(mesaj, "tool_calls", None) or []) if mesaj else 0,
            caractere_rationament_separat=len(rationament),
            **_tokeni_think(continut, tokeni_iesire), **baza,
        )
        return raspuns

    create._profilat = True  # type: ignore[attr-defined]
    completions.Completions.create = create

    # fiecare cerere HTTP (inclusiv reîncercările interne ale bibliotecii openai și erorile 429)
    import httpx

    send_original = httpx.Client.send
    if not getattr(send_original, "_profilat", False):
        @functools.wraps(send_original)
        def send(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            if _sesiune is None or "/chat/completions" not in str(request.url):
                return send_original(self, request, *args, **kwargs)
            t0 = time.perf_counter()
            try:
                raspuns = send_original(self, request, *args, **kwargs)
            except Exception as exc:
                _adauga("http", status=None, durata_s=round(time.perf_counter() - t0, 3), eroare=type(exc).__name__)
                raise
            _adauga("http", status=raspuns.status_code, durata_s=round(time.perf_counter() - t0, 3), eroare=None)
            return raspuns

        send._profilat = True  # type: ignore[attr-defined]
        httpx.Client.send = send

    from extraction import llm_client

    cache_original = llm_client.LLMClient._citeste_din_cache
    if not getattr(cache_original, "_profilat", False):
        def citeste_din_cache(self: Any, cheie: str) -> Optional[str]:
            raspuns = cache_original(self, cheie)
            if _sesiune is not None and not self.offline:
                _adauga("llm", sursa="cache" if raspuns is not None else "cache_ratat", modul=_modul_apelant(),
                        etapa=_parinte(), durata_s=0.0)
            return raspuns

        citeste_din_cache._profilat = True  # type: ignore[attr-defined]
        llm_client.LLMClient._citeste_din_cache = citeste_din_cache


# ---------------------------------------------------------------- etape

def _agata_etape() -> None:
    import registry
    from agent import orchestrator, planner
    from extraction import extractor, extrage_structurat
    import ui.server

    def detalii_extractie(args: tuple, kwargs: dict) -> dict:
        folder = Path(args[0] if args else kwargs.get("folder_dosar"))
        return {"extras_existent": (folder / "_extras" / "dosar_extras.json").exists(),
                "force_reload": bool(kwargs.get("force_reload"))}

    def detalii_tool(args: tuple, kwargs: dict, rezultat: Any) -> dict:
        from config import MOD_TOOLS
        sursa = str(getattr(rezultat, "sursa", "") or "")
        return {"tool": args[0] if args else kwargs.get("nume"), "mod_tools": MOD_TOOLS,
                "cache": "cache local" in sursa.lower(), "sursa_tool": sursa[:120],
                "gasit": getattr(rezultat, "gasit", None)}

    def detalii_decizie(args: tuple, kwargs: dict, rezultat: Any) -> dict:
        return {"decizie": getattr(rezultat, "nume", None) or getattr(rezultat, "tip", None)}

    # extracția (rulează doar dacă _extras/ lipsește)
    _infasoara(extractor, "extrage", "extractie", inainte=detalii_extractie)
    _infasoara(orchestrator, "_extrage", "agent.incarcare_extras")
    _infasoara(extrage_structurat, "incarca_documente_brute", "extractie.citire_bruta")
    _infasoara(extrage_structurat, "ruleaza_etapa_1", "extractie.citire_bruta.pdf_ocr")
    _infasoara(extrage_structurat, "clasifica_document", "extractie.clasificare")
    _infasoara(extrage_structurat, "stabileste_categoria", "extractie.categorie")
    _infasoara(extrage_structurat, "extrage_campuri_document_llm", "extractie.campuri_llm")
    _infasoara(extrage_structurat, "proceseaza_dosar_structurat", "extractie.total")
    # agentul: fiecare decizie a planificatorului și fiecare pas executat prin registry
    _infasoara(planner.PlanificatorLLM, "pas_urmator", "agent.decizie_llm", detalii_decizie)
    _infasoara(planner.PlanificatorScriptat, "pas_urmator", "agent.decizie_scriptata", detalii_decizie)
    _infasoara(registry, "apeleaza", "agent.pas", detalii_tool)
    _infasoara(orchestrator, "_decide_verdict", "motor.verdict")
    _infasoara(orchestrator, "proceseaza_dosar", "agent.total")
    # raportul din interfață
    _infasoara(ui.server, "construieste_raport", "ui.raport")
    _infasoara(ui.server, "stare_pas", "ui.stare_pas")


def activeaza() -> bool:
    """Instalează profilarea dacă PROFILARE=1. Idempotent."""
    global _activ
    if not activata():
        return False
    with _lock:
        if _activ:
            return True
        _activ = True
    _agata_llm()
    _agata_etape()
    return True


# ---------------------------------------------------------------- sesiune și raport

def _dimensiuni() -> dict[str, Any]:
    """Ce crește de la o generare la alta: cache-uri, rezultate, decizii, profiluri."""
    def folder(cale: Path) -> dict[str, int]:
        fisiere = [p for p in cale.rglob("*") if p.is_file()] if cale.exists() else []
        return {"fisiere": len(fisiere), "octeti": sum(p.stat().st_size for p in fisiere)}

    from extraction.llm_client import get_llm_client
    return {
        "cache_llm": folder(get_llm_client().cache_dir),
        "cache_tools": folder(RADACINA / "tools" / "cache"),
        "ui_data": folder(Path(__file__).resolve().parent / "data"),
    }


def rezuma(sesiune: dict[str, Any]) -> dict[str, Any]:
    ev = sesiune["evenimente"]
    etape: dict[str, dict[str, float]] = {}
    for e in ev:
        if e["tip"] == "etapa":
            x = etape.setdefault(e["etapa"], {"nr": 0, "durata_s": 0.0})
            x["nr"] += 1
            x["durata_s"] = round(x["durata_s"] + e["durata_s"], 3)
    llm_real = [e for e in ev if e["tip"] == "llm" and e.get("sursa") == "real"]
    http = [e for e in ev if e["tip"] == "http"]
    return {
        "durata_totala_s": sesiune.get("durata_totala_s"),
        "etape": etape,
        "llm": {
            "apeluri_reale": len(llm_real),
            "apeluri_cache": sum(1 for e in ev if e["tip"] == "llm" and e.get("sursa") == "cache"),
            "durata_llm_s": round(sum(e["durata_s"] for e in llm_real), 3),
            "tokeni_intrare": sum(e.get("tokeni_intrare") or 0 for e in llm_real),
            "tokeni_iesire": sum(e.get("tokeni_iesire") or 0 for e in llm_real),
            "tokeni_think_estimati": sum(e.get("tokeni_think_estimati") or 0 for e in llm_real),
            "erori": sum(1 for e in llm_real if e.get("eroare")),
            "cereri_http": len(http),
            "http_429": sum(1 for e in http if e.get("status") == 429),
            "reincercari_http": max(0, len(http) - len(llm_real)),
            "pe_modul": _pe_cheie(llm_real, "modul"),
        },
        "tools": [{k: e.get(k) for k in ("tool", "durata_s", "mod_tools", "cache", "gasit")}
                  for e in ev if e["tip"] == "etapa" and e["etapa"] == "agent.pas"],
        "refacut_inutil": {
            "extractie_rulata_desi_exista_extras": sum(
                1 for e in ev if e["tip"] == "etapa" and e["etapa"] == "extractie" and e.get("extras_existent")
                and any(x["tip"] == "etapa" and x["etapa"] == "extractie.total" for x in ev)),
        },
    }


def _pe_cheie(evenimente: list[dict[str, Any]], cheie: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in evenimente:
        x = out.setdefault(str(e.get(cheie)), {"apeluri": 0, "durata_s": 0.0, "tokeni_intrare": 0, "tokeni_iesire": 0})
        x["apeluri"] += 1
        x["durata_s"] = round(x["durata_s"] + e["durata_s"], 3)
        x["tokeni_intrare"] += e.get("tokeni_intrare") or 0
        x["tokeni_iesire"] += e.get("tokeni_iesire") or 0
    return out


@contextmanager
def sesiune(dosar_id: str, eticheta: str = "", folder_profil: Path = FOLDER_PROFIL) -> Iterator[Optional[dict[str, Any]]]:
    """O generare profilată; scrie ui/data/profil/<dosar>_<moment>.json la final. Fără PROFILARE=1 nu face nimic."""
    global _sesiune
    if not activeaza():
        yield None
        return
    s: dict[str, Any] = {"dosar": dosar_id, "eticheta": eticheta, "inceput": datetime.now().isoformat(timespec="seconds"),
                         "_t0": time.perf_counter(), "evenimente": [], "dimensiuni_inainte": _dimensiuni()}
    with _lock:
        _sesiune = s
    try:
        yield s
    finally:
        with _lock:
            _sesiune = None
        s["durata_totala_s"] = round(time.perf_counter() - s.pop("_t0"), 3)
        s["dimensiuni_dupa"] = _dimensiuni()
        s["rezumat"] = rezuma(s)
        try:
            folder_profil.mkdir(parents=True, exist_ok=True)
            nume = f"{dosar_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{('_' + eticheta) if eticheta else ''}.json"
            (folder_profil / nume).write_text(json.dumps(s, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            s["fisier"] = str(folder_profil / nume)
        except OSError:
            pass
