"""Streamlit UI: real-time bypass dashboard + RAG chat assistant.

Run with:  streamlit run otp_sig/app/streamlit_app.py
(from the project root, after `make pipeline`).
"""
from __future__ import annotations

import sys
from pathlib import Path

# allow running via `streamlit run otp_sig/app/streamlit_app.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402  (streamlit ships pandas)
import streamlit as st  # noqa: E402

from otp_sig.pipeline import realtime  # noqa: E402
from otp_sig.rag import llm  # noqa: E402
from otp_sig.rag.assistant import Assistant  # noqa: E402

st.set_page_config(page_title="OTP Signature Analytics", layout="wide")
st.title("📡 OTP Signature Analytics — Real-Time A2P Bypass Assistant")

backend = "Ollama" if llm.ollama_available() else "Extractive fallback (offline)"
st.caption(f"LLM backend: **{backend}**  ·  Detecting OTP traffic that bypasses licensed A2P routes via OTT / SIM-box / grey routes.")

# --- live dashboard ---------------------------------------------------------
try:
    overall = realtime.overall_stats()
    summary = realtime.brand_bypass_summary()
except Exception:
    st.warning("Warehouse not built yet. Run `make pipeline` first.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("OTP events", overall["total_events"])
c2.metric("On bypass routes", f"{overall['bypass_events']} ({overall['bypass_ratio']:.0%})")
c3.metric("Est. revenue leakage", f"${overall['estimated_revenue_leakage_usd']}")

df = pd.DataFrame(summary)
if not df.empty:
    st.subheader("Per-brand bypass")
    st.bar_chart(df.set_index("brand")["bypass_ratio"])
    st.dataframe(df, use_container_width=True)

# --- chat assistant ---------------------------------------------------------
st.subheader("💬 Ask the assistant")
st.caption("Grounded in the routing/regulation KB + the live traffic snapshot.")

if "history" not in st.session_state:
    st.session_state.history = []

for q, a in st.session_state.history:
    with st.chat_message("user"):
        st.write(q)
    with st.chat_message("assistant"):
        st.write(a)

prompt = st.chat_input("e.g. Which brands are bypassing A2P and what should we do?")
if prompt:
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Retrieving + reasoning..."):
            ans = Assistant().ask(prompt)
        st.write(ans.text)
        st.caption(f"backend: {ans.backend} · sources: {', '.join(ans.sources)}")
    st.session_state.history.append((prompt, ans.text))
