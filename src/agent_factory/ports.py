"""Ports (interfaces) — the seam between the domain core and infrastructure.

See ARCHITECTURE.md §4 / ADR-001 (Ports & Adapters). The pipeline core depends
ONLY on these Protocols, never on concrete infrastructure. MVP adapters
(SQLite, JSONL, local Docker) and enterprise adapters (Cosmos, Key Vault, Azure
OpenAI) are interchangeable implementations behind the same ports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from agent_factory.schemas import (
    AgentSpec,
    JudgeResult,
    LayerResult,
    SandboxResult,
    TaskSpec,
    ValidationReport,
)


@dataclass
class ValidationContext:
    """Carried through the pipeline; layers read inputs and append their results."""

    task_spec: TaskSpec
    agent_spec: AgentSpec
    artifact_hash: str
    source_code: str
    results: list[LayerResult] = field(default_factory=list)
    sandbox_result: SandboxResult | None = None
    judge_result: JudgeResult | None = None


@runtime_checkable
class Layer(Protocol):
    """A validation layer. Pipeline conditions are compositions of these
    (ARCHITECTURE.md ADR-006), not branches."""

    name: str

    def run(self, ctx: ValidationContext) -> LayerResult: ...


@runtime_checkable
class Generator(Protocol):
    """Produces (or accepts) an agent artifact for a given task."""

    def generate(self, task: TaskSpec) -> AgentSpec: ...


@runtime_checkable
class ModelClient(Protocol):
    """LLM endpoint used by the judge. Swappable (OpenAI-compatible / Azure OpenAI)."""

    def judge(self, sanitized_evidence: dict) -> JudgeResult: ...


@runtime_checkable
class Sandbox(Protocol):
    """Hardened execution backend (local Docker / ACI / gVisor)."""

    def execute(self, ctx: ValidationContext) -> SandboxResult: ...


@runtime_checkable
class Registry(Protocol):
    """Persists decisions. Default SQLite; enterprise Cosmos/PostgreSQL adapter."""

    def save(self, report: ValidationReport) -> None: ...

    def get(self, artifact_hash: str) -> ValidationReport | None: ...


@runtime_checkable
class TelemetrySink(Protocol):
    """Append-only per-run metrics. Default JSONL; OpenTelemetry adapter optional."""

    def append(self, record: dict) -> None: ...
