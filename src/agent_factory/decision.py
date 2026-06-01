"""Deterministic-first decision function (ARCHITECTURE.md §8.1, ADR-004).

The decision is a pure function of layer evidence. Deterministic findings
strictly dominate the LLM judge: the judge can push a case toward ESCALATE or
confirm PASS, but can NEVER overturn a blocking deterministic FAIL (invariant R1).
"""

from __future__ import annotations

from agent_factory.schemas import Decision, JudgeResult, LayerResult


def decide(
    results: list[LayerResult],
    judge: JudgeResult | None,
) -> tuple[Decision, list[str]]:
    reasons: list[str] = []

    # 1. Any blocking deterministic failure => FAIL. Judge cannot override.
    blocking = [r for r in results if r.status == "fail" and r.blocking]
    if blocking:
        for r in blocking:
            for f in r.findings:
                if f.blocking:
                    reasons.append(f"{r.layer}: {f.rule_id} - {f.message}")
        reasons.append("Blocking deterministic violation; judge cannot override (R1).")
        return Decision.FAIL, reasons

    # 2. Any non-blocking deterministic fail/escalate => ESCALATE.
    soft = [r for r in results if r.status in ("fail", "escalate")]
    if soft:
        for r in soft:
            reasons.append(f"{r.layer}: status={r.status}")
        reasons.append("Non-blocking deterministic concern; routed to human review.")
        return Decision.ESCALATE, reasons

    # 3. Judge ambiguity => ESCALATE.
    if judge and judge.uncertain:
        reasons.append("Judge returned an uncertain verdict; routed to human review.")
        return Decision.ESCALATE, reasons

    # 4. Conflict: deterministic layers clean but judge says fail => ESCALATE.
    if judge and judge.decision == "fail":
        reasons.append(
            "Judge flagged risk while deterministic layers passed; "
            "deterministic evidence shown first, routed to human review."
        )
        return Decision.ESCALATE, reasons

    # 5. Everything clean (+ confident judge in full pipeline) => PASS.
    reasons.append("No deterministic violation; acceptance evidence and judge consistent.")
    return Decision.PASS, reasons
