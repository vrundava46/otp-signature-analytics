"""Synthetic data generation for OTP Signature Analytics.

Produces two things:
  1. A stream of A2P SMS OTP events (JSONL) — the live traffic the real-time
     pipeline classifies. A configurable fraction of each brand's traffic is
     diverted onto bypass routes (OTT/SIM box/grey route), which is the signal
     the whole project is about.
  2. A small Markdown knowledge base the RAG assistant reasons over.

Everything is seeded so runs are reproducible and tests are deterministic.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import config

# Enterprise senders: (brand, sender_id, country, bypass_propensity)
# bypass_propensity = chance a message is routed off the licensed A2P channel.
BRANDS = [
    ("HDFC Bank", "VM-HDFCBK", "IN", 0.08),
    ("ICICI Bank", "VM-ICICIB", "IN", 0.06),
    ("Amazon", "AD-AMAZON", "IN", 0.35),   # heavy OTT bypass via aggregator
    ("Flipkart", "AD-FLPKRT", "IN", 0.30),
    ("Paytm", "VM-PAYTM", "IN", 0.20),
    ("Swiggy", "AD-SWIGGY", "IN", 0.45),   # worst offender
    ("Uber", "AD-UBER", "IN", 0.40),
    ("Google", "AD-GOOGLE", "US", 0.15),
    ("Netflix", "AD-NFLIX", "US", 0.25),
    ("WhatsApp", "AD-WHATSAPP", "US", 0.55),  # ironically self-routes via OTT
]

OTP_TEMPLATES = [
    "Your {brand} OTP is {code}. Valid for 10 minutes. Do not share with anyone.",
    "{code} is your {brand} verification code. Never share this code.",
    "Use OTP {code} to login to {brand}. This passcode expires in 5 min.",
    "{brand}: {code} is your one-time password. Do not disclose.",
    "Your {brand} secret code for this transaction is {code}.",
]

PROMO_TEMPLATES = [  # non-OTP noise
    "{brand}: Mega Sale is live! Up to 70% off. Shop now at our app.",
    "Hi from {brand}! Your weekend offer is waiting. Limited time only.",
]


def _route_for(bypass_propensity: float, rng: random.Random) -> str:
    if rng.random() < bypass_propensity:
        return rng.choice(["OTT_WHATSAPP", "OTT_TELEGRAM", "SIM_BOX", "GREY_ROUTE"])
    return "A2P_LICENSED"


def generate_events(n: int = 4000, seed: int = 42) -> List[Dict]:
    rng = random.Random(seed)
    start = datetime(2026, 6, 20, 9, 0, 0)
    events: List[Dict] = []
    for i in range(n):
        brand, sender, country, bp = rng.choice(BRANDS)
        is_otp = rng.random() < 0.85  # most A2P enterprise traffic is OTP
        code = f"{rng.randint(1000, 999999)}"
        if is_otp:
            text = rng.choice(OTP_TEMPLATES).format(brand=brand, code=code)
        else:
            text = rng.choice(PROMO_TEMPLATES).format(brand=brand)
        route = _route_for(bp if is_otp else bp * 0.3, rng)
        bypass = route in config.BYPASS_ROUTES
        # bypass routes are flakier and slower
        delivered = rng.random() < (0.90 if bypass else 0.985)
        latency = rng.randint(400, 4000) if bypass else rng.randint(80, 900)
        cost = 0.0 if bypass else config.A2P_RATE_USD
        ts = start + timedelta(seconds=i * rng.randint(1, 4))
        events.append(
            {
                "event_id": f"evt-{i:06d}",
                "timestamp": ts.isoformat(),
                "brand": brand,
                "sender_id": sender,
                "country": country,
                "message_text": text,
                "route_type": route,
                "is_bypass": bypass,
                "is_otp": is_otp,
                "delivered": delivered,
                "latency_ms": latency,
                "cost_to_mno_usd": cost,
            }
        )
    return events


def write_events(events: List[Dict], path: Path | None = None) -> Path:
    path = path or (config.RAW_DIR / "sms_events.jsonl")
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return path


# --------------------------------------------------------------------------
# Knowledge base
# --------------------------------------------------------------------------
KB_DOCS: Dict[str, str] = {
    "a2p_routing_policy.md": """# A2P SMS Routing Policy

## Licensed A2P routes
All enterprise (Application-to-Person) OTP traffic destined for our subscribers
MUST be delivered over a licensed A2P route via a contracted aggregator. The MNO
earns a termination fee of USD 0.0065 per delivered A2P message. Only the
`A2P_LICENSED` route type is revenue-bearing.

## Prohibited bypass routes
The following delivery paths are prohibited for enterprise OTP traffic because
they deprive the MNO of A2P revenue and evade content/sender-ID controls:

- `OTT_WHATSAPP` / `OTT_TELEGRAM`: OTP delivered over an Over-The-Top messaging
  app instead of SMS. Carries zero MNO revenue.
- `SIM_BOX`: A2P traffic injected from racks of consumer SIMs disguised as P2P
  to dodge A2P pricing.
- `GREY_ROUTE`: international rerouting and sender-ID spoofing to disguise the
  true origin of the traffic.

## Enforcement
Traffic on any bypass route should be flagged for the revenue-assurance and
fraud teams. Repeat offenders by `sender_id` are candidates for sender-ID
suspension pending commercial review.
""",
    "sender_id_registry.md": """# Sender ID Registry

Registered enterprise sender IDs and their licensed aggregator. Any message
bearing one of these sender IDs but observed on a non-A2P route is a strong
bypass indicator.

- VM-HDFCBK -> HDFC Bank (Financial, IN) — strict no-bypass SLA
- VM-ICICIB -> ICICI Bank (Financial, IN)
- AD-AMAZON -> Amazon (E-commerce, IN)
- AD-FLPKRT -> Flipkart (E-commerce, IN)
- VM-PAYTM  -> Paytm (Fintech, IN)
- AD-SWIGGY -> Swiggy (Food delivery, IN)
- AD-UBER   -> Uber (Mobility, IN)
- AD-GOOGLE -> Google (Tech, US)
- AD-NFLIX  -> Netflix (Streaming, US)
- AD-WHATSAPP -> WhatsApp/Meta (Tech, US)

Financial-sector sender IDs (banks, fintech) are highest priority: bypass of
banking OTP also raises a security/deliverability risk for the subscriber.
""",
    "otp_template_dlt_rules.md": """# OTP Template & DLT Rules

Under DLT (Distributed Ledger Technology) commercial-communication rules,
enterprise OTP templates must be pre-registered. A registered template is
identified by its normalised skeleton (the code and digits masked). Our
pipeline computes a `template_hash` from this skeleton.

## What makes a valid OTP template
- Contains an explicit OTP keyword (OTP, code, verification, passcode, PIN).
- Contains a 4–8 digit numeric code.
- Identifies the sending brand.
- States validity/expiry and a do-not-share warning.

## Signature monitoring
The pair `(sender_id, template_hash)` is a *signature*. A known signature
appearing on a bypass route, or a brand suddenly emitting an unregistered
template, indicates either bypass or template tampering.
""",
    "bypass_detection_playbook.md": """# Bypass Detection Playbook

How the messaging-ops team should react to bypass alerts.

## Real-time signals
- A registered sender ID observed on `OTT_WHATSAPP`, `OTT_TELEGRAM`, `SIM_BOX`
  or `GREY_ROUTE`.
- A brand's bypass ratio (bypass messages / total) rising above 15% in an hour.
- Elevated delivery latency (>1500 ms) or drop in delivery rate for OTP traffic,
  which often accompanies SIM-box and grey-route delivery.

## Triage steps
1. Confirm the sender ID is registered (see sender ID registry).
2. Quantify the leaked volume and lost A2P revenue for the window.
3. For financial-sector brands, escalate immediately to fraud + security.
4. Open a case for the aggregator responsible for the route.

## Lost revenue
Each OTP that should have been A2P but was delivered via a bypass route is a
loss of one A2P termination fee (USD 0.0065). Multiply leaked volume by the rate
to estimate revenue leakage for the period.
""",
}


def write_kb(kb_dir: Path | None = None) -> List[Path]:
    kb_dir = kb_dir or config.KB_DIR
    kb_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, body in KB_DOCS.items():
        p = kb_dir / name
        p.write_text(body)
        written.append(p)
    return written


def generate_all(n: int = 4000, seed: int = 42) -> dict:
    events = generate_events(n=n, seed=seed)
    ev_path = write_events(events)
    kb_paths = write_kb()
    return {"events": len(events), "events_path": str(ev_path), "kb_docs": len(kb_paths)}


if __name__ == "__main__":
    print(generate_all())
