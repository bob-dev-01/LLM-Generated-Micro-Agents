"""Layer 4 - LLM-as-a-Judge (walking-skeleton stub).

Structural stub: returns a deterministic, high-confidence JudgeResult so no LLM
key or budget is needed for the skeleton. The full MVP sends ONLY sanitized,
structured evidence (never raw code, ADR-005) to an OpenAI-compatible endpoint
with structured outputs, behind the ModelClient port.

Critically: even here the judge is advisory. The deterministic-first decision
function (decision.py) ensures the judge can never overturn a blocking FAIL.
"""

from __future__ import annotations

import time

from agent_factory.ports import ValidationContext
from agent_factory.schemas import JudgeResult, LayerResult


def _sanitize_evidence(ctx: ValidationContext) -> dict:
    """Build the sanitized evidence pack the real judge will receive (ADR-005).

    Deliberately excludes raw source code; only structured findings + metrics.
    """
    return {
        "task_description": ctx.task_spec.task_description,
        "risk_tier": ctx.task_spec.risk_tier.value,
        "deterministic_findings": [
            {"rule_id": f.rule_id, "severity": f.severity, "message": f.message}
            for r in ctx.results
            for f in r.findings
        ],
        "sandbox": ctx.sandbox_result.model_dump() if ctx.sandbox_result else None,
    }


class JudgeLayer:
    """L4 - structured-output LLM judge. STUB (no model call)."""

    name = "L4_judge"

    def run(self, ctx: ValidationContext) -> LayerResult:
        start = time.perf_counter()
        _ = _sanitize_evidence(ctx)  # exercised now; sent to model in POC-1

        # TODO(POC-1): ModelClient.judge(evidence) -> JudgeResult (structured output).
        judge = JudgeResult(
            correctness_score=0.95,
            safety_risk="info",
            decision="pass",
            uncertain=False,
            reasons=["stub judge: high-confidence pass (no model call in skeleton)"],
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
