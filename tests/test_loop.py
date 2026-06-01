"""Full-loop tests: routing, reuse, generation, and the safety gate.

The measured contribution is the validation gate (see test_smoke.py). These
tests prove the surrounding loop wires together correctly and, crucially, that
the safety boundary holds: an unsafe agent is never executed.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from agent_factory.adapters.sqlite_registry import SqliteRegistry
from agent_factory.orchestrator import handle_ticket
from agent_factory.schemas import Decision, TaskSpec, Ticket

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
AT = "2026-01-01T00:00:00+00:00"


def _task(name: str) -> TaskSpec:
    data = yaml.safe_load((EXAMPLES / name).read_text(encoding="utf-8"))
    return TaskSpec.model_validate(data)


def _ticket(name: str, payload) -> Ticket:
    return Ticket(ticket_id="tk-1", task=_task(name), input_payload=payload)


def test_generate_on_miss_then_reuse(tmp_path):
    reg = SqliteRegistry(tmp_path / "registry.db")
    from agent_factory.adapters.jsonl_telemetry import JsonlTelemetry

    tel = JsonlTelemetry(tmp_path / "t.jsonl")
    common = dict(
        registry=reg, telemetry=tel, reports_dir=tmp_path / "reports", created_at=AT
    )
    safe_agent = EXAMPLES / "agents" / "hello_agent.py"

    # First ticket: capability not in repertoire -> generate, validate, register, execute.
    r1 = handle_ticket(_ticket("hello_task.yaml", [1, 2, 3]), safe_agent, run_id="r1", **common)
    assert r1.reused is False
    assert r1.validation_decision is Decision.PASS
    assert r1.executed is True
    assert r1.output == {"sum": 6}

    # Second identical ticket: routing hit -> reuse, no new validation.
    r2 = handle_ticket(_ticket("hello_task.yaml", [10, 20]), safe_agent, run_id="r2", **common)
    assert r2.reused is True
    assert r2.executed is True
    assert r2.output == {"sum": 30}


def test_unsafe_agent_is_not_executed(tmp_path):
    reg = SqliteRegistry(tmp_path / "registry.db")
    from agent_factory.adapters.jsonl_telemetry import JsonlTelemetry

    tel = JsonlTelemetry(tmp_path / "t.jsonl")
    evil_agent = EXAMPLES / "agents" / "evil_agent.py"

    result = handle_ticket(
        _ticket("danger_task.yaml", {"expr": "1+1"}),
        evil_agent,
        run_id="r-evil",
        registry=reg,
        telemetry=tel,
        reports_dir=tmp_path / "reports",
        created_at=AT,
    )
    # Safety boundary: blocking validation failure -> never executed.
    assert result.validation_decision is Decision.FAIL
    assert result.executed is False
    assert result.reused is False

    # And the unsafe agent must NOT have entered the reusable repertoire.
    assert reg.find_agent_by_capability("config-check") is None
