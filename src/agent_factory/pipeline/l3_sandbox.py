"""Layer 3 - Sandboxed Execution (hardened Docker runner).

Executes the agent inside a locked-down container and, when the task declares
acceptance tests, runs each one and checks the output. Hardening flags
(auditable, on purpose):

    --network=none                  no network egress (exfiltration containment)
    --cap-drop=ALL                  drop all Linux capabilities
    --security-opt=no-new-privileges
    --read-only                     immutable root filesystem
    --tmpfs /tmp:rw,size=64m        only a small writable scratch space
    --user 65534:65534              run as 'nobody', never root
    --memory / --cpus / --pids-limit   resource bounds
    host-enforced wall-clock timeout

The agent source is passed via an environment variable and written to the
tmpfs at runtime; each test's input is fed on stdin. If Docker is not
available the layer degrades to `skip` (non-blocking) so the pipeline still
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
_MAX_CASES = 5  # cap docker runs per validation


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
    """L3 - hardened container execution + acceptance-test checking."""

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

    def _run_once(self, code: str, stdin_data: str, name: str):
        """Returns (exit_code, stdout, stderr, timed_out)."""
        env = {**os.environ, "AGENT_CODE": code}
        try:
            proc = subprocess.run(
                self._docker_cmd(name),
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                env=env,
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True)  # best effort
            return None, "", "timeout", True
        return proc.returncode, proc.stdout, proc.stderr, False

    def run(self, ctx: ValidationContext) -> LayerResult:
        start = time.perf_counter()

        if not _docker_available():
            return self._result(
                ctx, "skip", False,
                [Finding(rule_id="SBX-NO-DOCKER",
                         message="Docker unavailable; sandbox execution skipped",
                         severity="info")],
                start, SandboxResult(),
            )

        code = ctx.source_code
        tests = ctx.task_spec.acceptance_tests[:_MAX_CASES]
        if tests:
            cases = [(t.input, t.expected_output, True) for t in tests]
        elif ctx.task_spec.sample_input is not None:
            cases = [(ctx.task_spec.sample_input, None, False)]
        else:
            cases = [(None, None, False)]

        findings: list[Finding] = []
        passed_checks = 0
        checked = 0
        last_exit: int | None = None

        for i, (payload, expected, is_check) in enumerate(cases):
            stdin_data = "" if payload is None else json.dumps(payload)
            name = f"afsbx_{ctx.artifact_hash[:12]}_{i}"
            exit_code, stdout, stderr, timed_out = self._run_once(code, stdin_data, name)

            if timed_out:
                wall = (time.perf_counter() - start) * 1000
                sandbox = SandboxResult(executed=True, timed_out=True, wall_time_ms=wall,
                                        violations=["wall-clock timeout"])
                return self._result(
                    ctx, "fail", False,
                    [Finding(rule_id="SBX-TIMEOUT",
                             message=f"Execution exceeded {self.timeout_s}s wall-clock limit",
                             severity="high")],
                    start, sandbox,
                )

            last_exit = exit_code
            if exit_code != 0:
                sandbox = SandboxResult(executed=True, exit_code=exit_code,
                                        acceptance_tests_passed=False if is_check else None)
                return self._result(
                    ctx, "escalate", False,
                    [Finding(rule_id="SBX-NONZERO-EXIT",
                             message=f"Agent exited {exit_code}: {(stderr or '').strip()[:200]}",
                             severity="medium")],
                    start, sandbox,
                )

            if is_check:
                checked += 1
                if _output_matches(stdout, expected):
                    passed_checks += 1
                else:
                    findings.append(Finding(
                        rule_id="SBX-ACCEPTANCE-FAIL",
                        message=f"Test {i}: expected {expected!r}, got {stdout.strip()[:120]!r}",
                        severity="high",
                        blocking=True,
                    ))

        acceptance_passed = (checked > 0 and passed_checks == checked) if checked else None
        wall = (time.perf_counter() - start) * 1000
        sandbox = SandboxResult(
            executed=True, exit_code=last_exit, timed_out=False,
            wall_time_ms=wall, network_attempted=False,
            acceptance_tests_passed=acceptance_passed,
        )

        if any(f.blocking for f in findings):
            return self._result(ctx, "fail", True, findings, start, sandbox)  # functional FAIL
        return self._result(ctx, "pass", False, [], start, sandbox)

    def _result(self, ctx, status, blocking, findings, start, sandbox) -> LayerResult:
        ctx.sandbox_result = sandbox
        return LayerResult(
            layer=self.name,
            status=status,
            blocking=blocking,
            findings=findings,
            timing_ms=(time.perf_counter() - start) * 1000,
        )


def _output_matches(stdout: str, expected) -> bool:
    """Compare the agent's stdout to the expected output, JSON-aware."""
    text = stdout.strip()
    try:
        return json.loads(text) == expected
    except json.JSONDecodeError:
        return text == (expected if isinstance(expected, str) else json.dumps(expected))
