"""Layer 2 - Policy & Supply Chain.

Deterministic enforcement of:
  * Import policy - the agent may import only what its TaskSpec allows, and never
    a globally denied module (complements L1, which catches dangerous *usage*).
  * Supply-chain policy - declared requirements must be exactly pinned, must not
    come from VCS/URL/external indexes, and must respect allow/deny lists.

Policy lives in `policies/default.yaml` (loaded if present), with a safe built-in
fallback. An optional pip-audit pass (vulnerable-dependency scan) is available but
OFF by default, since it requires network access and would make runs non-offline.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path
from typing import Any

import yaml

from agent_factory.ports import ValidationContext
from agent_factory.schemas import Finding, LayerResult

# Built-in fallback policy (mirrors policies/default.yaml).
DEFAULT_POLICY: dict[str, Any] = {
    "imports": {
        "denylist": [
            "subprocess", "socket", "ctypes", "multiprocessing",
            "ftplib", "smtplib", "telnetlib", "http.client", "urllib.request",
        ]
    },
    "dependencies": {"require_pinned": True, "allow_vcs_or_url": False, "denylist": []},
}

# Modules always permitted even if a task declares a narrow allowlist.
_ALWAYS_ALLOWED = {"__future__"}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_POLICY_PATH = _REPO_ROOT / "policies" / "default.yaml"


def _load_policy(policy_path: str | Path | None) -> dict[str, Any]:
    path = Path(policy_path) if policy_path else _DEFAULT_POLICY_PATH
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
    return DEFAULT_POLICY


def _imported_modules(source: str) -> list[tuple[str, int]]:
    """Return (top_level_module, lineno) for every import in the source."""
    out: list[tuple[str, int]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out  # L1 already reports the syntax error as a blocking finding
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module.split(".")[0], node.lineno))
    return out


def _dep_name(spec: str) -> str:
    """Extract a package name from a requirement spec for allow/deny matching."""
    for sep in ("==", ">=", "<=", "~=", ">", "<", "!=", "@", "[", " "):
        if sep in spec:
            return spec.split(sep)[0].strip().lower()
    return spec.strip().lower()


class PolicyLayer:
    """L2 - deterministic policy + supply-chain checks."""

    name = "L2_policy"

    def __init__(self, policy: dict | None = None, policy_path: str | Path | None = None) -> None:
        self.policy = policy or _load_policy(policy_path)

    def run(self, ctx: ValidationContext) -> LayerResult:
        start = time.perf_counter()
        findings: list[Finding] = []

        imports_policy = self.policy.get("imports", {})
        deny_modules = {m.split(".")[0] for m in imports_policy.get("denylist", [])}
        allowed_imports = {m.split(".")[0] for m in ctx.task_spec.allowed_imports}

        # --- Import policy --------------------------------------------------- #
        for module, lineno in _imported_modules(ctx.source_code):
            if module in deny_modules:
                findings.append(
                    Finding(
                        rule_id="POLICY-IMPORT-DENIED",
                        message=f"Import '{module}' is on the global policy denylist",
                        severity="critical",
                        location=f"agent.py:{lineno}",
                        blocking=True,
                    )
                )
            elif allowed_imports and module not in allowed_imports and module not in _ALWAYS_ALLOWED:
                findings.append(
                    Finding(
                        rule_id="POLICY-IMPORT-NOT-ALLOWED",
                        message=f"Import '{module}' is not in the task's allowed_imports",
                        severity="high",
                        location=f"agent.py:{lineno}",
                        blocking=True,
                    )
                )

        # --- Supply-chain policy -------------------------------------------- #
        deps_policy = self.policy.get("dependencies", {})
        require_pinned = deps_policy.get("require_pinned", True)
        allow_vcs = deps_policy.get("allow_vcs_or_url", False)
        dep_denylist = {d.lower() for d in deps_policy.get("denylist", [])}
        allowed_deps = {_dep_name(d) for d in ctx.task_spec.allowed_dependencies}

        for spec in ctx.agent_spec.requirements:
            name = _dep_name(spec)
            is_url = any(t in spec for t in ("git+", "http://", "https://", "@ ", "file:"))
            if is_url and not allow_vcs:
                findings.append(_dep_finding("POLICY-DEP-EXTERNAL-SOURCE", spec,
                                             "Requirement uses a VCS/URL/external source"))
            elif require_pinned and "==" not in spec:
                findings.append(_dep_finding("POLICY-DEP-UNPINNED", spec,
                                             "Requirement is not exactly pinned (name==version)"))
            if name in dep_denylist:
                findings.append(_dep_finding("POLICY-DEP-DENIED", spec,
                                             "Dependency is on the policy denylist"))
            if allowed_deps and name not in allowed_deps:
                findings.append(_dep_finding("POLICY-DEP-NOT-ALLOWED", spec,
                                             "Dependency is not in the task's allowed_dependencies"))

        status = "fail" if any(f.blocking for f in findings) else "pass"
        return LayerResult(
            layer=self.name,
            status=status,
            blocking=any(f.blocking for f in findings),
            findings=findings,
            timing_ms=(time.perf_counter() - start) * 1000,
        )


def _dep_finding(rule_id: str, spec: str, message: str) -> Finding:
    return Finding(
        rule_id=rule_id,
        message=f"{message}: '{spec}'",
        severity="high",
        location="requirements",
        blocking=True,
    )
