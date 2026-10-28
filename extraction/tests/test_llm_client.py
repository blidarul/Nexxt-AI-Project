"""Teste unitare pentru funcționalitățile clientului LLM (cache, parsare JSON, curățare think)."""

import json
from pathlib import Path
import tempfile
import pytest

from extraction.llm_client import LLMClient


def test_curata_text_raspuns_think():
    text_cu_think = "<think>Aici este un raționament intern de la Qwen3.\nAnalizăm datele...</think>{\"rezultat\": 123}"
    curatat = LLMClient.curata_text_raspuns(text_cu_think)
    assert curatat == '{"rezultat": 123}'


def test_curata_text_raspuns_think_neterminat():
    text_cu_think = "<think>Raționament care a fost întrerupt brusc"
    curatat = LLMClient.curata_text_raspuns(text_cu_think)
    assert curatat == ""


def test_extrage_json_din_text():
    # 1. JSON pur
    assert LLMClient.extrage_json_din_text('{"a": 1, "b": "test"}') == {"a": 1, "b": "test"}

    # 2. Markdown bloc
    text_md = "Iată răspunsul:\n```json\n{\"suprafata\": 20000}\n```\nSper că ajută!"
    assert LLMClient.extrage_json_din_text(text_md) == {"suprafata": 20000}

    # 3. Text amestecat cu Qwen3 think
    text_complex = "<think>Am găsit 30 mil</think>Desigur, extrasul este:\n{\"suma\": 30000000}\nMulțumesc."
    assert LLMClient.extrage_json_din_text(text_complex) == {"suma": 30000000}

    # 4. Array JSON
    text_arr = "[{\"nume\": \"Alfa\"}, {\"nume\": \"Beta\"}]"
    assert LLMClient.extrage_json_din_text(text_arr) == [{"nume": "Alfa"}, {"nume": "Beta"}]

    # 5. Text invalid
    assert LLMClient.extrage_json_din_text("Nu am găsit niciun JSON aici.") is None


def test_cache_llm():
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = LLMClient(cache_dir=Path(tmp_dir))
        mesaje = [{"role": "user", "content": "ping"}]
        cheie = client._calculeaza_cheie_cache("model-test", mesaje, 0.0)

        # La început nu este în cache
        assert client._citeste_din_cache(cheie) is None

        # Salvăm un răspuns simulat în cache
        client._salveaza_in_cache(cheie, '{"raspuns": "pong"}', "model-test", mesaje)

        # Verificăm că acum este citit din cache
        citit = client._citeste_din_cache(cheie)
        assert citit == '{"raspuns": "pong"}'

        # Apelul prin apeleaza() trebuie să returneze valoarea din cache fără a face request HTTP real
        rezultat = client.apeleaza(mesaje, model="model-test", temperature=0.0)
        assert rezultat == '{"raspuns": "pong"}'
        stats = client.get_statistici()
        assert stats["apeluri_cache"] == 1
        assert stats["apeluri_reale"] == 0
