# OTP Signature Analytics — Real-Time RAG Assistant

A **real-time AI assistant (RAG)** that monitors a live stream of A2P SMS OTP
traffic, fingerprints each message's **signature**, and flags traffic that is
**bypassing licensed A2P routes** — delivered instead over OTT apps (WhatsApp /
Telegram), SIM boxes, or grey routes. Each bypassed OTP is lost A2P revenue for
the Mobile Network Operator (MNO).

The assistant answers operator questions grounded in **both** a routing/
regulation knowledge base **and** a live snapshot of current traffic.

> Part 1 of 3 in the *Telecom RAG* series. See also `otp-fraud-management`
> (multi-document RAG) and `mno-revenue-assurance` (agentic RAG).

---

## What it does

```
            synthetic generator                      knowledge base (Markdown)
          (SMS OTP events, JSONL)              routing policy · sender registry
                    │                          DLT rules · bypass playbook
                    ▼                                       │
        ┌───────────────────────┐                          ▼
        │  stream_simulator      │              ┌───────────────────────┐
        │  (producer, throttled) │              │ index_kb (chunk+embed) │
        └───────────┬───────────┘              └───────────┬───────────┘
                    ▼                                       ▼
        ┌───────────────────────┐                ┌───────────────────┐
        │ realtime consumer      │                │  Vector store      │
        │ • OTP + signature      │                │  (numpy cosine)    │
        │ • bypass detection     │                └─────────┬─────────┘
        │ • rolling alerts       │                          │
        │ → DuckDB warehouse     │                          │
        └───────────┬───────────┘                          │
                    │   live traffic snapshot               │ KB retrieval
                    └───────────────┬───────────────────────┘
                                    ▼
                        ┌───────────────────────┐
                        │  RAG Assistant         │
                        │  Ollama  ─or─          │
                        │  extractive fallback   │
                        └───────────┬───────────┘
                                    ▼
                          CLI  ·  Streamlit chat UI
```

**Signature** = a normalised template fingerprint. We mask the code/digits so
`"Your HDFC OTP is 482915"` and `"...is 119284"` collapse to the same
`template_hash`. The pair `(sender_id, template_hash)` identifies a brand's
template. The same signature seen on a **non-A2P route** is the core bypass
signal.

---

## Quick start

```bash
cd otp-signature-analytics
make setup          # creates .venv and installs deps (light: numpy/duckdb/typer...)
make pipeline       # generate data -> index KB -> ingest stream into DuckDB
make stats          # per-brand bypass ratios + estimated revenue leakage
make ask Q="Which brands are bypassing A2P via OTT and what should we do?"
make ui             # launch the Streamlit dashboard + chat
make test           # 7 tests, fully offline & deterministic
```

It **works with zero API keys and no Ollama** — the LLM layer falls back to a
deterministic extractive answerer, and embeddings fall back to a hashing
vectorizer if `sentence-transformers` isn't installed.

### Optional: better answers with a local LLM
```bash
./setup_ollama.sh   # installs Ollama + pulls llama3.2:3b
```
The assistant auto-detects Ollama and uses it; otherwise it stays in offline
mode. Better embeddings come free once `sentence-transformers` is installed
(it's in `requirements.txt`).

---

## Layout

```
otp_sig/
  config.py                 paths, model names, domain constants
  data/generate.py          synthetic SMS events + Markdown KB
  pipeline/
    stream_simulator.py     local stand-in for Kafka/Kinesis
    signatures.py           OTP detection + template fingerprinting
    realtime.py             stream consumer -> DuckDB + rolling alerts
    index_kb.py             chunk + embed KB (incremental by content hash)
  rag/
    embeddings.py           sentence-transformers OR hashing fallback
    vector_store.py         persistent numpy cosine store
    chunking.py             heading-aware Markdown chunker
    retriever.py            dense retrieval over the KB
    llm.py                  Ollama with extractive fallback
    fallback.py             deterministic offline answerer
    assistant.py            KB retrieval + live snapshot -> Answer
  app/
    cli.py                  typer CLI (generate/index/ingest/stats/ask)
    streamlit_app.py        dashboard + chat
tests/                      pytest (offline)
```

## Data engineering notes
- **Stream simulator** mimics a broker so the consumer code matches a real
  deployment; swap `stream_events()` for a Kafka consumer with no other changes.
- **DuckDB** is the analytical warehouse (zero-ops, file-based). The `events`
  table holds enriched, signature-tagged records.
- **Incremental indexing**: KB chunks are keyed by content hash, so re-running
  `index` only embeds changed/new content.

## Configuration (env vars)
| Var | Default | Purpose |
|-----|---------|---------|
| `TELCO_RAG_FORCE_FALLBACK` | `0` | `1` forces offline LLM + hashing embeddings |
| `TELCO_OLLAMA_MODEL` | `llama3.2:3b` | Ollama model name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `TELCO_EMBED_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
