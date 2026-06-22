# OTP Signature Analytics — developer commands
# A local virtualenv keeps this isolated from your base Anaconda environment.

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
export TELCO_RAG_FORCE_FALLBACK ?= 0

.PHONY: help setup setup-embeddings data index ingest pipeline stats ask test ui clean

help:
	@echo "make setup     - create .venv and install dependencies"
	@echo "make pipeline  - generate data -> index KB -> ingest stream"
	@echo "make stats     - show per-brand bypass + revenue leakage"
	@echo "make ask Q='..'- ask the assistant a question"
	@echo "make ui        - launch the Streamlit app"
	@echo "make test      - run the test suite (offline, deterministic)"
	@echo "make clean     - remove generated data & vectors"

setup:
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt
	@echo "Done. Optional: 'make setup-embeddings' (better retrieval) and './setup_ollama.sh' (nicer answers)."

setup-embeddings:
	$(PIP) install -q -r requirements-embeddings.txt

data:
	$(PY) -m otp_sig.app.cli generate

index:
	$(PY) -m otp_sig.app.cli index

ingest:
	$(PY) -m otp_sig.app.cli ingest

pipeline:
	$(PY) -m otp_sig.app.cli pipeline

stats:
	$(PY) -m otp_sig.app.cli stats

ask:
	$(PY) -m otp_sig.app.cli ask "$(Q)"

ui:
	$(VENV)/bin/streamlit run otp_sig/app/streamlit_app.py

test:
	TELCO_RAG_FORCE_FALLBACK=1 $(PY) -m pytest -q

clean:
	rm -rf data_store
