"""Router adapter (walking-skeleton): exact capability-key match.

Implements the Router port. The 'is there already an agent for this task?'
decision. Thin by design — exact match on TaskSpec.capability. A richer
implementation (semantic/embedding match) can replace this behind the same
port without touching the loop; routing quality is NOT part of the measured
contribution (the thesis measures the validation gate only).
"""

from __future__ import annotations

from agent_factory.ports import Registry
from agent_factory.schemas import AgentSpec, TaskSpec


class CapabilityRouter:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def find_agent(self, task: TaskSpec) -> AgentSpec | None:
        return self.registry.find_agent_by_capability(task.capability)
