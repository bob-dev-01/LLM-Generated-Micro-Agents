"""Thin orchestrator: load -> generate/accept -> validate -> decide -> register.

Deliberately minimal (ARCHITECTURE.md §4). It wires ports together, runs the
chosen layer composition, builds the ValidationReport, and persists it. No
enterprise routing, no agent-reuse strategy.
"""

from __future__ import annotations

from pathlib import Path

from agent_factory.adapters.jsonl_telemetry import JsonlTelemetry
from agent_factory.adapters.local_executor import LocalExecutor
from agent_factory.adapters.router import CapabilityRouter
from agent_factory.adapters.sqlite_registry import SqliteRegistry
from agent_factory.adapters.stub_generator import ExistingArtifactGenerator, sha256_of
from agent_factory.decision import decide
from agent_factory.pipeline import CONDITIONS
from agent_factory.ports import Executor, Router, ValidationContext
from agent_factory.schemas import (
    AgentSpec,
    Decision,
    TaskResult,
    Ticket,
    TaskSpec,
    ValidationReport,
)


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


def handle_ticket(
    ticket: Ticket,
    candidate_artifact_path: str | Path,
    *,
    run_id: str,
    created_at: str,
    registry: SqliteRegistry | None = None,
    telemetry: JsonlTelemetry | None = None,
    router: Router | None = None,
    executor: Executor | None = None,
    reports_dir: str | Path = "data/reports",
) -> TaskResult:
    """Full thin loop: route -> (reuse | generate -> validate -> register) -> execute.

    SAFETY BOUNDARY: a freshly generated agent is executed ONLY if it earns a
    PASS verdict from the validation pipeline. FAIL/ESCALATE agents are recorded
    but never executed. (Reused agents are already PASS by construction, since
    only validated agents enter the repertoire.)

    The MEASURED scientific contribution remains the validation gate; routing,
    reuse, and execution here are a demonstration of the surrounding system.
    """
    registry = registry or SqliteRegistry()
    telemetry = telemetry or JsonlTelemetry()
    router = router or CapabilityRouter(registry)
    executor = executor or LocalExecutor()
    task = ticket.task

    # 1. Routing: does a reusable agent already exist?
    existing = router.find_agent(task)
    if existing is not None:
        exec_res = executor.execute(existing, ticket.input_payload)
        reasons = ["reused existing validated agent (routing hit)"]
        if not exec_res.success:
            reasons.append(f"execution error: {exec_res.error}")
        return TaskResult(
            ticket_id=ticket.ticket_id,
            capability=task.capability,
            agent_id=existing.agent_id,
            reused=True,
            validation_decision=Decision.PASS,
            executed=exec_res.success,
            output=exec_res.output,
            reasons=reasons,
        )

    # 2. Miss: generate a candidate and validate it (full pipeline).
    report = run_validation(
        task,
        candidate_artifact_path,
        condition="full",
        run_id=run_id,
        created_at=created_at,
        reports_dir=reports_dir,
        registry=registry,
        telemetry=telemetry,
    )

    # 3. Safety gate: only a PASS agent may be registered and executed.
    if report.final_decision is not Decision.PASS:
        return TaskResult(
            ticket_id=ticket.ticket_id,
            capability=task.capability,
            agent_id=report.agent_id,
            artifact_hash=report.artifact_hash,
            reused=False,
            validation_decision=report.final_decision,
            executed=False,
            reasons=["generated agent did NOT pass validation; execution blocked", *report.reasons],
        )

    # 4. PASS: register into the reusable repertoire, then execute.
    agent_spec = AgentSpec(
        agent_id=report.agent_id,
        generated_code_path=str(candidate_artifact_path),
    )
    registry.register_agent(task.capability, agent_spec, report.artifact_hash, registered_at=created_at)
    exec_res = executor.execute(agent_spec, ticket.input_payload)
    reasons = ["agent passed validation; registered and executed"]
    if not exec_res.success:
        reasons.append(f"execution error: {exec_res.error}")
    return TaskResult(
        ticket_id=ticket.ticket_id,
        capability=task.capability,
        agent_id=report.agent_id,
        artifact_hash=report.artifact_hash,
        reused=False,
        validation_decision=Decision.PASS,
        executed=exec_res.success,
        output=exec_res.output,
        reasons=reasons,
    )
