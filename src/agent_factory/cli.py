"""Typer CLI for the validation pipeline.

    agent-factory run   --task examples/hello_task.yaml --agent examples/agents/hello_agent.py
    agent-factory run   --task examples/hello_task.yaml --agent examples/agents/evil_agent.py
    agent-factory bench --task examples/hello_task.yaml --agent examples/agents/hello_agent.py
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml

from agent_factory.orchestrator import run_validation
from agent_factory.pipeline import CONDITIONS
from agent_factory.schemas import Decision, TaskSpec

app = typer.Typer(add_completion=False, help="LLM micro-agent validation pipeline (MVP).")

_DECISION_COLOR = {
    Decision.PASS: typer.colors.GREEN,
    Decision.FAIL: typer.colors.RED,
    Decision.ESCALATE: typer.colors.YELLOW,
}


def _load_task(task_path: Path) -> TaskSpec:
    data = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    return TaskSpec.model_validate(data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.command()
def run(
    task: Path = typer.Option(..., exists=True, help="Path to a TaskSpec YAML file."),
    agent: Path = typer.Option(..., exists=True, help="Path to the Python artifact."),
    condition: str = typer.Option("full", help=f"One of {list(CONDITIONS)}."),
) -> None:
    """Validate one artifact under one condition and print the decision."""
    task_spec = _load_task(task)
    report = run_validation(
        task_spec,
        agent,
        condition=condition,
        run_id=uuid.uuid4().hex[:12],
        created_at=_now_iso(),
    )

    typer.echo("")
    typer.echo(f"  run_id        {report.run_id}")
    typer.echo(f"  artifact_hash {report.artifact_hash[:16]}...")
    typer.echo(f"  condition     {report.condition}")
    typer.echo(f"  layers        {report.per_layer_status}")
    if report.findings:
        typer.echo("  findings:")
        for f in report.findings:
            mark = "BLOCK" if f.blocking else " warn"
            typer.echo(f"    [{mark}] {f.rule_id} @ {f.location}: {f.message}")
    typer.echo("")
    typer.secho(
        f"  DECISION: {report.final_decision.value}",
        fg=_DECISION_COLOR[report.final_decision],
        bold=True,
    )
    for r in report.reasons:
        typer.echo(f"    - {r}")
    typer.echo("")


@app.command()
def bench(
    task: Path = typer.Option(..., exists=True, help="Path to a TaskSpec YAML file."),
    agent: Path = typer.Option(..., exists=True, help="Path to the Python artifact."),
) -> None:
    """Run all three conditions on one artifact (mini-benchmark demo)."""
    task_spec = _load_task(task)
    typer.echo("")
    typer.echo(f"  {'condition':<16} decision     latency_ms")
    typer.echo(f"  {'-' * 40}")
    for cond in CONDITIONS:
        report = run_validation(
            task_spec,
            agent,
            condition=cond,
            run_id=uuid.uuid4().hex[:12],
            created_at=_now_iso(),
        )
        latency = round(sum(report.timings.values()), 2)
        typer.secho(
            f"  {cond:<16} {report.final_decision.value:<12} {latency}",
            fg=_DECISION_COLOR[report.final_decision],
        )
    typer.echo("")


if __name__ == "__main__":
    app()
