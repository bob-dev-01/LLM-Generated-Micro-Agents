"""Registry adapter - SQLite (default, MVP). Implements the Registry port.

Stores the port-neutral logical record (ARCHITECTURE.md §7.2). The enterprise
Cosmos/PostgreSQL + Key Vault adapter stores the same logical record and is a
drop-in replacement (ADR-002) — the pipeline never knows which backend is used.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent_factory.schemas import AgentSpec, Decision, ValidationReport

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

-- Reusable agent repertoire: ONLY agents that passed validation are stored
-- here, so a routing hit is always a safe-to-execute agent.
CREATE TABLE IF NOT EXISTS agents (
    capability      TEXT PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    artifact_hash   TEXT NOT NULL,
    code_path       TEXT NOT NULL,
    entrypoint      TEXT NOT NULL,
    registered_at   TEXT
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

    def register_agent(
        self,
        capability: str,
        agent: AgentSpec,
        artifact_hash: str,
        registered_at: str | None = None,
    ) -> None:
        """Add a validated agent to the reusable repertoire (keyed by capability)."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agents
                (capability, agent_id, artifact_hash, code_path, entrypoint, registered_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    capability,
                    agent.agent_id,
                    artifact_hash,
                    agent.generated_code_path,
                    agent.expected_entrypoint,
                    registered_at,
                ),
            )

    def find_agent_by_capability(self, capability: str) -> AgentSpec | None:
        """Return a reusable agent for this capability, or None."""
        if not capability:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT agent_id, code_path, entrypoint FROM agents WHERE capability = ?",
                (capability,),
            ).fetchone()
        if row is None:
            return None
        return AgentSpec(
            agent_id=row[0],
            generated_code_path=row[1],
            expected_entrypoint=row[2],
            manifest={"source": "registry-reuse"},
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
