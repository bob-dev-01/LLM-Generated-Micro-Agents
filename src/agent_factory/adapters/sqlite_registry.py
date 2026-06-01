"""Registry adapter - SQLite (default, MVP). Implements the Registry port.

Stores the port-neutral logical record (ARCHITECTURE.md §7.2). The enterprise
Cosmos/PostgreSQL + Key Vault adapter stores the same logical record and is a
drop-in replacement (ADR-002) — the pipeline never knows which backend is used.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent_factory.schemas import Decision, ValidationReport

_SCHEMA = """
CREATE TABLE IF NOT EXISTS validations (
    artifact_hash       TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL,
    agent_id            TEXT NOT NULL,
    final_decision      TEXT NOT NULL,
    condition           TEXT NOT NULL,
    validation_timestamp TEXT NOT NULL,
    report_path         TEXT,
    model_metadata      TEXT,
    hmac_signature      TEXT
);
"""


class SqliteRegistry:
    def __init__(self, db_path: str | Path = "data/registry.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def save(self, report: ValidationReport, report_path: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO validations
                (artifact_hash, task_id, agent_id, final_decision, condition,
                 validation_timestamp, report_path, model_metadata, hmac_signature)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.artifact_hash,
                    report.task_id,
                    report.agent_id,
                    report.final_decision.value,
                    report.condition,
                    report.created_at,
                    report_path,
                    json.dumps(report.model_metadata),
                    None,  # HMAC signing arrives with the Key Vault adapter (optional)
                ),
            )

    def get(self, artifact_hash: str) -> ValidationReport | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT artifact_hash, task_id, agent_id, final_decision, condition, "
                "validation_timestamp FROM validations WHERE artifact_hash = ?",
                (artifact_hash,),
            ).fetchone()
        if row is None:
            return None
        return ValidationReport(
            run_id="(from-registry)",
            task_id=row[1],
            agent_id=row[2],
            artifact_hash=row[0],
            condition=row[4],
            final_decision=Decision(row[3]),
            created_at=row[5],
        )
