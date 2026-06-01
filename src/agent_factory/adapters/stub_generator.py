"""Generator adapter (walking-skeleton): accepts an existing artifact file.

The skeleton does not call an LLM. It loads a supplied Python artifact and wraps
it in an AgentSpec. The full MVP plugs in an AutoGen-based generator behind this
same Generator port (ADR-001), upgradable in isolation if generation quality is
the bottleneck.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from agent_factory.schemas import AgentSpec, TaskSpec


def sha256_of(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ExistingArtifactGenerator:
    """Accepts a pre-existing Python artifact instead of generating one."""

    def __init__(self, artifact_path: str | Path) -> None:
        self.artifact_path = Path(artifact_path)

    def generate(self, task: TaskSpec) -> AgentSpec:
        if not self.artifact_path.is_file():
            raise FileNotFoundError(f"Artifact not found: {self.artifact_path}")
        return AgentSpec(
            agent_id=f"{task.task_id}-artifact",
            generated_code_path=str(self.artifact_path),
            manifest={"source": "existing-artifact"},
            model_metadata={"generator": "ExistingArtifactGenerator", "model": "none"},
        )
