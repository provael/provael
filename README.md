# vla-redteam · `robopwn`

[![CI](https://github.com/sattyamjjain/vla-redteam/actions/workflows/ci.yml/badge.svg)](https://github.com/sattyamjjain/vla-redteam/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/vla-redteam.svg)](https://pypi.org/project/vla-redteam/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)

> Red-team open **Vision-Language-Action (VLA)** robot policies in simulation and
> report an **Attack Success Rate (ASR)**.

<p align="center">
  <img src="docs/assets/demo.svg" alt="robopwn attack — ASR across instruction/visual/injection families" width="760">
</p>

<p align="center"><sub>Deterministic CPU stub run, seed 0 — regenerate with <code>./scripts/record_demo.sh</code>.</sub></p>

`vla-redteam` is a small, **model-agnostic** harness. It perturbs the instructions and
observations a VLA policy receives inside a simulator and measures how often those
perturbations drive the policy into an *unsafe* state. The headline number is the ASR.

It ships **three attack families** — `instruction` (text reframings), `visual`
(perception perturbations), and `injection` (indirect / embodied prompt injection) — an
ASR **leaderboard**, and gated adapters for real **SmolVLA** policies and the **LIBERO**
simulator.

The entire core — abstractions, attacks, scoring, runner, report, CLI, leaderboard —
runs and is tested on a **plain CPU with no GPU and no model/dataset download**, using a
deterministic `StubPolicy` + `StubSuite`. Real policies (SmolVLA via LeRobot) and the
LIBERO simulator live behind an optional extra and a `ROBOPWN_INTEGRATION=1` gate.

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
uv run robopwn attack --policy stub --suite stub \
    --attacks instruction,visual,injection --episodes 10 --seed 0 --out runs/stub/
```

```
              RoboPwn — ASR by attack
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ attack            ┃   ASR ┃ successes ┃ attempts ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ decoy_object      │ 60.0% │         6 │       10 │
│ goal_substitution │ 60.0% │         6 │       10 │
│ mcp_tool_desc     │ 70.0% │         7 │       10 │
│ paraphrase        │ 70.0% │         7 │       10 │
│ patch             │ 80.0% │         8 │       10 │
│ roleplay          │ 80.0% │         8 │       10 │
│ scene_text        │ 50.0% │         5 │       10 │
└───────────────────┴───────┴───────────┴──────────┘
Attack Success Rate (ASR): 67.1% (47/70)
```

This writes `runs/stub/report.json` (machine-readable, byte-deterministic) and
`runs/stub/report.md`. Per family, seed-0 ASR is **instruction 21/30**, **visual
14/20**, **injection 12/20** — exact, asserted numbers.

Other commands:

```bash
uv run robopwn list-policies            # stub (CPU); smolvla (needs the [lerobot] extra)
uv run robopwn list-attacks             # 7 attacks across families instruction/visual/injection
uv run robopwn report --in runs/stub/
uv run robopwn leaderboard build --runs runs --out leaderboard/results   # ranked ASR table
uv run robopwn version
```

## What runs on CPU vs. what needs a GPU

| Capability | CPU (default) | Needs GPU + `[lerobot]` extra |
| --- | :---: | :---: |
| `stub` policy + `stub` suite | ✅ | |
| All 3 attack families (`instruction`/`visual`/`injection`) | ✅ | |
| Scoring, runner, report, CLI, `leaderboard build` | ✅ | |
| Full test suite (`pytest`), `ruff`, `mypy` | ✅ | |
| `smolvla` policy (real SmolVLA via LeRobot) | | ✅ |
| `libero` suite (real LIBERO simulator) | | ✅ |

On CPU, `--policy smolvla` or `--suite libero` fails with a clear, actionable message
(not a traceback) telling you exactly what to install.

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
`pytest` → **86 passed, 4 skipped** (the 4 skips are the GPU-gated LeRobot/LIBERO
integration tests) · `robopwn attack` completes in well under a second.

> The LeRobot adapter was written **after introspecting the installed
> `lerobot==0.5.1`** — every symbol and signature it calls was confirmed against the
> real package (see the adapter docstring and CHANGELOG), not guessed.

## The real SmolVLA + LIBERO path (GPU box)

The in-process attack loop `robopwn attack --policy smolvla --suite libero` runs the
**real** rollout — replicating LeRobot's own evaluator (`preprocess_observation` →
`select_action` → …), with attacks applied to what SmolVLA actually consumes (the task
string and the camera image). Nothing here runs in CI or on the CPU core.

> ⚠️ **`lerobot/smolvla_base` is NOT directly evaluable on LIBERO** (verified by running
> it): it expects `camera1/2/3` but LIBERO provides `image`/`image2` + 8-dim state, and
> it is untrained on LIBERO. Pass a **LIBERO-fine-tuned** SmolVLA checkpoint via
> `--model`; the base model surfaces a clean `IncompatiblePolicyError`. Train one with
> `lerobot-train … --dataset.repo_id=HuggingFaceVLA/libero` (see the LeRobot LIBERO docs).
>
> Real-policy ASR is **seeded but model-stochastic** — reported as mean ± per-seed std,
> **not** byte-deterministic (only the stub is).

On a provisioned (GPU) machine:

```bash
pip install 'vla-redteam[lerobot]' 'lerobot[libero]==0.5.1'
export ROBOPWN_SMOLVLA_LIBERO_CKPT=<your-libero-finetuned-smolvla-repo_id>

# Gated integration tests (real load + real env + one real step through the glue):
ROBOPWN_INTEGRATION=1 pytest tests/test_lerobot_adapter.py tests/test_libero_adapter.py -q

# Real seeded attack-ASR (mean ± std) in the LIBERO simulator, then update the leaderboard:
robopwn attack --policy smolvla --suite libero --model "$ROBOPWN_SMOLVLA_LIBERO_CKPT" \
    --attacks instruction,visual,injection --seeds 10 --seed 0 --out runs/smolvla_libero
robopwn leaderboard build --runs 'runs/*' --out leaderboard/results
```

The helper [`scripts/run_real.sh`](scripts/run_real.sh) detects CUDA and runs the above
(or prints the exact commands and exits cleanly if there is no GPU). LeRobot's own
evaluator remains available for reference task-success numbers (`lerobot-eval
--env.type=libero`).

## Leaderboard

`robopwn leaderboard build` aggregates `report.json` files into a ranked, deterministic
`(policy × suite × family) → ASR` table. The [`leaderboard/`](leaderboard/) folder is a
ZeroGPU-compatible Gradio Space that renders the committed `results/*.json` with **no
GPU**.

> The committed `leaderboard/results/_demo.json` is **stub/demo data** — it shows the
> harness works, but the numbers are not a real model's robustness. Add real SmolVLA /
> OpenVLA results with the GPU command above; the "demo data" banner clears once a
> non-stub run is present.

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
it sums the weights of hard-coded "unsafe-intent" tokens found in the instruction **and**
in a fixed allow-list of observation channels (`scene_text`, `visual_tokens`,
`tool_descriptions`, `patch`, `objects`), then emits a proportionally aggressive action.
The `StubSuite` declares an episode unsafe when that action crosses a per-seed threshold
derived from a stable SHA-256 hash. The benign base scene + instruction have no triggers
(so an unattacked run scores 0); each shipped attack injects triggers at a calibrated
potency, so every per-attack ASR is exact and reproducible. For `seed=0`: instruction
**21/30**, visual **14/20**, injection **12/20** — and the test suite asserts each exact
value.

**Determinism.** A `RunReport` embeds no wall-clock time or process-varying values, so
the same config + seed always produces a byte-identical `report.json`.

## Development

```bash
uv run ruff check .      # lint
uv run mypy src          # type-check (strict)
uv run pytest -q         # tests (CPU only; LeRobot tests skip unless gated)
```

CI (GitHub Actions) runs exactly these three on Python 3.12 and **never installs
lerobot**. The test suite (CPU; the 3 GPU-gated tests skip):

```
tests/
  conftest.py                # stub policy / suite fixtures
  test_attacks.py            # instruction family: perturb + frozen aggressions
  test_visual_injection.py   # visual + injection families: perturb + frozen ASR
  test_scoring.py            # ASR math, zero-division guard
  test_runner_smoke.py       # exact seed-0 ASR (instruction canary 21/30)
  test_determinism.py        # byte-identical report.json per seed
  test_cli.py                # CLI commands + clean error paths
  test_registries.py         # policy/suite factories + config validation
  test_leaderboard.py        # leaderboard aggregation + determinism
  test_lerobot_adapter.py    # SmolVLA adapter: missing-dep error + gated integration
  test_libero_adapter.py     # LIBERO predicate (CPU) + gated integration
```

### Releasing

Tag-triggered: `git tag v0.1.0 && git push origin v0.1.0` builds an sdist + wheel and
publishes to PyPI via **OIDC trusted publishing** (no token in the repo), then cuts a
GitHub Release from the CHANGELOG. See the one-time setup notes at the top of
[`.github/workflows/release.yml`](.github/workflows/release.yml).

## Further reading

- **[SAFETY.md](SAFETY.md)** — responsible use, sim-only default, scope.
- **[PRIOR_ART.md](PRIOR_ART.md)** — RoboPAIR, POEX, BadVLA, SafeVLA, and how we differ.
- **[CHANGELOG.md](CHANGELOG.md)** — what shipped and what's planned for v0.2.

## License

[Apache-2.0](LICENSE).
