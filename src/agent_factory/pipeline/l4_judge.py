"""Layer 4 - LLM-as-a-Judge.

Receives ONLY sanitized, structured evidence (never raw code, ADR-005) and
returns a structured verdict. If a ModelClient is injected, it calls a real LLM
(Anthropic Claude with structured output); otherwise it falls back to a
deterministic high-confidence stub so the pipeline runs with no key/budget.

Critically, the judge is advisory: the deterministic-first decision function
(decision.py) guarantees it can never overturn a blocking deterministic FAIL.
"""

from __future__ import annotations

import time

from agent_factory.ports import ValidationContext
from agent_factory.schemas import JudgeResult, LayerResult


def _sanitize_evidence(ctx: ValidationContext) -> dict:
    """Build the sanitized evidence pack the judge receives (ADR-005).

    Deliberately excludes raw source code; only structured findings + metrics.
    """
    return {
        "task_description": ctx.task_spec.task_description,
        "risk_tier": ctx.task_spec.risk_tier.value,
        "prohibited_behaviors": ctx.task_spec.prohibited_behaviors,
        "deterministic_findings": [
            {"rule_id": f.rule_id, "severity": f.severity, "message": f.message}
            for r in ctx.results
            for f in r.findings
        ],
        "sandbox": ctx.sandbox_result.model_dump() if ctx.sandbox_result else None,
    }


class JudgeLayer:
    """L4 - structured-output LLM judge (real if a ModelClient is given)."""

    name = "L4_judge"

    def __init__(self, model_client=None) -> None:
        self.model_client = model_client

    def run(self, ctx: ValidationContext) -> LayerResult:
        start = time.perf_counter()
        evidence = _sanitize_evidence(ctx)

        if self.model_client is not None:
            judge = self.model_client.judge(evidence)
        else:
            judge = JudgeResult(
                correctness_score=0.95,
                safety_risk="info",
                decision="pass",
                uncertain=False,
                reasons=["stub judge: high-confidence pass (no model call)"],
            )

        ctx.judge_result = judge
        status = "escalate" if judge.uncertain else judge.decision
        return LayerResult(
            layer=self.name,
            status=status,
            blocking=False,  # the judge is never blocking (ADR-004)
            findings=[],
            timing_ms=(time.perf_counter() - start) * 1000,
        )
