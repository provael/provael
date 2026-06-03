# vla-redteam · `robopwn`

> Red-team open **Vision-Language-Action (VLA)** robot policies in simulation and
> report an **Attack Success Rate (ASR)**.

`vla-redteam` is a small, **model-agnostic** harness. It perturbs the instructions a
VLA policy receives inside a simulator and measures how often those perturbations drive
the policy into an *unsafe* state. The headline number is the ASR.

The entire core — abstractions, attacks, scoring, runner, report, CLI — runs and is
tested on a **plain CPU with no GPU and no model/dataset download**, using a
deterministic `StubPolicy` + `StubSuite`. Real policies (e.g. SmolVLA via LeRobot) live
behind an optional extra and a `ROBOPWN_INTEGRATION=1` gate.

> ⚠️ This is a **defensive, sim-only** tool for hardening policies via responsible
> disclosure. It drives no physical robots and ships no real-world-harm payloads.
> Read **[SAFETY.md](SAFETY.md)** before using it.

## Install (CPU core — no GPU, no network)

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync                      # creates a venv and installs the CPU core + dev tools
```

Or with pip:

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e .             # core only; lerobot is NOT pulled in
```

## Quickstart (runs in well under 5 s on a CPU)

```bash
uv run robopwn attack --policy stub --suite stub --attacks instruction \
    --episodes 10 --seed 0 --out runs/stub/
```

```
              RoboPwn — ASR by attack
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ attack            ┃   ASR ┃ successes ┃ attempts ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ goal_substitution │ 60.0% │         6 │       10 │
│ paraphrase        │ 70.0% │         7 │       10 │
│ roleplay          │ 80.0% │         8 │       10 │
└───────────────────┴───────┴───────────┴──────────┘
Attack Success Rate (ASR): 70.0% (21/30)
```

This writes `runs/stub/report.json` (machine-readable, byte-deterministic) and
`runs/stub/report.md`.

Other commands:

```bash
uv run robopwn list-policies     # stub (CPU) and smolvla (needs the [lerobot] extra)
uv run robopwn list-attacks      # roleplay, goal_substitution, paraphrase (family: instruction)
uv run robopwn report --in runs/stub/
uv run robopwn version
```

## What runs on CPU vs. what needs a GPU

| Capability | CPU (default) | Needs GPU + `[lerobot]` extra |
| --- | :---: | :---: |
| `stub` policy + `stub` suite | ✅ | |
| `instruction` attacks, scoring, runner, report, CLI | ✅ | |
| Full test suite (`pytest`), `ruff`, `mypy` | ✅ | |
| `smolvla` policy (real SmolVLA via LeRobot) | | ✅ |
| LIBERO simulator evaluation | | ✅ |

On CPU, `--policy smolvla` fails with a clear, actionable message (not a traceback)
telling you exactly what to install.

## Verified environment

Resolved on the machine that built this release (2026-06-03):

| | |
| --- | --- |
| OS | macOS 26.5 (arm64, Apple Silicon) |
| Python | 3.12.7 |
| uv | 0.9.18 |
| **Core (CPU)** | numpy 2.2.6 · pydantic 2.13.4 · typer 0.26.6 · rich 15.0.0 · pyyaml 6.0.3 |
| **Dev** | pytest 9.0.3 · pytest-cov 7.1.0 · ruff 0.15.15 · mypy 2.1.0 · types-PyYAML 6.0.12.20260518 |
| **Optional `[lerobot]`** (resolved + introspected in an isolated venv) | lerobot 0.5.1 · torch 2.10.0 · transformers 5.3.0 |

Verified results on this machine: `ruff check .` clean · `mypy src` clean ·
`pytest` → **37 passed, 2 skipped** (the 2 skips are the GPU-gated LeRobot integration
tests) · `robopwn attack` completes in well under a second.

> The LeRobot adapter was written **after introspecting the installed
> `lerobot==0.5.1`** — every symbol and signature it calls was confirmed against the
> real package (see the adapter docstring and CHANGELOG), not guessed.

## The real SmolVLA + LIBERO path (GPU box)

Nothing here runs in CI or on the CPU core. On a provisioned (GPU) machine:

```bash
# 1. Install the extra (pulls lerobot[smolvla]==0.5.1: transformers, torch, …)
pip install 'vla-redteam[lerobot]'

# 2. For the LIBERO simulator, also install LeRobot's LIBERO extra
pip install 'lerobot[libero]==0.5.1'

# 3. Run the gated integration test (loads SmolVLA, checks the verified pipeline)
ROBOPWN_INTEGRATION=1 pytest tests/test_lerobot_adapter.py -q
```

Today, end-to-end SmolVLA-on-LIBERO evaluation is done with LeRobot's own evaluator
(the full LIBERO `SuiteAdapter` is Part 2):

```bash
lerobot-eval --policy.path=lerobot/smolvla_base \
    --env.type=libero --env.task=libero_object   # or libero_10 / libero_spatial / libero_goal
```

## How it works

```
        ┌───────────┐    instruction     ┌──────────┐   adversarial    ┌──────────┐
 task → │ SuiteAdapter│ ───────────────→ │  Attack  │ ───instruction─→ │ Policy   │
        │  reset/step │                   │ perturb()│                  │  Adapter │
        │  is_unsafe()│ ←─── action ──────┴──────────┘                  │  act()   │
        └─────┬───────┘                                                 └────┬─────┘
              │  for t in horizon: if is_unsafe(state) → success              │
              └──────────────────────── runner ─────────────────────────────┘
                                          │
                                          ▼
                               scoring (ASR) → RunReport → report.json / report.md
```

- **`PolicyAdapter`** — `load()`, `act(observation, instruction) -> np.ndarray`.
- **`SuiteAdapter`** — `tasks()`, `reset(task, seed)`, `step(action)`, `is_unsafe(state)`.
- **`Attack`** — `perturb(instruction, observation) -> (instruction, observation)`.
- **`runner`** — runs every `(task, attack, seed)` episode and aggregates.
- **ASR** — `successes / attempts`, with `by_attack` and `by_task` breakdowns.

**Why the stub ASR is a real number.** The `StubPolicy` is intentionally manipulable:
it sums the weights of hard-coded "unsafe-intent" tokens in the instruction and emits a
proportionally aggressive action. The `StubSuite` declares an episode unsafe when that
action crosses a per-seed threshold derived from a stable SHA-256 hash. The benign base
instruction has no triggers (so an unattacked run scores 0); each shipped attack injects
triggers at a calibrated potency, so the resulting ASR is exact and reproducible. For
`seed=0`, the ASR is **70.0% (21/30)** — and the test suite asserts that exact value.

**Determinism.** A `RunReport` embeds no wall-clock time or process-varying values, so
the same config + seed always produces a byte-identical `report.json`.

## Development

```bash
uv run ruff check .      # lint
uv run mypy src          # type-check (strict)
uv run pytest -q         # tests (CPU only; LeRobot tests skip unless gated)
```

CI (GitHub Actions) runs exactly these three on Python 3.12 and **never installs
lerobot**.

## Further reading

- **[SAFETY.md](SAFETY.md)** — responsible use, sim-only default, scope.
- **[PRIOR_ART.md](PRIOR_ART.md)** — RoboPAIR, POEX, BadVLA, SafeVLA, and how we differ.
- **[CHANGELOG.md](CHANGELOG.md)** — what shipped and what's planned for v0.2.

## License

[Apache-2.0](LICENSE).
