"""Real-time processing of the SMS event stream.

For each event we extract the OTP signature, decide whether it is on a bypass
route, and persist the enriched record to DuckDB. We also maintain rolling,
per-brand counters so the assistant can answer "what's happening right now"
without scanning the whole table. Alerts fire when a brand's bypass ratio
crosses a threshold.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import duckdb

import config
from otp_sig.pipeline.signatures import extract_signature
from otp_sig.pipeline.stream_simulator import stream_events

BYPASS_RATIO_ALERT = 0.15

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT, timestamp TIMESTAMP, brand TEXT, sender_id TEXT, country TEXT,
    route_type TEXT, is_bypass BOOLEAN, is_otp BOOLEAN, delivered BOOLEAN,
    latency_ms INTEGER, cost_to_mno_usd DOUBLE, template_hash TEXT
);
"""


@dataclass
class BrandCounter:
    total: int = 0
    bypass: int = 0
    otp: int = 0
    leaked_revenue: float = 0.0
    latency_sum: int = 0

    @property
    def bypass_ratio(self) -> float:
        return self.bypass / self.total if self.total else 0.0


@dataclass
class StreamResult:
    processed: int
    alerts: List[dict] = field(default_factory=list)
    brands: Dict[str, BrandCounter] = field(default_factory=dict)


def connect(db_path: Optional[str] = None) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path or config.WAREHOUSE))


def _enrich(ev: dict) -> dict:
    sig = extract_signature(ev["message_text"])
    return {
        "event_id": ev["event_id"],
        "timestamp": ev["timestamp"],
        "brand": ev["brand"],
        "sender_id": ev["sender_id"],
        "country": ev["country"],
        "route_type": ev["route_type"],
        "is_bypass": bool(ev["is_bypass"]),
        "is_otp": bool(sig.is_otp),
        "delivered": bool(ev["delivered"]),
        "latency_ms": int(ev["latency_ms"]),
        "cost_to_mno_usd": float(ev["cost_to_mno_usd"]),
        "template_hash": sig.template_hash,
    }


def process_stream(
    limit: Optional[int] = None,
    rate_per_sec: float = 0.0,
    db_path: Optional[str] = None,
    events: Optional[Iterable[dict]] = None,
) -> StreamResult:
    """Consume the stream, persist enriched events, and surface alerts."""
    con = connect(db_path)
    con.execute(SCHEMA)
    con.execute("DELETE FROM events")

    counters: Dict[str, BrandCounter] = defaultdict(BrandCounter)
    alerted: set = set()
    alerts: List[dict] = []
    rows: List[tuple] = []

    src = events if events is not None else stream_events(limit=limit, rate_per_sec=rate_per_sec)
    n = 0
    for ev in src:
        r = _enrich(ev)
        rows.append(tuple(r.values()))
        c = counters[r["brand"]]
        c.total += 1
        c.otp += int(r["is_otp"])
        c.latency_sum += r["latency_ms"]
        if r["is_bypass"]:
            c.bypass += 1
            if r["is_otp"]:
                c.leaked_revenue += config.A2P_RATE_USD
        # real-time alerting once a brand has meaningful volume
        if (
            c.total >= 50
            and c.bypass_ratio >= BYPASS_RATIO_ALERT
            and r["brand"] not in alerted
        ):
            alerted.add(r["brand"])
            alerts.append(
                {
                    "brand": r["brand"],
                    "sender_id": r["sender_id"],
                    "bypass_ratio": round(c.bypass_ratio, 3),
                    "message": f"{r['brand']} bypass ratio {c.bypass_ratio:.0%} exceeds {BYPASS_RATIO_ALERT:.0%}",
                }
            )
        n += 1

    if rows:
        con.executemany(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
    con.close()
    return StreamResult(processed=n, alerts=alerts, brands=dict(counters))


# --- query helpers used by the assistant -----------------------------------
def brand_bypass_summary(db_path: Optional[str] = None) -> List[dict]:
    con = connect(db_path)
    try:
        rows = con.execute(
            """
            SELECT brand, sender_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN is_bypass THEN 1 ELSE 0 END) AS bypass,
                   ROUND(AVG(latency_ms)) AS avg_latency_ms,
                   ROUND(SUM(CASE WHEN is_bypass AND is_otp THEN ? ELSE 0 END), 2) AS leaked_revenue_usd
            FROM events GROUP BY brand, sender_id
            ORDER BY bypass DESC
            """,
            [config.A2P_RATE_USD],
        ).fetchall()
    finally:
        con.close()
    out = []
    for brand, sender, total, bypass, lat, leaked in rows:
        out.append(
            {
                "brand": brand,
                "sender_id": sender,
                "total": int(total),
                "bypass": int(bypass or 0),
                "bypass_ratio": round((bypass or 0) / total, 3) if total else 0.0,
                "avg_latency_ms": int(lat or 0),
                "leaked_revenue_usd": float(leaked or 0.0),
            }
        )
    return out


def overall_stats(db_path: Optional[str] = None) -> dict:
    con = connect(db_path)
    try:
        row = con.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN is_bypass THEN 1 ELSE 0 END),
                   ROUND(SUM(CASE WHEN is_bypass AND is_otp THEN ? ELSE 0 END), 2)
            FROM events
            """,
            [config.A2P_RATE_USD],
        ).fetchone()
    finally:
        con.close()
    total, bypass, leaked = row
    total = int(total or 0)
    return {
        "total_events": total,
        "bypass_events": int(bypass or 0),
        "bypass_ratio": round((bypass or 0) / total, 3) if total else 0.0,
        "estimated_revenue_leakage_usd": float(leaked or 0.0),
    }
