"""Real-time RAG assistant.

Grounds answers in BOTH:
  * the static knowledge base (routing policy, sender registry, playbooks) via
    dense retrieval, and
  * a live snapshot of current traffic computed from DuckDB (per-brand bypass
    ratios, leaked revenue).

The live snapshot is injected as an extra retrieved "context" so the LLM (or
the extractive fallback) can answer operational questions like "which brands
are bypassing right now and what should I do?".
"""
from __future__ import annotations

from typing import List

from otp_sig.pipeline.realtime import brand_bypass_summary, overall_stats
from otp_sig.rag import llm
from otp_sig.rag.retriever import Retriever


def _live_context(top: int = 5) -> dict:
    stats = overall_stats()
    summary = brand_bypass_summary()
    lines = [
        f"Overall: {stats['total_events']} OTP events, "
        f"{stats['bypass_events']} on bypass routes "
        f"({stats['bypass_ratio']:.0%}), estimated revenue leakage "
        f"USD {stats['estimated_revenue_leakage_usd']}."
    ]
    for s in summary[:top]:
        lines.append(
            f"{s['brand']} ({s['sender_id']}): {s['bypass']}/{s['total']} bypass "
            f"({s['bypass_ratio']:.0%}), avg latency {s['avg_latency_ms']}ms, "
            f"leaked USD {s['leaked_revenue_usd']}."
        )
    return {"text": "\n".join(lines), "source": "live_traffic_snapshot", "score": 1.0}


class Assistant:
    def __init__(self, retriever: Retriever | None = None, use_live: bool = True):
        self.retriever = retriever or Retriever()
        self.use_live = use_live

    def build_contexts(self, question: str, k: int = 4) -> List[dict]:
        contexts = self.retriever.as_contexts(question, k=k)
        if self.use_live:
            try:
                contexts = [_live_context()] + contexts
            except Exception:
                pass  # warehouse not built yet -> KB-only answer
        return contexts

    def ask(self, question: str, k: int = 4) -> llm.Answer:
        contexts = self.build_contexts(question, k=k)
        return llm.answer(question, contexts)
