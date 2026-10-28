"""Configurații globale ale sistemului, încărcate din .env."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

# Valori permise și implicite
MOD_EXTRACTIE = os.getenv("MOD_EXTRACTIE", "mock").strip().lower()
if MOD_EXTRACTIE not in ("mock", "real"):
    raise ValueError(f"MOD_EXTRACTIE invalid: {MOD_EXTRACTIE!r}. Valori permise: 'mock', 'real'.")

MOD_TOOLS = os.getenv("MOD_TOOLS", "offline").strip().lower()
if MOD_TOOLS not in ("offline", "online"):
    raise ValueError(f"MOD_TOOLS invalid: {MOD_TOOLS!r}. Valori permise: 'offline', 'online'.")

MOD_AGENT = os.getenv("MOD_AGENT", "scriptat").strip().lower()
if MOD_AGENT not in ("scriptat", "llm"):
    raise ValueError(f"MOD_AGENT invalid: {MOD_AGENT!r}. Valori permise: 'scriptat', 'llm'.")

DATA_ALOCARE = os.getenv("DATA_ALOCARE", "2026-10-28").strip()

_raw_max_pasi = os.getenv("MAX_PASI_AGENT", "15").strip()
try:
    MAX_PASI_AGENT = int(_raw_max_pasi)
except ValueError as e:
    raise ValueError(f"MAX_PASI_AGENT trebuie sa fie un numar intreg valid, primit: {_raw_max_pasi!r}") from e

if MAX_PASI_AGENT <= 0:
    raise ValueError(f"MAX_PASI_AGENT trebuie sa fie un intreg pozitiv (> 0), primit: {MAX_PASI_AGENT}")

# Chei opționale pentru servicii LLM
FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "").strip().strip('"').strip("'")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.featherless.ai/v1").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL_TEXT = os.getenv("LLM_MODEL_TEXT", "Qwen/Qwen3-32B").strip()
LLM_MODEL_VISION = os.getenv("LLM_MODEL_VISION", "google/gemma-3-27b-it").strip()
