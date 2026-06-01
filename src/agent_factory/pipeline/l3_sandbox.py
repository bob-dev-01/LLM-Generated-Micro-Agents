"""Layer 3 - Sandboxed Execution (walking-skeleton stub).

Structural stub: simulates a clean sandboxed run and records a SandboxResult on
the context. The full MVP replaces this with a hardened Docker runner
(--network=none, --cap-drop=ALL, read-only + tmpfs, non-root, no-new-privileges,
cpu/mem/pids limits, host-enforced timeout) via the docker SDK.
"""

from __future__ import annotations

import time

from agent_factory.ports import ValidationContext
from agent_factory.schemas import LayerResult, SandboxResult


class SandboxLayer:
    """L3 - hardened container execution. STUB."""

    name = "L3_sandbox"

    def run(self, ctx: ValidationContext) -> LayerResult:
        start = time.perf_counter()
        # TODO(POC-1): real docker run with hardening flags + resource capture.
        ctx.sandbox_result = SandboxResult(
            executed=True,
            exit_code=0,
            timed_out=False,
            network_attempted=False,
            acceptance_tests_passed=True,
            violations=[],
        )
        return LayerResult(
            layer=self.name,
            status="pass",
            blocking=False,
            findings=[],
            timing_ms=(time.perf_counter() - start) * 1000,
        )
