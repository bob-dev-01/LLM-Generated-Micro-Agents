"""Generator adapter - Anthropic Claude code generation.

Implements the Generator port: asks Claude to write a Python micro-agent that
satisfies a TaskSpec, saves it to disk, and returns an AgentSpec. This replaces
the ExistingArtifactGenerator stub with real generation, behind the same port
(ADR-001) — the validation pipeline is unchanged.

Model is configurable via ANTHROPIC_MODEL (default claude-opus-4-8); set
ANTHROPIC_MODEL=claude-haiku-4-5 for a tighter token budget. Generated code is
ALWAYS validated by the pipeline before it may run.

Requires the `llm` extra: `uv pip install -e ".[llm]"` and ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from agent_factory.schemas import AgentSpec, TaskSpec

try:
    from dotenv import load_dotenv

    # override=True so the project .env wins over a stale/empty shell var.
    load_dotenv(override=True)
except Exception:  # pragma: no cover
    pass

_DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM = """You write small, single-file Python micro-agents for an enterprise \
automation pipeline. The code you produce is automatically validated (static \
analysis, policy, sandbox) before it may run, so it must be safe and minimal.

Hard rules:
- Output ONLY raw Python source. No markdown fences, no prose, no explanation.
- Read the task input as JSON from stdin; write the result as JSON to stdout.
- Import ONLY modules the task explicitly allows.
- Never use eval/exec, subprocess, sockets/network, ctypes, os.system, or \
filesystem writes outside the working directory.
- Define a main() function and call it under `if __name__ == "__main__":`."""

_PROMPT = """Write a Python micro-agent for this task.

Task: {description}
Allowed imports: {allowed_imports}
Prohibited behaviors: {prohibited}
Input (JSON on stdin) example: {sample_input}

Output only the Python source code."""


def _strip_fences(text: str) -> str:
    """Remove ```python ... ``` fences if the model added them anyway."""
    fence = re.match(r"^\s*```(?:python)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    return fence.group(1) if fence else text.strip()


class AnthropicGenerator:
    """Generates a micro-agent artifact with Anthropic Claude."""

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = 2048,
        output_dir: str | Path = "data/generated",
    ) -> None:
        import anthropic

        self.model = model or os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.output_dir = Path(output_dir)
        self._client = anthropic.Anthropic()

    def generate(self, task: TaskSpec) -> AgentSpec:
        prompt = _PROMPT.format(
            description=task.task_description,
            allowed_imports=", ".join(task.allowed_imports) or "(standard library only)",
            prohibited=", ".join(task.prohibited_behaviors) or "(none specified)",
            sample_input=task.sample_input,
        )
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        code = _strip_fences(text)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]
        path = self.output_dir / f"{task.task_id}-{digest}.py"
        path.write_text(code, encoding="utf-8")

        return AgentSpec(
            agent_id=f"{task.task_id}-{digest}",
            generated_code_path=str(path),
            manifest={"source": "anthropic-generated"},
            expected_entrypoint="main",
            model_metadata={"generator": "AnthropicGenerator", "model": self.model},
        )
