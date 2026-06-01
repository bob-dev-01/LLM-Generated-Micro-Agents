"""Executor adapter (walking-skeleton): runs a validated agent locally.

Implements the Executor port. The agent is executed as a subprocess: the
ticket's input_payload is passed as JSON on stdin, and stdout is parsed as the
result.

SAFETY NOTE: this runs locally only because the orchestrator guarantees that an
agent reaches execution ONLY after a PASS validation verdict. In the enterprise
target state (ARCHITECTURE_ENTERPRISE.md), execution routes through the same
hardened sandbox as L3 (Kata/gVisor, deny-all egress) behind this same port.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

from agent_factory.schemas import AgentSpec, ExecutionResult


class LocalExecutor:
    def __init__(self, python_executable: str | None = None, timeout_s: float = 10.0) -> None:
        self.python = python_executable or sys.executable
        self.timeout_s = timeout_s

    def execute(self, agent: AgentSpec, input_payload: object) -> ExecutionResult:
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                [self.python, agent.generated_code_path],
                input=json.dumps(input_payload),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error=f"execution timed out after {self.timeout_s}s",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        duration_ms = (time.perf_counter() - start) * 1000
        if proc.returncode != 0:
            return ExecutionResult(
                success=False,
                error=(proc.stderr or "non-zero exit").strip(),
                duration_ms=duration_ms,
            )

        try:
            output: object = json.loads(proc.stdout)
        except json.JSONDecodeError:
            output = proc.stdout.strip()
        return ExecutionResult(success=True, output=output, duration_ms=duration_ms)
