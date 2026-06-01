# Walking Skeleton — Quickstart

A runnable end-to-end proof of the `generate → validate → decide → register` pipe.
**No Docker daemon and no LLM key are needed** for the skeleton: L1 (static analysis)
is real; L2 (policy), L3 (sandbox), L4 (judge) are structural stubs behind their
real interfaces (see `ARCHITECTURE.md` §4).

## Setup

```bash
# from the repo root
uv venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"   # Windows
# (Linux/macOS: source .venv/bin/activate && uv pip install -e ".[dev]")
```

## Run

```bash
# Safe agent -> PASS
.venv/Scripts/python.exe -m agent_factory.cli run \
    --task examples/hello_task.yaml --agent examples/agents/hello_agent.py

# Adversarial agent -> FAIL (blocking L1 findings)
.venv/Scripts/python.exe -m agent_factory.cli run \
    --task examples/hello_task.yaml --agent examples/agents/evil_agent.py

# Mini-benchmark: all three conditions (static_only / static_policy / full)
.venv/Scripts/python.exe -m agent_factory.cli bench \
    --task examples/hello_task.yaml --agent examples/agents/hello_agent.py
```

## Full loop (route → reuse | generate → validate → execute)

```bash
PY=.venv/Scripts/python.exe

# 1. capability "sum-integers" not yet known -> generate, validate, register, execute
$PY -m agent_factory.cli ticket --task examples/hello_task.yaml \
    --candidate examples/agents/hello_agent.py --input "[1,2,3,4]"      # -> {"sum": 10}

# 2. same capability -> routing hit, reuse the validated agent (no re-validation)
$PY -m agent_factory.cli ticket --task examples/hello_task.yaml \
    --candidate examples/agents/hello_agent.py --input "[100,200]"      # -> {"sum": 300}

# 3. unsafe generated agent -> FAILS validation -> NOT EXECUTED (safety gate)
$PY -m agent_factory.cli ticket --task examples/danger_task.yaml \
    --candidate examples/agents/evil_agent.py --input "{}"              # -> NOT EXECUTED
```

> The full loop is demonstrated, but the **measured** contribution stays the validation gate.
> Routing here is an exact `capability` match; execution runs locally only because the agent
> already passed validation (in production it routes through the L3 sandbox).

## What to look at

| Output | Demonstrates |
|---|---|
| Safe agent → **PASS**, evil agent → **FAIL** | Real static-analysis gate (AST scan), not a fake |
| Evil agent: L4 judge = `pass` but decision = **FAIL** | **Invariant R1** — the judge can never override a blocking deterministic finding (ADR-004) |
| `bench` runs 3 conditions with no branching | Conditions are layer *compositions* (ADR-006) |
| `data/reports/<run_id>.json` | Complete machine-readable `ValidationReport` per run |
| `data/registry.db` | SQLite registry keyed by SHA-256 artifact hash (ADR-002) |
| `data/telemetry.jsonl` | One provenance-carrying record per run (for DuckDB/pandas) |

## Test & lint

```bash
.venv/Scripts/python.exe -m pytest -q        # 4 smoke tests, incl. the R1 invariant
.venv/Scripts/python.exe -m ruff check src tests
```

## What is real vs stubbed in the skeleton

| Layer | Status | Notes |
|---|---|---|
| L1 Static | **Real** | AST scan (`eval/exec/os.system/subprocess/socket/ctypes`). POC-1 adds Bandit + richer rules. |
| L2 Policy | **Real** | YAML policy (`policies/default.yaml`): per-task import allowlist + global denylist + supply-chain (pinning, VCS/URL, allow/deny). Optional pip-audit is off by default (needs network). |
| L3 Sandbox | **Real** | Hardened Docker runner (`--network=none`, `--cap-drop=ALL`, read-only + tmpfs, non-root, mem/cpu/pids limits, timeout). Degrades to `skip` if Docker is unavailable. |
| L4 Judge | Stub | Deterministic high-confidence pass; sanitized-evidence pack already built. POC-1 wires a real model call via `ModelClient` (needs LLM endpoint). |

Deterministic layers (L1+L2+L3) are now real; only the LLM judge (L4) remains a
stub. Deepening it is "fill in behind the interface," not re-architecting.

> **Safety short-circuit:** if L1/L2 raise a blocking violation, the pipeline stops
> *before* L3 — known-dangerous code is never executed in the sandbox.
