"""Layer 3 - Sandboxed Execution (hardened Docker runner).

Executes the agent inside a locked-down container and records what actually
happened. Hardening flags (auditable, on purpose):

    --network=none                  no network egress (exfiltration containment)
    --cap-drop=ALL                  drop all Linux capabilities
    --security-opt=no-new-privileges
    --read-only                     immutable root filesystem
    --tmpfs /tmp:rw,size=64m        only a small writable scratch space
    --user 65534:65534              run as 'nobody', never root
    --memory / --cpus / --pids-limit   resource bounds
    host-enforced wall-clock timeout

The agent source is passed via an environment variable and written to the
tmpfs at runtime; the task's `sample_input` is fed on stdin. If Docker is not
available, the layer degrades to `skip` (non-blocking) so the pipeline still
completes - it never executes untrusted code outside the sandbox.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from agent_factory.ports import ValidationContext
from agent_factory.schemas import Finding, LayerResult, SandboxResult

_DEFAULT_IMAGE = "python:3.13-slim"
_RUN_SCRIPT = 'printf "%s" "$AGENT_CODE" > /tmp/agent.py && python /tmp/agent.py'


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


class SandboxLayer:
    """L3 - hardened container execution."""

    name = "L3_sandbox"

    def __init__(
        self,
        image: str = _DEFAULT_IMAGE,
        timeout_s: float = 20.0,
        memory: str = "256m",
        cpus: str = "1.0",
        pids_limit: int = 128,
    ) -> None:
        self.image = image
        self.timeout_s = timeout_s
        self.memory = memory
        self.cpus = cpus
        self.pids_limit = pids_limit

    def _docker_cmd(self, container_name: str) -> list[str]:
        return [
            "docker", "run", "--rm", "-i",
            "--name", container_name,
            "--network=none",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m,mode=1777",
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            f"--pids-limit={self.pids_limit}",
            "--user", "65534:65534",
            "-e", "AGENT_CODE",
            self.image,
            "sh", "-c", _RUN_SCRIPT,
        ]

    def run(self, ctx: ValidationContext) -> LayerResult:
        start = time.perf_counter()

        if not _docker_available():
            return self._result(
                "skip", False,
                [Finding(rule_id="SBX-NO-DOCKER",
                         message="Docker unavailable; sandbox execution skipped",
                         severity="info")],
                start,
            )

        payload = ctx.task_spec.sample_input
        stdin_data = json.dumps(payload) if payload is not None else ""
        container_name = f"afsbx_{ctx.artifact_hash[:16]}"
        env = {**os.environ, "AGENT_CODE": ctx.source_code}

        try:
            proc = subprocess.run(
                self._docker_cmd(container_name),
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                env=env,
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container_name], capture_output=True)  # best effort
            wall = (time.perf_counter() - start) * 1000
            ctx.sandbox_result = SandboxResult(
                executed=True, timed_out=True, wall_time_ms=wall,
                violations=["wall-clock timeout"],
            )
            return self._result(
                "fail", False,
                [Finding(rule_id="SBX-TIMEOUT",
                         message=f"Execution exceeded {self.timeout_s}s wall-clock limit",
                         severity="high")],
                start,
            )
        except Exception as exc:  # infrastructure error -> degrade, do not crash the pipeline
            return self._result(
                "skip", False,
                [Finding(rule_id="SBX-ERROR",
                         message=f"Sandbox infrastructure error; skipped: {exc}",
                         severity="info")],
                start,
            )

        wall = (time.perf_counter() - start) * 1000
        ctx.sandbox_result = SandboxResult(
            executed=True,
            exit_code=proc.returncode,
            timed_out=False,
            wall_time_ms=wall,
            network_attempted=False,
        )

        if proc.returncode == 0:
            return self._result("pass", False, [], start)
        return self._result(
            "escalate", False,
            [Finding(rule_id="SBX-NONZERO-EXIT",
                     message=f"Agent exited {proc.returncode}: {(proc.stderr or '').strip()[:200]}",
                     severity="medium")],
            start,
        )

    def _result(self, status, blocking, findings, start) -> LayerResult:
        return LayerResult(
            layer=self.name,
            status=status,
            blocking=blocking,
            findings=findings,
            timing_ms=(time.perf_counter() - start) * 1000,
        )
