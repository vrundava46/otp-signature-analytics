"""LLM access layer with an always-available fallback.

``answer()`` builds a grounded prompt from retrieved context and tries Ollama.
On any failure (Ollama not installed/running, model missing, network error,
or ``FORCE_FALLBACK``) it transparently degrades to the deterministic
extractive answerer in ``fallback.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import config
from otp_sig.rag import fallback


@dataclass
class Answer:
    text: str
    backend: str  # "ollama:<model>" or "extractive-fallback"
    sources: List[str] = field(default_factory=list)


def ollama_available() -> bool:
    if config.FORCE_FALLBACK:
        return False
    try:
        import requests

        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_generate(prompt: str) -> str:
    import requests

    r = requests.post(
        f"{config.OLLAMA_HOST}/api/generate",
        json={"model": config.OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["response"].strip()


SYSTEM = (
    "You are an assistant for a mobile network operator's messaging team. "
    "You help detect A2P OTP traffic that bypasses licensed routes via OTT "
    "channels (WhatsApp/Telegram), SIM boxes, or grey routes. Answer ONLY from "
    "the provided context. Cite sources in square brackets. If the context is "
    "insufficient, say so."
)


def _build_prompt(question: str, contexts: List[dict]) -> str:
    blocks = []
    for c in contexts:
        blocks.append(f"[source: {c.get('source','?')}]\n{c['text']}")
    ctx = "\n\n".join(blocks)
    return f"{SYSTEM}\n\n=== CONTEXT ===\n{ctx}\n\n=== QUESTION ===\n{question}\n\n=== ANSWER ==="


def answer(question: str, contexts: List[dict]) -> Answer:
    sources = []
    for c in contexts:
        s = c.get("source")
        if s and s not in sources:
            sources.append(s)

    if ollama_available():
        try:
            text = _ollama_generate(_build_prompt(question, contexts))
            return Answer(text=text, backend=f"ollama:{config.OLLAMA_MODEL}", sources=sources)
        except Exception:
            pass  # fall through to extractive

    text = fallback.extractive_answer(question, contexts)
    return Answer(text=text, backend="extractive-fallback", sources=sources)
