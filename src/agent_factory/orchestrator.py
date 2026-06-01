"""Thin orchestrator: load -> generate/accept -> validate -> decide -> register.

Deliberately minimal (ARCHITECTURE.md §4). It wires ports together, runs the
chosen layer composition, builds the ValidationReport, and persists it. No
enterprise routing, no agent-reuse strategy.
"""

from __future__ import annotations

from pathlib import Path

from agent_factory.adapters.jsonl_telemetry import JsonlTelemetry
from agent_factory.adapters.sqlite_registry import SqliteRegistry
from agent_factory.adapters.stub_generator import ExistingArtifactGenerator, sha256_of
from agent_factory.decision import decide
from agent_factory.pipeline import CONDITIONS
from agent_factory.ports import ValidationContext
from agent_factory.schemas import TaskSpec, ValidationReport


def run_validation(
    task: TaskSpec,
    artifact_path: str | Path,
    *,
    condition: str = "full",
    run_id: str,
    created_at: str,
    reports_dir: str | Path = "data/reports",
    registry: SqliteRegistry | None = None,
    telemetry: JsonlTelemetry | None = None,
) -> ValidationReport:
    """Execute one validation run end-to-end and persist the result.

    `run_id` and `created_at` are injected (no hidden clock/uuid reads) to keep
    runs reproducible and the core free of ambient state.
    """
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown condition '{condition}'. Choices: {list(CONDITIONS)}")

    registry = registry or SqliteRegistry()
    telemetry = telemetry or JsonlTelemetry()

    # 1. Generate / accept artifact.
    generator = ExistingArtifactGenerator(artifact_path)
    agent_spec = generator.generate(task)
    artifact_hash = sha256_of(agent_spec.generated_code_path)
    source_code = Path(agent_spec.generated_code_path).read_text(encoding="utf-8")

    # 2. Run the chosen layer composition.
    ctx = ValidationContext(
        task_spec=task,
        agent_spec=agent_spec,
        artifact_hash=artifact_hash,
        source_code=source_code,
    )
    for layer in CONDITIONS[condition]:
        ctx.results.append(layer.run(ctx))

    # 3. Deterministic-first decision.
    final_decision, reasons = decide(ctx.results, ctx.judge_result)

    # 4. Build the report.
    report = ValidationReport(
        run_id=run_id,
        task_id=task.task_id,
        agent_id=agent_spec.agent_id,
        artifact_hash=artifact_hash,
        condition=condition,
        per_layer_status={r.layer: r.status for r in ctx.results},
        findings=[f for r in ctx.results for f in r.findings],
        timings={r.layer: round(r.timing_ms, 3) for r in ctx.results},
        sandbox_result=ctx.sandbox_result,
        judge_result=ctx.judge_result,
        final_decision=final_decision,
        reasons=reasons,
        model_metadata=agent_spec.model_metadata,
        created_at=created_at,
    )

    # 5. Persist: report JSON + registry row + telemetry line.
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{run_id}.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    registry.save(report, report_path=str(report_path))
    telemetry.append(
        {
            "run_id": run_id,
            "artifact_hash": artifact_hash,
            "task_id": task.task_id,
            "condition": condition,
            "per_layer_status": report.per_layer_status,
            "timings_ms": report.timings,
            "total_latency_ms": round(sum(report.timings.values()), 3),
            "final_decision": final_decision.value,
            "model_metadata": agent_spec.model_metadata,
            "created_at": created_at,
        }
    )

    return report
