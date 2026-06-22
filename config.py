"""Central configuration for the OTP Signature Analytics project.

All paths are derived from this file so the project is relocatable. Runtime
behaviour (LLM backend, embedding backend) is controlled by environment
variables so the same code runs in a rich local setup or a bare CI box.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths ------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data_store"
RAW_DIR = DATA_DIR / "raw"
KB_DIR = DATA_DIR / "kb"
STREAM_DIR = DATA_DIR / "stream"
WAREHOUSE = DATA_DIR / "analytics.duckdb"
VECTOR_DIR = DATA_DIR / "vectors"

for _d in (DATA_DIR, RAW_DIR, KB_DIR, STREAM_DIR, VECTOR_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Models -----------------------------------------------------------------
EMBED_MODEL = os.environ.get("TELCO_EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM_FALLBACK = 256  # dim of the deterministic hashing embedder

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("TELCO_OLLAMA_MODEL", "llama3.2:3b")

# When set, the LLM and embedding layers skip heavy/network backends and use
# their deterministic fallbacks. Tests set this so they run anywhere.
FORCE_FALLBACK = os.environ.get("TELCO_RAG_FORCE_FALLBACK", "0") == "1"

# --- Domain constants -------------------------------------------------------
# Route types an OTP message can take. Only A2P_LICENSED earns the MNO revenue.
ROUTE_TYPES = ["A2P_LICENSED", "OTT_WHATSAPP", "OTT_TELEGRAM", "SIM_BOX", "GREY_ROUTE"]
BYPASS_ROUTES = {"OTT_WHATSAPP", "OTT_TELEGRAM", "SIM_BOX", "GREY_ROUTE"}

# Per-message A2P revenue the MNO earns when traffic is correctly routed.
A2P_RATE_USD = 0.0065
