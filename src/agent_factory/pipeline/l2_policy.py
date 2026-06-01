"""Layer 2 - Policy & Supply Chain (walking-skeleton stub).

Structural stub: returns a well-formed LayerResult so the pipe and decision
logic are exercised end-to-end. The full MVP plugs in a YAML allow/denylist
engine plus pip-audit dependency checks behind this same contract.
"""

from __future__ import annotations

import time

from agent_factory.ports import ValidationContext
from agent_factory.schemas import LayerResult


class PolicyLayer:
    """L2 - deterministic policy + supply-chain checks. STUB."""

    name = "L2_policy"

    def run(self, ctx: ValidationContext) -> LayerResult:
        start = time.perf_counter()
        # TODO(POC-1): YAML allow/denylist for imports/deps/tools/network/fs;
        # pip-audit on pinned+hashed requirements; forbidden-index detection.
        return LayerResult(
            layer=self.name,
            status="pass",
            blocking=False,
            findings=[],
            timing_ms=(time.perf_counter() - start) * 1000,
        )
