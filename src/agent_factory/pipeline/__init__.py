"""Validation layers L1-L4 and condition compositions."""

from agent_factory.pipeline.l1_static import StaticAnalysisLayer
from agent_factory.pipeline.l2_policy import PolicyLayer
from agent_factory.pipeline.l3_sandbox import SandboxLayer
from agent_factory.pipeline.l4_judge import JudgeLayer

# Benchmark conditions are declarative compositions of layers (ADR-006),
# never branching logic. The orchestrator runs whatever list it is given.
CONDITIONS: dict[str, list] = {
    "static_only": [StaticAnalysisLayer()],
    "static_policy": [StaticAnalysisLayer(), PolicyLayer()],
    "full": [StaticAnalysisLayer(), PolicyLayer(), SandboxLayer(), JudgeLayer()],
}

__all__ = [
    "StaticAnalysisLayer",
    "PolicyLayer",
    "SandboxLayer",
    "JudgeLayer",
    "CONDITIONS",
]
