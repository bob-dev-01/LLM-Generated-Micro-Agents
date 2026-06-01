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

| Layer | Skeleton | POC-1 |
|---|---|---|
| L1 Static | **Real** AST scan (`eval/exec/os.system/subprocess/socket/ctypes`) | + Bandit, richer rules |
| L2 Policy | Stub (`pass`) | YAML allow/denylist + pip-audit on pinned+hashed deps |
| L3 Sandbox | Stub (simulated clean run) | Hardened Docker runner (needs Docker daemon) |
| L4 Judge | Stub (deterministic high-confidence pass; sanitized-evidence pack already built) | Real model call via `ModelClient` (needs LLM endpoint) |

The contracts, schemas, decision logic, registry, and telemetry are all real —
deepening each layer is now "fill in behind the interface," not re-architecting.
