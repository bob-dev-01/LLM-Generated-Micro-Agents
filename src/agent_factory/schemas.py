"""Canonical Pydantic v2 schemas — the contracts every layer and adapter shares.

See ARCHITECTURE.md §7 (Data Architecture). These are frozen by end of Week 2
in the implementation plan; treat changes here as architecturally significant.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class Decision(str, Enum):
    """Final, deterministic-first decision for an artifact."""

    PASS = "PASS"
    FAIL = "FAIL"
    ESCALATE = "ESCALATE"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


LayerStatus = Literal["pass", "fail", "escalate", "skip"]
Severity = Literal["info", "low", "medium", "high", "critical"]


# --------------------------------------------------------------------------- #
# Inputs: TaskSpec, AgentSpec
# --------------------------------------------------------------------------- #


class TaskSpec(BaseModel):
    """What the micro-agent is supposed to do, and the rules it must obey."""

    task_id: str
    task_description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    allowed_imports: list[str] = Field(default_factory=list)
    allowed_dependencies: list[str] = Field(default_factory=list)
    prohibited_behaviors: list[str] = Field(default_factory=list)
    risk_tier: RiskTier = RiskTier.MEDIUM
    acceptance_tests: list[str] = Field(default_factory=list)


class AgentSpec(BaseModel):
    """A generated (or supplied) micro-agent artifact ready for validation."""

    agent_id: str
    generated_code_path: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    declared_tools: list[str] = Field(default_factory=list)
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    expected_entrypoint: str = "main"
    model_metadata: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Layer evidence
# --------------------------------------------------------------------------- #


class Finding(BaseModel):
    """A single piece of evidence produced by a validation layer."""

    rule_id: str
    message: str
    severity: Severity = "info"
    location: str | None = None  # e.g. "agent.py:42"
    blocking: bool = False


class LayerResult(BaseModel):
    """Uniform output of every layer — the basis of the deterministic decision."""

    layer: str
    status: LayerStatus
    blocking: bool = False  # True if this layer hit a hard, decision-forcing failure
    findings: list[Finding] = Field(default_factory=list)
    timing_ms: float = 0.0


class SandboxResult(BaseModel):
    """Outcome of executing the artifact in the hardened container (L3)."""

    executed: bool = False
    exit_code: int | None = None
    timed_out: bool = False
    wall_time_ms: float | None = None
    cpu_time_ms: float | None = None
    peak_memory_mb: float | None = None
    network_attempted: bool = False
    acceptance_tests_passed: bool | None = None
    violations: list[str] = Field(default_factory=list)


class JudgeResult(BaseModel):
    """Structured output of the LLM-as-a-Judge layer (L4)."""

    correctness_score: float = 0.0  # 0..1
    safety_risk: Severity = "info"
    decision: LayerStatus = "skip"
    uncertain: bool = False
    reasons: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Output: ValidationReport
# --------------------------------------------------------------------------- #


class ValidationReport(BaseModel):
    """Complete, machine-readable, hash-anchored result of one validation run."""

    report_version: str = "0.1"
    run_id: str
    task_id: str
    agent_id: str
    artifact_hash: str
    condition: str = "full"
    per_layer_status: dict[str, LayerStatus] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    sandbox_result: SandboxResult | None = None
    judge_result: JudgeResult | None = None
    final_decision: Decision
    reasons: list[str] = Field(default_factory=list)
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str  # ISO-8601, injected by the orchestrator (no hidden clock reads)
