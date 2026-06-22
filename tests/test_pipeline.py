"""End-to-end tests for the OTP Signature Analytics pipeline (offline mode)."""
import pytest

from otp_sig.data import generate as datagen
from otp_sig.pipeline import index_kb as kb
from otp_sig.pipeline import realtime
from otp_sig.pipeline.signatures import extract_signature, is_otp_message
from otp_sig.rag.assistant import Assistant


@pytest.fixture(scope="module", autouse=True)
def built_pipeline():
    datagen.generate_all(n=600, seed=7)
    kb.index_kb()
    realtime.process_stream()
    yield


# --- data generation --------------------------------------------------------
def test_generate_events_shape():
    events = datagen.generate_events(n=100, seed=1)
    assert len(events) == 100
    e = events[0]
    for key in ["event_id", "message_text", "route_type", "is_bypass", "is_otp"]:
        assert key in e
    assert any(ev["is_bypass"] for ev in events), "expected some bypass traffic"
    assert any(not ev["is_bypass"] for ev in events), "expected some licensed traffic"


# --- signature extraction ---------------------------------------------------
def test_otp_detection():
    assert is_otp_message("Your HDFC Bank OTP is 482915. Valid 10 min.")
    assert not is_otp_message("Mega Sale is live! 70% off today only.")


def test_signature_collapses_codes():
    a = extract_signature("Your HDFC Bank OTP is 482915. Valid for 10 minutes.")
    b = extract_signature("Your HDFC Bank OTP is 119284. Valid for 10 minutes.")
    assert a.template_hash == b.template_hash
    assert a.code != b.code
    assert "<code>" in a.template_skeleton


# --- warehouse --------------------------------------------------------------
def test_warehouse_populated():
    stats = realtime.overall_stats()
    assert stats["total_events"] == 600
    assert stats["bypass_events"] > 0
    assert stats["estimated_revenue_leakage_usd"] > 0


def test_brand_summary_ratios():
    summary = realtime.brand_bypass_summary()
    assert summary
    for s in summary:
        assert 0.0 <= s["bypass_ratio"] <= 1.0
        assert s["bypass"] <= s["total"]


# --- RAG retrieval + assistant ---------------------------------------------
def test_retriever_finds_policy():
    a = Assistant(use_live=False)
    contexts = a.build_contexts("What routes are prohibited for OTP traffic?", k=3)
    joined = " ".join(c["text"].lower() for c in contexts)
    assert "bypass" in joined or "grey_route" in joined or "ott" in joined


def test_assistant_answers_with_sources():
    a = Assistant()
    ans = a.ask("Which brands are bypassing A2P and what should I do?")
    assert ans.backend == "extractive-fallback"  # forced offline in tests
    assert len(ans.text) > 0
    assert ans.sources  # at least the live snapshot or a KB doc
