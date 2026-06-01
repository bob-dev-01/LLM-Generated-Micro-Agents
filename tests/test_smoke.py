"""Walking-skeleton smoke tests: prove the pipe end-to-end and the R1 invariant."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent_factory.decision import decide
from agent_factory.orchestrator import run_validation
from agent_factory.schemas import Decision, JudgeResult, LayerResult, TaskSpec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _task() -> TaskSpec:
    data = yaml.safe_load((EXAMPLES / "hello_task.yaml").read_text(encoding="utf-8"))
    return TaskSpec.model_validate(data)


def test_benign_agent_passes_full_pipeline(tmp_path):
    report = run_validation(
        _task(),
        EXAMPLES / "agents" / "hello_agent.py",
        condition="full",
        run_id="test-pass",
        created_at="2026-06-01T00:00:00+00:00",
        reports_dir=tmp_path / "reports",
        registry=_TmpRegistry(tmp_path),
        telemetry=_TmpTelemetry(tmp_path),
    )
    assert report.final_decision is Decision.PASS
    assert report.per_layer_status["L1_static"] == "pass"
    assert len(report.artifact_hash) == 64  # SHA-256 hex


def test_evil_agent_fails_blocking(tmp_path):
    report = run_validation(
        _task(),
        EXAMPLES / "agents" / "evil_agent.py",
        condition="full",
        run_id="test-fail",
        created_at="2026-06-01T00:00:00+00:00",
        reports_dir=tmp_path / "reports",
        registry=_TmpRegistry(tmp_path),
        telemetry=_TmpTelemetry(tmp_path),
    )
    assert report.final_decision is Decision.FAIL
    assert any(f.blocking for f in report.findings)


def test_judge_cannot_override_blocking_fail():
    """R1 invariant: a blocking deterministic FAIL is final, even if judge passes."""
    results = [
        LayerResult(layer="L1_static", status="fail", blocking=True),
    ]
    approving_judge = JudgeResult(correctness_score=1.0, decision="pass", uncertain=False)
    decision, _ = decide(results, approving_judge)
    assert decision is Decision.FAIL


def test_conditions_are_layer_subsets(tmp_path):
    """static_only runs fewer layers than full (ADR-006)."""
    so = run_validation(
        _task(), EXAMPLES / "agents" / "hello_agent.py",
        condition="static_only", run_id="t-so", created_at="2026-06-01T00:00:00+00:00",
        reports_dir=tmp_path / "r", registry=_TmpRegistry(tmp_path), telemetry=_TmpTelemetry(tmp_path),
    )
    full = run_validation(
        _task(), EXAMPLES / "agents" / "hello_agent.py",
        condition="full", run_id="t-full", created_at="2026-06-01T00:00:00+00:00",
        reports_dir=tmp_path / "r", registry=_TmpRegistry(tmp_path), telemetry=_TmpTelemetry(tmp_path),
    )
    assert len(so.per_layer_status) < len(full.per_layer_status)


# --- tiny temp adapters so tests never touch the real data/ dir ------------- #


class _TmpRegistry:
    def __init__(self, base: Path):
        from agent_factory.adapters.sqlite_registry import SqliteRegistry

        self._r = SqliteRegistry(base / "registry.db")

    def save(self, report, report_path=None):
        self._r.save(report, report_path=report_path)

    def get(self, h):
        return self._r.get(h)


class _TmpTelemetry:
    def __init__(self, base: Path):
        from agent_factory.adapters.jsonl_telemetry import JsonlTelemetry

        self._t = JsonlTelemetry(base / "telemetry.jsonl")

    def append(self, record):
        self._t.append(record)
