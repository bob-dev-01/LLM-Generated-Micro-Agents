"""Telemetry adapter - JSONL (default, MVP). Implements the TelemetrySink port.

Append-only, one line per run, carrying enough provenance to reconstruct any
run (ARCHITECTURE.md §7.3). Analyzed later with DuckDB / pandas. The optional
OpenTelemetry / App Insights adapter sits behind this same port.
"""

from __future__ import annotations

import json
from pathlib import Path


class JsonlTelemetry:
    def __init__(self, path: str | Path = "data/telemetry.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
