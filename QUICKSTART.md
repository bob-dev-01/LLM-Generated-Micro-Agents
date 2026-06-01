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

## Benchmark over the labeled corpus

```bash
PY=.venv/Scripts/python.exe
$PY scripts/run_benchmark.py            # stub judge — free, no API calls
$PY scripts/run_benchmark.py --llm      # real Claude judge in the 'full' condition
```

Runs the 8-artifact corpus (`corpus/manifest.yaml`) under all three conditions and
writes [`BENCHMARK.md`](BENCHMARK.md) + `benchmark_results.json` with UAR / acceptance metrics.

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
| L4 Judge | **Real (opt-in)** | Anthropic Claude via `ModelClient` (structured output). Falls back to a deterministic stub when no client is injected, so offline runs still work. |

All four layers can now run for real. The judge (L4) and real agent generation
use the Anthropic API behind the `ModelClient` / `Generator` ports.

## LLM mode (Anthropic) — optional

Real judging and generation need the `llm` extra and an API key:

```bash
uv pip install --python .venv/Scripts/python.exe -e ".[dev,llm]"   # Windows
setx ANTHROPIC_API_KEY "sk-ant-..."        # or put it in a .env file (gitignored)
# optional, to save budget — default is claude-opus-4-8:
setx ANTHROPIC_MODEL "claude-haiku-4-5"
```

```bash
PY=.venv/Scripts/python.exe
# Validate an existing artifact with the REAL Claude judge:
$PY -m agent_factory.cli run --task examples/hello_task.yaml \
    --agent examples/agents/hello_agent.py --judge

# Full loop with REAL generation + REAL judge (no --candidate needed):
$PY -m agent_factory.cli ticket --task examples/hello_task.yaml \
    --generate --judge --input "[1,2,3,4]"
```

> **Cost note:** the judge is invoked only in the `full` condition. With Haiku 4.5 a
> judge call is well under a cent; with Opus 4.8 it is a few cents. Set
> `ANTHROPIC_MODEL=claude-haiku-4-5` for cheap dev/benchmark runs.
> Live LLM tests (`tests/test_llm.py`) skip automatically unless `ANTHROPIC_API_KEY` is set.

> **Safety short-circuit:** if L1/L2 raise a blocking violation, the pipeline stops
> *before* L3 — known-dangerous code is never executed in the sandbox.
