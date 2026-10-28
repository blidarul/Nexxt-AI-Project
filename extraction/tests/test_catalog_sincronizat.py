"""Test automat de sincronizare între cerinte_dosar.yaml și campuri.yaml."""

import pytest
from extraction.verifica_catalog import verifica_sincronizare_catalog


def test_toate_campurile_cerinte_in_catalog():
    """Verifică că orice câmp din cerinte_dosar.yaml este descris în campuri.yaml."""
    lipsa = verifica_sincronizare_catalog()
    assert lipsa == [], f"Câmpuri din cerinte_dosar.yaml lipsă din campuri.yaml: {lipsa}"
