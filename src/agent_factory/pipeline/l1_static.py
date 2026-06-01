"""Layer 1 - Static Analysis.

Walking-skeleton implementation: a REAL (if minimal) AST scan for dangerous
Python patterns, so the PASS/FAIL paths are genuine, not faked. The full MVP
adds Bandit integration and a richer rule set on top of this same contract.
"""

from __future__ import annotations

import ast
import time

from agent_factory.ports import ValidationContext
from agent_factory.schemas import Finding, LayerResult

# rule_id -> (dotted call / module of concern, human message, blocking?)
_DANGEROUS_CALLS = {
    "PY-EVAL": ("eval", "Use of eval()", True),
    "PY-EXEC": ("exec", "Use of exec()", True),
    "PY-COMPILE": ("compile", "Use of compile()", False),
    "PY-OS-SYSTEM": ("os.system", "Shell command execution via os.system()", True),
    "PY-DYN-IMPORT": ("__import__", "Dynamic import via __import__()", False),
}

_DANGEROUS_IMPORTS = {
    "PY-IMP-SUBPROCESS": ("subprocess", "Imports subprocess (process spawning)", True),
    "PY-IMP-SOCKET": ("socket", "Imports socket (network access)", True),
    "PY-IMP-CTYPES": ("ctypes", "Imports ctypes (native memory access)", True),
}


def _dotted_name(node: ast.AST) -> str:
    """Best-effort dotted name for a call target, e.g. os.system -> 'os.system'."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted_name(node.value)}.{node.attr}"
    return ""


class _DangerVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def _add(self, rule_id: str, message: str, blocking: bool, lineno: int) -> None:
        self.findings.append(
            Finding(
                rule_id=rule_id,
                message=message,
                severity="critical" if blocking else "medium",
                location=f"agent.py:{lineno}",
                blocking=blocking,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        target = _dotted_name(node.func)
        for rule_id, (needle, message, blocking) in _DANGEROUS_CALLS.items():
            if target == needle:
                self._add(rule_id, message, blocking, node.lineno)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._check_module(node.module, node.lineno)
        self.generic_visit(node)

    def _check_module(self, module: str, lineno: int) -> None:
        root = module.split(".")[0]
        for rule_id, (needle, message, blocking) in _DANGEROUS_IMPORTS.items():
            if root == needle:
                self._add(rule_id, message, blocking, lineno)


class StaticAnalysisLayer:
    """L1 - dangerous-pattern AST scan."""

    name = "L1_static"

    def run(self, ctx: ValidationContext) -> LayerResult:
        start = time.perf_counter()
        findings: list[Finding] = []
        status = "pass"

        try:
            tree = ast.parse(ctx.source_code, filename="agent.py")
        except SyntaxError as exc:
            findings.append(
                Finding(
                    rule_id="PY-SYNTAX",
                    message=f"Artifact does not parse: {exc.msg}",
                    severity="critical",
                    location=f"agent.py:{exc.lineno}",
                    blocking=True,
                )
            )
            return LayerResult(
                layer=self.name,
                status="fail",
                blocking=True,
                findings=findings,
                timing_ms=(time.perf_counter() - start) * 1000,
            )

        visitor = _DangerVisitor()
        visitor.visit(tree)
        findings = visitor.findings

        if any(f.blocking for f in findings):
            status = "fail"
        elif findings:
            status = "escalate"

        return LayerResult(
            layer=self.name,
            status=status,
            blocking=any(f.blocking for f in findings),
            findings=findings,
            timing_ms=(time.perf_counter() - start) * 1000,
        )
