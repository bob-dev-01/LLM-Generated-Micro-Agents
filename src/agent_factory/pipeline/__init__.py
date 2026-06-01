"""Validation layers L1-L4 and condition compositions.

Benchmark conditions are declarative compositions of layers (ADR-006), never
branching logic. `build_pipeline` constructs the layer list for a condition and
optionally injects a ModelClient into the L4 judge (real LLM vs deterministic
stub).
"""

from agent_factory.pipeline.l1_static import StaticAnalysisLayer
from agent_factory.pipeline.l2_policy import PolicyLayer
from agent_factory.pipeline.l3_sandbox import SandboxLayer
from agent_factory.pipeline.l4_judge import JudgeLayer

# Condition names (the three benchmark conditions).
CONDITIONS: tuple[str, ...] = ("static_only", "static_policy", "full")


def build_pipeline(condition: str, model_client=None) -> list:
    """Return the ordered layer list for a condition.

    `model_client` (a ModelClient) is injected into the L4 judge; when None the
    judge runs as a deterministic stub (no LLM call, no key/budget needed).
    """
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown condition '{condition}'. Choices: {list(CONDITIONS)}")
    layers: list = [StaticAnalysisLayer()]
    if condition in ("static_policy", "full"):
        layers.append(PolicyLayer())
    if condition == "full":
        layers.append(SandboxLayer())
        layers.append(JudgeLayer(model_client=model_client))
    return layers


__all__ = [
    "StaticAnalysisLayer",
    "PolicyLayer",
    "SandboxLayer",
    "JudgeLayer",
    "CONDITIONS",
    "build_pipeline",
]
