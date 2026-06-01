"""Unit tests for the deterministic layers L2 (policy) and L3 (sandbox)."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from agent_factory.pipeline.l2_policy import PolicyLayer
from agent_factory.pipeline.l3_sandbox import SandboxLayer
from agent_factory.ports import ValidationContext
from agent_factory.schemas import AgentSpec, TaskSpec


def _ctx(source: str, *, allowed_imports=None, allowed_deps=None, requirements=None, sample_input=None):
    task = TaskSpec(
        task_id="t",
        task_description="d",
        allowed_imports=allowed_imports or [],
        allowed_dependencies=allowed_deps or [],
        sample_input=sample_input,
    )
    agent = AgentSpec(
        agent_id="a",
        generated_code_path="<inline>",
        requirements=requirements or [],
    )
    return ValidationContext(
        task_spec=task, agent_spec=agent, artifact_hash="0" * 64, source_code=source
    )


# --------------------------- L2 policy --------------------------------------- #


def test_policy_allows_compliant_agent():
    ctx = _ctx("import json\nimport sys\n", allowed_imports=["json", "sys"])
    result = PolicyLayer().run(ctx)
    assert result.status == "pass"
    assert result.findings == []


def test_policy_flags_import_outside_allowlist():
    # csv is harmless (L1 would not block it) but the task did not permit it.
    ctx = _ctx("import json\nimport csv\n", allowed_imports=["json"])
    result = PolicyLayer().run(ctx)
    assert result.status == "fail"
    assert any(f.rule_id == "POLICY-IMPORT-NOT-ALLOWED" for f in result.findings)


def test_policy_flags_denylisted_import():
    ctx = _ctx("import socket\n", allowed_imports=["socket"])  # allowlisted but globally denied
    result = PolicyLayer().run(ctx)
    assert result.status == "fail"
    assert any(f.rule_id == "POLICY-IMPORT-DENIED" for f in result.findings)


def test_policy_flags_unpinned_dependency():
    ctx = _ctx("import json\n", allowed_imports=["json"], requirements=["requests"])
    result = PolicyLayer().run(ctx)
    assert any(f.rule_id == "POLICY-DEP-UNPINNED" for f in result.findings)


def test_policy_flags_vcs_dependency():
    ctx = _ctx("import json\n", allowed_imports=["json"],
               requirements=["evil @ git+https://example.com/evil.git"])
    result = PolicyLayer().run(ctx)
    assert any(f.rule_id == "POLICY-DEP-EXTERNAL-SOURCE" for f in result.findings)


def test_policy_accepts_pinned_dependency():
    ctx = _ctx("import json\n", allowed_imports=["json"], requirements=["requests==2.32.0"])
    result = PolicyLayer().run(ctx)
    assert result.status == "pass"


# --------------------------- L3 sandbox (needs Docker) ----------------------- #

_DOCKER = shutil.which("docker") is not None and (
    subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                   capture_output=True).returncode == 0
)
docker_required = pytest.mark.skipif(not _DOCKER, reason="Docker daemon not available")


@docker_required
def test_sandbox_runs_benign_agent():
    source = "import json,sys\njson.dump({'sum': sum(json.load(sys.stdin))}, sys.stdout)\n"
    ctx = _ctx(source, sample_input=[1, 2, 3])
    result = SandboxLayer(timeout_s=60).run(ctx)
    assert result.status == "pass"
    assert ctx.sandbox_result.exit_code == 0
    assert ctx.sandbox_result.timed_out is False


@docker_required
def test_sandbox_enforces_timeout():
    ctx = _ctx("import time\ntime.sleep(30)\n")
    result = SandboxLayer(timeout_s=4).run(ctx)
    assert result.status == "fail"
    assert ctx.sandbox_result.timed_out is True


@docker_required
def test_sandbox_blocks_network():
    # network=none -> any socket connection attempt fails -> non-zero exit
    source = (
        "import socket\n"
        "s = socket.socket()\n"
        "s.settimeout(3)\n"
        "s.connect(('1.1.1.1', 80))\n"
    )
    ctx = _ctx(source, sample_input=None)
    SandboxLayer(timeout_s=60).run(ctx)
    assert ctx.sandbox_result.exit_code != 0  # connection could not be established
