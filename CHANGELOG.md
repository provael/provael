# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `docs/TOP10.md` — The Embodied AI Security Top 10 (v0.2), an independent risk taxonomy for VLA/robot
  security with a crosswalk to OWASP/MITRE/NIST.

## [0.1.0] — 2026-06-27

Initial **Provael** release. Provael is the open-source red-team & assurance layer for
physical AI — a CPU-first, model-agnostic harness that perturbs the instructions and
observations a Vision-Language-Action (VLA) robot policy receives in simulation and reports
an Attack Success Rate (ASR).

> **Renamed from `vla-redteam` / `robopwn`.** The same engine and full git history, under a
> new name, CLI (`provael`), and home (github.com/provael/provael). It was previously
> published on PyPI as `vla-redteam` (0.1.0–0.2.2); the env-var gate is now
> `PROVAEL_INTEGRATION`. Behavior is unchanged — the deterministic stub run still reports
> ASR 67.1% (47/70), byte-identical.

### Included
- **CPU-first deterministic core** — `StubPolicy` + `StubSuite` give exact, byte-reproducible
  ASRs with no GPU or model download; strict typing, `py.typed`, 100 tests.
- **Three templated attack families** (`instruction`, `visual`, `injection`) + a `none`
  baseline; ASR with per-attack / per-task breakdowns and seeded mean ± std for real policies.
- **Real SmolVLA × LIBERO path** behind the `[lerobot]` extra + `PROVAEL_INTEGRATION=1`,
  replicating LeRobot's verified evaluator rollout; first real result on `libero_object/0`
  (instruction attacks 60–100% vs a 0% benign baseline; visual/injection 0% — honest null).
- **Per-task calibrated keep-out zones** scaffold (`suites/keepout_zones.py` +
  `scripts/calibrate_zones.py`) toward a calibrated hazard rate.
- **Leaderboard** — deterministic `(policy × suite × family) → ASR` table, a Gradio Space, and
  a public submission flow (validator + CI on `results/**`).
- **CLI `provael`** — `attack`, `report`, `leaderboard build`, `list-policies`,
  `list-attacks`, `version`; actionable errors (exit code 2), never a traceback.
- Apache-2.0; OIDC trusted-publishing release pipeline; strict `ruff` + `mypy` gate in CI.

### Honest scope
Attacks are templated (not gradient/optimization-based); only the instruction family
transfers to real SmolVLA so far; one policy + one suite shipped; the headline result uses a
single task with a default, uncalibrated keep-out predicate. See the README's
"Scope and honest limitations."

### Roadmap
- **v0.2.0** — SARIF output (`provael report --format sarif`) for GitHub code scanning; a
  reusable `provael/provael-action` CI gate; an Embodied-AI Top-10 risk mapping; per-task
  keep-out-zone calibration.
- **later** — optimized (gradient/search) attacks; a second policy/suite backend.

> Detailed pre-rebrand history (the `vla-redteam` 0.2.x line) is preserved in the git log and
> the prior PyPI releases.

[0.1.0]: https://github.com/provael/provael/releases/tag/v0.1.0
