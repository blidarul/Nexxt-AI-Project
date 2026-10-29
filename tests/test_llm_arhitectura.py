"""Teste unitare pentru noua arhitectură de apeluri LLM:

- Caching tiered (L1 RAM + L2 disc)
- Deduplicare concurentă (SingleFlight / request coalescing)
- Tool calling nativ și eliminare blocuri think
- Siguranță la scriere concurentă pe Windows (fără WinError 32)
- Metrice detaliate și raportare
- Optimizarea PlanificatorLLM (eliminare apeluri inutile de calcul impact)
- Endpoint-ul de metrice din UI server
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
import tempfile
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from contracts import Camp, DosarExtras, StareDosar
from extraction.llm_client import LLMClient, SingleFlight, get_llm_client
from agent.planner import Decizie, PlanificatorLLM


def test_singleflight_deduplicare_apeluri_concurente():
    """Verifică că 5 apeluri simultane pe aceeași cheie execută un singur apel real."""
    sf = SingleFlight()
    contor_executii = 0
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=5)

    def _operatie_lenta():
        nonlocal contor_executii
        contor_executii += 1
        time.sleep(0.05)
        return "rezultat_partajat"

    with pool as executor:
        futures = [
            executor.submit(sf.execute, "cheie_comuna", _operatie_lenta)
            for _ in range(5)
        ]
        rezultate = [f.result() for f in futures]

    # Toate cele 5 thread-uri au primit același rezultat
    assert all(r[0] == "rezultat_partajat" for r in rezultate)
    # Exact un singur thread a fost liderul care a executat funcția
    lideri = [r[1] for r in rezultate]
    assert lideri.count(True) == 1
    assert lideri.count(False) == 4
    # Funcția lentă a fost executată o singură dată
    assert contor_executii == 1


def test_cache_tiered_l1_si_l2():
    """Verifică stratul L1 în memorie (0ms) și stratul L2 persistent pe disc."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = LLMClient(cache_dir=Path(tmp_dir))
        mesaje = [{"role": "user", "content": "test context"}]
        cheie = client._calculeaza_cheie_cache("model-test", mesaje, 0.0)

        # Salvare în cache
        client._salveaza_in_cache(cheie, '{"raspuns": "ok"}', "model-test", mesaje)

        # 1. Prima citire: vine din L1 (RAM)
        resp1, sursa1 = client._citeste_din_cache_cu_sursa(cheie)
        assert resp1 == '{"raspuns": "ok"}'
        assert sursa1 == "l1"

        # 2. Golim explicit L1: a doua citire trebuie să vină din L2 (disc) și să re-populeze L1
        client._cache_l1.clear()
        resp2, sursa2 = client._citeste_din_cache_cu_sursa(cheie)
        assert resp2 == '{"raspuns": "ok"}'
        assert sursa2 == "l2"

        # 3. A treia citire: vine din nou din L1 (re-populat)
        resp3, sursa3 = client._citeste_din_cache_cu_sursa(cheie)
        assert resp3 == '{"raspuns": "ok"}'
        assert sursa3 == "l1"


def test_scriere_concurenta_cache_windows_safe():
    """Verifică că scrierea concurentă din 10 thread-uri nu generează WinError 32."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = LLMClient(cache_dir=Path(tmp_dir))

        def _scrie(index: int):
            cheie = f"cheie_test_{index}"
            client._salveaza_in_cache(cheie, f"raspuns_{index}", "model", [{"role": "user", "content": str(index)}])

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(_scrie, range(30)))

        # Toate cele 30 fișiere au fost scrise corect pe disc
        fisiere = list(Path(tmp_dir).glob("*.json"))
        assert len(fisiere) == 30


def test_apeleaza_cu_tools_caching_si_think_clean(monkeypatch):
    """Verifică tool calling-ul cu caching și eliminarea tagurilor think."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = LLMClient(cache_dir=Path(tmp_dir))
        client.api_key = "test_cheie"

        apeluri_facute = 0

        class MockChoice:
            class Message:
                content = "<think>Analizez starea dosarului...</think>Apelez verificarea firmei"
                tool_calls = [
                    type("ToolCall", (), {
                        "id": "call_1",
                        "type": "function",
                        "function": type("Function", (), {
                            "name": "verifica_firma",
                            "arguments": '{"cui": "123456"}',
                        })(),
                    })()
                ]
            message = Message()

        class MockResponse:
            choices = [MockChoice()]
            model = "Qwen/Qwen3-32B"

        def mock_create(**kwargs):
            nonlocal apeluri_facute
            apeluri_facute += 1
            return MockResponse()

        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = mock_create
        client._client = mock_openai

        mesaje = [{"role": "user", "content": "stare dosar"}]
        tools = [{"type": "function", "function": {"name": "verifica_firma", "parameters": {}}}]

        # 1. Primul apel: execută remote și salvează în cache
        content, tool_calls, model = client.apeleaza_cu_tools(mesaje, tools, motiv="test_planner")
        assert apeluri_facute == 1
        assert content == "Apelez verificarea firmei"
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "verifica_firma"

        # 2. Al doilea apel pe aceleași date: vine 100% din cache (0 apeluri remote)
        c2, t2, m2 = client.apeleaza_cu_tools(mesaje, tools, motiv="test_planner")
        assert apeluri_facute == 1  # neschimbat!
        assert c2 == content
        assert t2 == tool_calls

        stats = client.get_statistici_detaliate()
        assert stats["sumar"]["apeluri_reale"] == 1
        assert stats["sumar"]["apeluri_cache_total"] == 1
        assert "test_planner" in stats["pe_operatiuni"]


def test_statistici_si_raport_metrici():
    """Verifică colectarea metricilor detaliate și formatarea raportului."""
    client = LLMClient(cache_dir=Path(tempfile.mkdtemp()))
    client.reseteaza_statistici()

    client._inregistreaza_apel("clasificare_document", "Qwen/Qwen3-32B", "cache_l1", 0.1)
    client._inregistreaza_apel("clasificare_document", "Qwen/Qwen3-32B", "cache_l2", 1.2)
    client._inregistreaza_apel("stabileste_categoria", "Qwen/Qwen3-32B", "real", 1500.0)
    client._inregistreaza_apel("stabileste_categoria", "Qwen/Qwen3-32B", "singleflight", 1500.0)

    detalii = client.get_statistici_detaliate()
    assert detalii["pe_operatiuni"]["clasificare_document"]["total"] == 2
    assert detalii["pe_operatiuni"]["clasificare_document"]["cache_l1"] == 1
    assert detalii["pe_operatiuni"]["stabileste_categoria"]["real"] == 1
    assert detalii["pe_operatiuni"]["stabileste_categoria"]["singleflight"] == 1

    raport = client.raport_metrici()
    assert "RAPORT METRICI APELURI LLM" in raport
    assert "clasificare_document" in raport
    assert "stabileste_categoria" in raport


def test_planificator_llm_omite_calcul_impact_pe_dosar_neeligibil(monkeypatch):
    """Verifică că PlanificatorLLM nu apelează inutil calculează_impact pe dosare escaladate/neeligibile."""
    planificator = PlanificatorLLM()

    # Creăm un dosar escaladat (de exemplu cu semnal sau excludere)
    extras = DosarExtras(
        dosar_id="test_escaladat",
        cui=Camp(valoare="123456"),
        suma_eur=Camp(valoare=1000000),
        cota_banca=Camp(valoare=0.5),
        data_aprobare=Camp(valoare="2026-01-01"),
        tara=Camp(valoare="Romania"),
        adresa_cladire=Camp(valoare="Str. Test"),
        suprafata_m2=Camp(valoare=5000),
        stadiu_cladire=Camp(valoare="Finalizata"),
        nr_certificat_declarat=Camp(valoare="CERT-1"),
    )
    stare = StareDosar(dosar_folder="dosare/test", extras=extras)
    stare.rezultate_tools["verifica_firma"] = type("TR", (), {"gasit": True, "date": {}, "eroare": None, "sursa": "ANAF", "tool": "verifica_firma"})()
    stare.rezultate_tools["evalueaza_conditii_generale"] = type("TR", (), {"gasit": True, "date": {}, "eroare": None, "sursa": "reguli", "tool": "evalueaza_conditii_generale"})()
    stare.rezultate_tools["stabileste_categoria"] = type("TR", (), {"gasit": True, "date": {}, "eroare": None, "sursa": "categorii", "tool": "stabileste_categoria"})()
    stare.rezultate_tools["verifica_completitudine"] = type("TR", (), {"gasit": True, "date": {}, "eroare": None, "sursa": "completitudine", "tool": "verifica_completitudine"})()
    stare.rezultate_tools["cauta_certificat"] = type("TR", (), {"gasit": True, "date": {}, "eroare": None, "sursa": "BREEAM", "tool": "cauta_certificat"})()
    stare.rezultate_tools["evalueaza_categoria"] = type("TR", (), {"gasit": True, "date": {}, "eroare": None, "sursa": "reguli", "tool": "evalueaza_categoria"})()
    stare.rezultate_tools["verifica_plauzibilitate"] = type("TR", (), {"gasit": True, "date": {}, "eroare": None, "sursa": "plauzibilitate", "tool": "verifica_plauzibilitate"})()

    # Forțăm starea ca fiind escaladată
    stare.escaladat = True

    # Simulăm că LLM-ul ar încerca totuși să apeleze calculeaza_co2
    def mock_apeleaza_cu_tools(*args, **kwargs):
        return "", [{"function": {"name": "calculeaza_co2", "arguments": "{}"}}], "model"

    monkeypatch.setattr(planificator.llm_client, "apeleaza_cu_tools", mock_apeleaza_cu_tools)

    decizie = planificator.pas_urmator(stare)
    # Planificatorul trebuie să intercepteze apelul inutil și să finalizeze fără calcul de impact
    assert decizie.tip == "final"
    assert "fără calcul de impact" in decizie.motiv or "finalizare" in decizie.motiv.lower()


def test_ui_server_endpoint_metrici(tmp_path):
    """Verifică că serverul UI expune endpoint-ul /api/llm/statistici."""
    from ui.server import creeaza_app

    app = creeaza_app(folder_dosare=tmp_path / "dosare", folder_date=tmp_path / "date")
    client = TestClient(app)

    # 1. Interogare statistici
    resp = client.get("/api/llm/statistici")
    assert resp.status_code == 200
    date = resp.json()
    assert "sumar" in date
    assert "pe_operatiuni" in date
    assert "economii_estimate" in date

    # 2. Resetare statistici
    resp_reset = client.post("/api/llm/reseteaza_statistici")
    assert resp_reset.status_code == 200
    assert resp_reset.json()["status"] == "ok"
