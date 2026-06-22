"""Local streaming simulator.

Stands in for Kafka/Kinesis on a single machine. Reads the generated event log
and yields events one at a time, optionally sleeping to mimic real-time arrival.
A thin producer/consumer abstraction so the real-time pipeline code looks the
same as it would against a real broker.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator, Optional

import config


def stream_events(
    path: Optional[Path] = None,
    limit: Optional[int] = None,
    rate_per_sec: float = 0.0,
) -> Iterator[dict]:
    """Yield events from the JSONL log.

    rate_per_sec=0 means as-fast-as-possible (used by ETL/tests). A positive
    value throttles to roughly that many events/second to mimic a live feed.
    """
    path = path or (config.RAW_DIR / "sms_events.jsonl")
    delay = (1.0 / rate_per_sec) if rate_per_sec > 0 else 0.0
    with open(path) as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            yield json.loads(line)
            if delay:
                time.sleep(delay)
