"""Live LLM tests for the Anthropic judge and generator.

These call the real Anthropic API, so they are SKIPPED unless ANTHROPIC_API_KEY
is set (and the `llm` extra is installed). They never run in CI (no key there),
so they cost nothing by default. They use Haiku to keep any local run cheap.
"""

from __future__ import annotations

import os

import pytest

_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
try:
    import anthropic  # noqa: F401

    _HAS_SDK = True
except Exception:
    _HAS_SDK = False

llm_required = pytest.mark.skipif(
    not (_HAS_KEY and _HAS_SDK), reason="ANTHROPIC_API_KEY and anthropic SDK required"
)

CHEAP_MODEL = "claude-haiku-4-5"  # keep live-test cost minimal


@llm_required
def test_judge_returns_structured_verdict():
    from agent_factory.adapters.anthropic_client import AnthropicJudge

    judge = AnthropicJudge(model=CHEAP_MODEL)
    verdict = judge.judge(
        {
            "task_description": "Sum a list of integers from stdin.",
            "risk_tier": "low",
            "prohibited_behaviors": ["network access"],
            "deterministic_findings": [],
            "sandbox": {"executed": True, "exit_code": 0, "timed_out": False},
        }
    )
    assert verdict.decision in ("pass", "fail", "escalate")
    assert 0.0 <= verdict.correctness_score <= 1.0


@llm_required
def test_generator_produces_runnable_artifact(tmp_path):
    from agent_factory.adapters.anthropic_generator import AnthropicGenerator
    from agent_factory.schemas import TaskSpec

    task = TaskSpec(
        task_id="gen-test",
        task_description="Read a JSON list of integers from stdin and write {'sum': <total>} to stdout.",
        capability="sum-integers",
        allowed_imports=["json", "sys"],
        prohibited_behaviors=["network access", "subprocess execution"],
        sample_input=[1, 2, 3],
    )
    gen = AnthropicGenerator(model=CHEAP_MODEL, output_dir=tmp_path)
    spec = gen.generate(task)

    from pathlib import Path

    code = Path(spec.generated_code_path).read_text(encoding="utf-8")
    assert "def main" in code
    # the generated artifact should at least parse
    import ast

    ast.parse(code)
