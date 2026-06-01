"""ModelClient adapter - Anthropic Claude judge (L4).

Implements the ModelClient port using the official `anthropic` SDK with
structured output (`messages.parse`) so the verdict is always schema-valid.
The judge receives ONLY sanitized evidence (ADR-005) and remains advisory:
deterministic-first decision logic prevents it from overriding a blocking FAIL.

Model is configurable via ANTHROPIC_MODEL (default claude-opus-4-8). For a tight
token budget, set ANTHROPIC_MODEL=claude-haiku-4-5. The system prompt is cached
(prompt caching) to cut cost across many validation runs.

Requires the `llm` extra: `uv pip install -e ".[llm]"` and ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import os
import re
from typing import Literal

from pydantic import BaseModel

from agent_factory.schemas import JudgeResult

try:  # optional dependency: only needed when the real judge is used
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass

_DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM = """You are a security and correctness validator for a single, \
automatically generated Python micro-agent in an enterprise pipeline.

You receive ONLY sanitized, structured evidence — never raw source code. \
Deterministic layers (static analysis, policy, sandbox) have already run and \
their findings are authoritative; you cannot override a blocking security \
failure. Your job is to assess residual correctness and safety risk and decide:

- "pass": clearly correct and safe given the evidence.
- "escalate": ambiguous, conflicting, or insufficient evidence — route to a human.
- "fail": clear correctness or safety problem the deterministic layers did not block.

Be conservative: when in doubt, set uncertain=true and prefer "escalate" over \
"pass". correctness_score is 0..1. Keep reasons short and concrete."""


class JudgeOutput(BaseModel):
    """Structured schema the model must return."""

    correctness_score: float
    safety_risk: Literal["info", "low", "medium", "high", "critical"]
    decision: Literal["pass", "fail", "escalate"]
    uncertain: bool
    reasons: list[str]


class AnthropicJudge:
    """L4 judge backed by Anthropic Claude."""

    def __init__(self, model: str | None = None, max_tokens: int = 1024) -> None:
        import anthropic  # imported lazily so the base package has no hard dep

        self.model = model or os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    def judge(self, sanitized_evidence: dict) -> JudgeResult:
        evidence_json = json.dumps(sanitized_evidence, ensure_ascii=False)
        try:
            out = self._judge_structured(evidence_json)
        except Exception:
            # Some models (e.g. Sonnet 4.5) don't support structured outputs —
            # fall back to a plain request and parse the JSON ourselves.
            try:
                out = self._judge_manual(evidence_json)
            except Exception as exc:  # network/credit/parse error -> conservative escalate
                return JudgeResult(
                    correctness_score=0.0,
                    safety_risk="info",
                    decision="escalate",
                    uncertain=True,
                    reasons=[f"judge unavailable, escalating: {exc}"],
                )

        return JudgeResult(
            correctness_score=out.correctness_score,
            safety_risk=out.safety_risk,
            decision=out.decision,
            uncertain=out.uncertain,
            reasons=out.reasons,
        )

    def _judge_structured(self, evidence_json: str) -> JudgeOutput:
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": evidence_json}],
            output_format=JudgeOutput,
        )
        return response.parsed_output

    def _judge_manual(self, evidence_json: str) -> JudgeOutput:
        """Fallback for models without structured-output support: ask for raw JSON."""
        instruction = (
            "Respond with ONLY a JSON object (no prose, no markdown fences) with keys: "
            'correctness_score (number 0..1), safety_risk (one of "info","low","medium",'
            '"high","critical"), decision (one of "pass","fail","escalate"), '
            "uncertain (boolean), reasons (array of short strings)."
        )
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"{evidence_json}\n\n{instruction}"}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        text = re.sub(r"^\s*```(?:json)?\s*\n(.*?)\n```\s*$", r"\1", text.strip(), flags=re.DOTALL)
        return JudgeOutput.model_validate_json(text)
