# Automated Validation Pipeline for LLM-Generated Micro-Agents

[![CI](https://github.com/bob-dev-01/LLM-Generated-Micro-Agents/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bob-dev-01/LLM-Generated-Micro-Agents/actions/workflows/ci.yml)

> Design and Evaluation of an Automated Validation Pipeline for LLM-Generated Micro-Agents in Enterprise Multi-Agent Systems — **Revised MVP scope**.

This repository implements a layered **validation pipeline** that decides whether a newly generated Python micro-agent is safe and correct enough to be registered or executed. A single linear workflow takes a task specification and a generated agent artifact, runs four validation layers, and emits a structured decision: **PASS / FAIL / ESCALATE**.

| | |
|---|---|
| **Student** | Bobur Yusupov |
| **Scientific advisor** | Viktor Kauk |
| **Industry expert** | Izzet Mustafayev |
| **Implementation window** | 12 weeks, individual work |

**Companion documents:** [`ARCHITECTURE.md`](ARCHITECTURE.md) — local PoC solution architecture (C4 + ADRs) · [`ARCHITECTURE_ENTERPRISE.md`](ARCHITECTURE_ENTERPRISE.md) — cloud-native enterprise target state (Azure) · [`QUICKSTART.md`](QUICKSTART.md) — run the walking skeleton.

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Goal & Research Claim](#2-goal--research-claim)
3. [Scope: MVP vs Optional](#3-scope-mvp-vs-optional)
4. [Architecture](#4-architecture)
5. [Core Schemas](#5-core-schemas)
6. [The Four Validation Layers](#6-the-four-validation-layers)
7. [Decision Logic](#7-decision-logic)
8. [Registry & Telemetry](#8-registry--telemetry)
9. [Evaluation / Benchmark Design](#9-evaluation--benchmark-design)
10. [Metrics](#10-metrics)
11. [Technology Stack](#11-technology-stack)
12. [12-Week Plan & Fallback Triggers](#12-12-week-plan--fallback-triggers)
13. [Expected Deliverables](#13-expected-deliverables)
14. [Proposed Implementation (Recommendations)](#14-proposed-implementation-recommendations) ← *additions beyond the source spec*

---

## 1. Motivation

Enterprises face many **long-tail automation tasks**: one-off configuration-drift checks, ad-hoc data transformations, simple compliance checks, operational data cleaning. They are too specific to justify pre-built scripts, but too frequent or urgent for fully manual handling. Multi-agent LLM frameworks can route such work between specialized agents, but their repertoire is usually fixed in advance.

The **Agent Factory** idea fills this gap by generating narrowly scoped micro-agents on demand. But dynamic generation creates a solution-architecture problem: a generated agent may contain unsafe behavior, dependency risk, incorrect logic, or prompt-injection-sensitive output. An enterprise system therefore **cannot generate and execute agents directly in production** — a validation layer is required first.

This project implements that validation layer as its core, scoped as an **MVP-first research implementation** rather than a full production platform.

### 1.1 The full system loop (demonstrated) and the measured boundary

The surrounding system is the **Agent Factory loop**: a request (ticket) arrives, the system checks whether a suitable agent already exists, and either reuses it or generates a new one — and a newly generated agent is **only allowed to run after it passes validation**.

```
   Ticket / request
        │
        ▼
   Router: "is there already an agent for this capability?"
        │
   ┌────┴─────┐
   │ yes      │ no
   ▼          ▼
 Reuse      Generate new agent
 agent          │
   │            ▼
   │      VALIDATION GATE  ── FAIL / ESCALATE ──► not executed
   │      (4 layers →                              (safety boundary)
   │       PASS/FAIL/ESCALATE)
   │            │ PASS
   │            ▼
   │      Register into repertoire
   └────┬───────┘
        ▼
   Execute task → result
```

> **Scope discipline.** The full loop (routing, reuse, generation, execution) is **built and demonstrated** end-to-end, but the **rigorously measured scientific contribution is the validation gate only** — routing and execution are intentionally thin and are *not* part of the benchmark. This keeps the thesis defensible: one mechanism is evaluated well, while the working loop shows how it embeds in the larger system. Try it: `agent-factory ticket ...` (see [`QUICKSTART.md`](QUICKSTART.md)).

## 2. Goal & Research Claim

**Goal.** Design, implement, and evaluate a layered validation pipeline for LLM-generated Python micro-agents. The system accepts a task specification + a generated agent artifact, runs a sequence of deterministic and LLM-assisted checks, and produces a structured PASS / FAIL / ESCALATE decision.

**Research claim (narrowed).** Test whether a layered validation pipeline **reduces unsafe acceptances** compared with lighter baselines, while keeping **latency, cost, and reproducibility** within practical limits. The deliverable is a reproducible validator module + evaluation framework, **not** a complete enterprise Agent Factory.

**Guiding principle.** *The thesis should build and evaluate one measurable mechanism well* — that mechanism is the validation pipeline. Orchestrator, registry, cloud, and governance integrations exist only to the extent needed to demonstrate and evaluate the validator.

## 3. Scope: MVP vs Optional

### Scope-reduction decisions

| Scope area | Revised decision | Reason |
|---|---|---|
| Primary contribution | Layered validation pipeline | Core research mechanism, directly evaluable |
| Orchestrator | Thin stub only | Enough to show generate → validate → decide |
| Registry | SQLite + artifact hashes | Sufficient for reproducibility/traceability |
| Sandboxing | One hardened Docker path | Meaningful isolation without multi-runtime complexity |
| Experiment size | 720 planned runs | Large enough; smaller than original 2,700-run design |
| Cloud services | Optional Azure-light | Avoids cloud quotas / managed-runtime uncertainty |

### Component matrix

| Component | MVP | Mandatory | Optional | Notes |
|---|:--:|:--:|:--:|---|
| Task specification schema | ✅ | ✅ | — | task ID, I/O schema, allowed tools, risk tier, acceptance tests |
| AgentSpec / artifact schema | ✅ | ✅ | — | generated code, manifest, deps, resource limits, policy metadata |
| Thin orchestrator stub | ✅ | ✅ | — | invokes generation, validation, registry write, final decision |
| Static analysis layer | ✅ | ✅ | — | Bandit + custom AST rules |
| Policy & supply-chain layer | ✅ | ✅ | — | YAML allow/denylist, pinning, hashes, index restrictions |
| Sandboxed execution layer | ✅ | ✅ | — | one Docker sandbox: no network, CPU/mem limits, timeout, tmpfs |
| LLM-as-a-Judge layer | ✅ | ✅ | — | structured-output judge on sanitized evidence; deterministic findings win |
| Lightweight registry | ✅ | ✅ | — | SQLite: hash, decision, timestamps, report path |
| JSONL telemetry | ✅ | ✅ | — | per-run structured logs |
| Multi-tier sandbox benchmark | — | — | ⭕ | gVisor / ACI comparison, post-MVP |
| Azure PostgreSQL + Key Vault | — | — | ⭕ | enterprise registry, unnecessary for MVP |
| angr symbolic execution | — | — | ⭕ | high effort, less aligned with Python source |
| NVivo interview analysis | — | — | ⭕ | only if degree rubric requires + time allows |

## 4. Architecture

The architecture is intentionally **linear and reproducible**:

```
TaskSpec
   │
   ▼
Generator  ──or──►  Existing AgentSpec
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  VALIDATION PIPELINE                                      │
│                                                           │
│  L1 Static Analysis ─► L2 Policy & Supply-Chain ─►        │
│  L3 Docker Sandbox  ─► L4 Structured LLM Judge            │
└─────────────────────────────────────────────────────────┘
   │
   ▼
Final Decision  (PASS / FAIL / ESCALATE)
   │
   ├──► SQLite Registry  (artifact hash, decision, report path)
   └──► JSONL Telemetry  (per-run metrics)
```

**Thin orchestrator & generation harness.** The orchestrator does *not* implement enterprise routing or agent-reuse strategy. It loads the TaskSpec, calls the generator (or accepts an existing artifact), submits the artifact to the pipeline, writes the report, and returns the decision. The generator may use **AutoGen AgentChat (pinned)** with one OpenAI-compatible endpoint; generated output is converted to a strict `AgentSpec` before validation. If generation quality is a bottleneck, only the generator model is upgraded — the rest of the pipeline stays stable.

## 5. Core Schemas

All inputs/outputs are explicit **Pydantic v2** schemas to remove hidden assumptions and support reproducible evaluation.

| Schema | Minimum fields |
|---|---|
| **TaskSpec** | `task_id`, `task_description`, `input_schema`, `output_schema`, `allowed_imports`, `allowed_dependencies`, `prohibited_behaviors`, `risk_tier`, `acceptance_tests` |
| **AgentSpec** | `agent_id`, `generated_code_path`, `manifest`, `requirements`, `declared_tools`, `resource_limits`, `expected_entrypoint`, `model_metadata` |
| **ValidationReport** | `artifact_hash`, `per_layer_status`, `findings`, `timings`, `sandbox_result`, `judge_result`, `final_decision`, `reasons`, `report_version` |

## 6. The Four Validation Layers

Each layer is implemented in the **simplest testable form**.

| Layer | MVP implementation | Output |
|---|---|---|
| **L1 — Static Analysis** | Bandit scan + custom Python AST rules for `eval`/`exec`, dynamic import, `subprocess`, socket/network, filesystem writes, `ctypes`. | Static findings: severity, rule ID, location, blocking/non-blocking status. |
| **L2 — Policy & Supply Chain** | YAML policy engine enforcing allow/denylists; dependency checks for pinned versions, hashes, forbidden external indexes. | Policy violations, dependency status, escalation flags. |
| **L3 — Sandboxed Execution** | One hardened Docker sandbox: `--network=none`, CPU/memory limits, timeout, no privileged mode, tmpfs workspace. | Exit code, timeout, test results, wall time, CPU time, memory usage, sandbox violations. |
| **L4 — LLM-as-a-Judge** | Single structured-output judge receiving **only sanitized evidence**; returns correctness score, safety risk, decision, reasons. | Judge JSON + uncertainty flag. **Deterministic security findings override judge approval.** |

## 7. Decision Logic

The decision is based on **deterministic evidence first, LLM judgment second**. The judge **cannot override a hard security failure**. Ambiguous cases are escalated, never accepted.

| Condition | Decision |
|---|---|
| Hard static-analysis violation or forbidden policy violation | **FAIL** |
| Sandbox timeout, resource violation, blocked network attempt, or failed mandatory acceptance tests | **FAIL or ESCALATE** (by severity) |
| No deterministic violation, acceptance tests pass, but judge score ambiguous | **ESCALATE** |
| No deterministic violation, tests pass, judge returns high-confidence correctness | **PASS** |
| Conflicting evidence between deterministic layers and judge | **ESCALATE** (deterministic evidence shown first) |

## 8. Registry & Telemetry

**Registry — SQLite.** Stores only traceability metadata: task ID, artifact hash (SHA-256), final decision, validation timestamp, report path, model metadata, optional HMAC signature. Avoids PostgreSQL / Key Vault / embedding-signature complexity while preserving the integrity concept.

**Telemetry — JSONL.** Every run appends one structured record. Initial analysis with Python + pandas; optional R scripts for statistical tests and plots. OpenTelemetry / Azure Monitor / Application Insights are deferred until the core JSONL pipeline is stable.

### Expected functionality

1. Accept a structured TaskSpec + generated Python artifact.
2. Validate through static analysis, policy checks, sandboxed execution, and structured LLM judging.
3. Return PASS / FAIL / ESCALATE with a short explanation and per-layer evidence.
4. Generate a machine-readable `ValidationReport` JSON per run.
5. Store artifact hash, final decision, and report location in SQLite.
6. Append reproducible telemetry to JSONL logs.
7. Support a controlled benchmark across static-only, static + policy, and full-pipeline conditions.

## 9. Evaluation / Benchmark Design

A **quantitative controlled benchmark**: the same curated artifact corpus is run under three conditions to test whether added layers reduce unsafe acceptances and what overhead they introduce.

| Condition | Included layers | Purpose |
|---|---|---|
| **Static-only baseline** | Bandit + AST rules | Performance of lightweight code inspection |
| **Static + policy** | + YAML policy & dependency checks | Benefit of deterministic policy enforcement |
| **Full pipeline** | + Docker sandbox + LLM judge | Effect of layering on safety, correctness, latency, cost |

### Experiment corpus — 720 runs

| Set | Size | Purpose | Primary metrics |
|---|---|---|---|
| Pilot corpus | 24 × 3 = **72** | Calibrate thresholds, detect flakiness, estimate latency | Completion rate, p95 latency, report completeness |
| Main benign corpus | 48 × 3 × 2 = **288** | Measure overblocking, correctness, latency, cost | Valid acceptance rate, escalation rate, latency, cost |
| Main risky corpus | 72 × 3 × 2 = **432** | Measure unsafe-acceptance reduction | Unsafe acceptance rate, fail/escalate rate, latency |
| Manual adjudication | **50** sampled cases | Judge usefulness + error taxonomy | Judge-human agreement, confusion matrix, false overrides |

## 10. Metrics

| Metric | Definition |
|---|---|
| **Unsafe Acceptance Rate (UAR)** | Share of unsafe/policy-violating agents incorrectly accepted |
| **False Positive Rate (FPR)** | Share of safe & correct agents incorrectly failed/escalated |
| **False Negative Rate (FNR)** | Share of unsafe/incorrect agents accepted as pass |
| **Task Success Rate (TSR)** | Share passing mandatory functional acceptance tests |
| **Validation latency** | End-to-end and per-layer runtime: median, p95, p99 |
| **Cost per validation** | Estimated model cost per run from token usage + pricing |
| **Escalation Rate** | Share routed to human review (uncertainty / conflict) |
| **Report completeness** | Share of runs with complete structured reports + hashes |

## 11. Technology Stack

| Layer / Role | Tool | Purpose | Status |
|---|---|---|---|
| Language & schemas | Python 3.11+, Pydantic v2 | Implementation + schema validation | **Mandatory** |
| Agent harness | AutoGen AgentChat (pinned) | Thin generator/orchestrator harness | **Mandatory** |
| Model endpoint | Anthropic Claude (implemented) via `ModelClient` port; OpenAI-compatible / Azure OpenAI are drop-in alternatives | Generation + structured-output judge | **Mandatory** |
| Static analysis | Bandit + custom AST rules | Detect dangerous Python patterns | **Mandatory** |
| Dependency/security audit | pip-audit, pinned reqs, hash enforcement | Vulnerable-dep detection, supply-chain risk | **Mandatory** |
| Policy engine | YAML policy + deterministic Python checker | Allow/denylist for imports, deps, tools, network, fs | **Mandatory** |
| Sandbox | Docker Engine on Linux | Controlled execution, no network, limits, timeout, tmpfs | **Mandatory** |
| Registry | SQLite + SHA-256 hashes | Reproducible metadata + decisions, no DB server | **Mandatory** |
| Telemetry | JSONL, pandas, optional R | Metrics + plots for evaluation chapter | **Mandatory** |
| CI | pytest, pre-commit, GitHub Actions | Unit/smoke tests, formatting, light security checks | **Mandatory** |
| Threat mapping | MITRE ATLAS | Categorize adversarial patterns | Recommended ext. |
| Static-analysis ext. | Semgrep taint rules / CrossHair | Extra source-level analysis if stable | Optional |
| Cloud registry | Azure PostgreSQL + Key Vault | Enterprise registry + key management | Optional |
| Cloud execution | Azure VM / ACI / Container Apps jobs | Alternative execution backend | Optional |
| Advanced sandboxing | gVisor / runsc | Extra isolation tier, post-MVP | Optional |

**Default deployment target:** one Linux-capable host running Python + Docker. Azure can be a single VM if cloud-hosted execution is needed; managed Azure services are not mandatory for the MVP.

## 12. 12-Week Plan & Fallback Triggers

| Period | Stage | Deliverables |
|---|---|---|
| Weeks 1–2 | Scope freeze & repo setup | Final schemas, Git repo, CI skeleton, sample tasks, smoke-test corpus |
| Weeks 2–3 | Generator harness + deterministic base | AutoGen generation stub, Bandit integration, AST rules, initial YAML policy |
| Weeks 3–4 | Docker sandbox + registry | Hardened Docker runner, resource limits, timeout, SQLite registry, hashing |
| Weeks 4–5 | LLM judge + report schema | Judge schema, sanitized evidence pack, escalation rules, full ValidationReport JSON |
| Week 5 | Pilot run & scope lock | 72-run pilot, latency estimate, flakiness report, decision on optional features |
| Weeks 6–8 | Main benchmark | 720 runs, JSONL telemetry, registry snapshots, reproducibility logs |
| Weeks 8–9 | Manual adjudication | 50-case review, judge-human comparison, error taxonomy |
| Weeks 9–10 | Quantitative analysis | Metrics tables, latency plots, UAR comparison, cost estimates |
| Weeks 10–12 | Writing & packaging | Code package, docs, reproducibility guide, thesis chapter, defense materials |

### Fallback triggers

| Trigger | Fallback action |
|---|---|
| Schemas & smoke tests unstable by end of Week 2 | Remove all cloud extensions from the plan |
| Fewer than 24 artifacts complete end-to-end in pilot | Freeze scope to deterministic layers + Docker; judge advisory only |
| p95 latency exceeds predeclared ceiling in pilot | Reduce repeats, optimize sandbox/test execution before adding features |
| Judge-human agreement below 70% on calibration | Use judge as explanatory/assistive only; deterministic layers authoritative |
| Docker sandbox flaky above 20% of runs | Reduce corpus, remove parallelism, run sequentially on one host |

## 13. Expected Deliverables

1. A working open-source validation pipeline for generated Python micro-agents.
2. Strict TaskSpec, AgentSpec, ValidationReport schemas (Pydantic).
3. Static analysis layer (Bandit + custom AST rules).
4. Deterministic policy & supply-chain layer (YAML rules, pinned deps, package-safety checks).
5. A hardened Docker sandbox runner for functional execution + resource enforcement.
6. A structured-output LLM judge routing ambiguous cases to escalation.
7. A lightweight SQLite registry with artifact hashes + decisions.
8. A JSONL telemetry dataset + metric computation scripts.
9. A 720-run benchmark across the three conditions.
10. A thesis-ready architecture specification + reproducibility package.

---

## 14. Proposed Implementation (Recommendations)

> This section contains **my engineering recommendations** beyond the source specification. It is advisory and does not change the mandatory MVP scope above.

### 14.1 Proposed repository structure

```
agent-factory/
├── README.md
├── pyproject.toml              # deps + tool config (ruff, pytest, mypy)
├── requirements.lock           # pinned + hashed (pip-compile --generate-hashes)
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── policies/
│   └── default.yaml            # allow/denylists, dependency rules, index restrictions
├── src/agent_factory/
│   ├── schemas/                # Pydantic v2: TaskSpec, AgentSpec, ValidationReport
│   │   ├── task_spec.py
│   │   ├── agent_spec.py
│   │   └── report.py
│   ├── orchestrator.py         # thin: load → generate/accept → validate → register
│   ├── generator/
│   │   └── autogen_harness.py  # pinned AutoGen + OpenAI-compatible endpoint
│   ├── pipeline/
│   │   ├── base.py             # Layer protocol: run(ctx) -> LayerResult
│   │   ├── l1_static.py        # Bandit + AST visitor
│   │   ├── l2_policy.py        # YAML policy + pip-audit
│   │   ├── l3_sandbox.py       # Docker runner
│   │   ├── l4_judge.py         # structured-output judge
│   │   └── decision.py         # deterministic-first decision function
│   ├── registry/sqlite_store.py
│   └── telemetry/jsonl_writer.py
├── corpus/
│   ├── benign/                 # 48 artifacts + acceptance tests
│   ├── risky/                  # 72 adversarial artifacts (+ MITRE ATLAS tags)
│   └── pilot/                  # 24 calibration artifacts
├── scripts/
│   ├── run_benchmark.py        # sweeps {static-only, static+policy, full} × corpus
│   └── compute_metrics.py      # pandas → metrics tables + plots
└── tests/                      # unit + smoke tests per layer
```

### 14.2 Layer contract (uniform interface)

Recommend a single `Layer` protocol so layers are composable, independently testable, and so benchmark conditions are just *layer subsets*:

```python
class LayerResult(BaseModel):
    layer: str
    status: Literal["pass", "fail", "escalate", "skip"]
    blocking: bool
    findings: list[Finding]
    timing_ms: float

class Layer(Protocol):
    name: str
    def run(self, ctx: ValidationContext) -> LayerResult: ...
```

The three benchmark conditions then become declarative pipeline definitions (`[L1]`, `[L1, L2]`, `[L1, L2, L3, L4]`) — no branching code, which keeps results comparable and reproducible.

### 14.3 Determinism & reproducibility

- **Pin everything**: model name + version, AutoGen version, Docker base image by digest (`@sha256:...`), `temperature=0` for both generator and judge.
- **Seed the corpus**, store each artifact with its SHA-256 in the registry, and record `(model_metadata, policy_hash, image_digest)` in every JSONL record so any run is fully reconstructable.
- **Judge isolation**: feed the judge only sanitized, structured evidence (never raw agent output) to limit prompt-injection of the validator itself — this is itself a defensible research point worth measuring.

### 14.4 Sandbox hardening checklist (L3)

Beyond `--network=none` + limits, recommend: `--read-only` root fs + tmpfs workspace, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--pids-limit`, non-root user, and a hard wall-clock timeout enforced by the host (not only inside the container). Capture violations as structured findings.

### 14.5 Windows note (current dev host)

Docker layer (L3) requires a Linux execution context. On this Windows host, run L3 via **WSL2 + Docker Desktop** or a single Azure Linux VM. Recommend running the full benchmark on **one fixed Linux host** to keep latency/flakiness numbers comparable (aligns with the fallback trigger on flaky sandbox results).

### 14.6 Suggested early milestones (de-risking)

1. **Walking skeleton first**: TaskSpec → trivial generated agent → all four layers returning stub results → ValidationReport written → SQLite row + JSONL line. Prove the *pipe* end-to-end before deepening any single layer.
2. Build the **risky corpus taxonomy** early (mapped to MITRE ATLAS) so L1/L2 rules are written against concrete adversarial cases, not in the abstract.
3. Lock a **predeclared p95 latency ceiling** and **judge-agreement threshold** before the pilot, so the fallback triggers are objective.

### 14.7 Open questions for next iteration

- **Risk tiers**: how many tiers in `TaskSpec.risk_tier`, and do they change layer thresholds (e.g. high-tier → judge non-ambiguous required)?
- **Acceptance-test format**: pytest files shipped with each artifact, or declarative I/O examples checked by the harness?
- **Cost accounting**: track judge tokens only, or generation tokens too (since the generator is in the harness)?
- **Escalation sink**: for the MVP, does ESCALATE just mark the record, or is there a minimal human-review queue/CLI?

These don't block the walking skeleton — flag for discussion once L1–L4 stubs are wired.
