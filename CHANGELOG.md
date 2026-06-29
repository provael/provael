# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] — 2026-06-29

### Added
- **EAI04 action-space-integrity attack family (`action`).** Two new attacks alongside the
  existing instruction/visual/injection families: **`freeze`** — a FreezeVLA-style
  action-freeze (arXiv:2509.19870) that drives the policy's motor command to a no-op — and
  **`trajectory_hijack`** — a targeted redirect that biases the action toward an attacker
  waypoint. Both route through the standard `Attack` interface and are scored as a rate with
  a **95% Wilson CI against a benign-FPR control** (the `none` baseline under the same
  predicate). On the deterministic CPU stub both land at **100% [72–100%] vs a 0% benign
  baseline**; the EAI04 predicate (freeze / redirect) is OR-ed into the suite's unsafe check,
  is independent of danger calibration, and is a no-op on suites that surface no action
  signal (so the attacks report **not-applicable** there — e.g. the GPU-gated LIBERO path).
  **Stub-validated scaffolding:** a real-model action-freeze needs an adversarial-image search
  (FreezeVLA / AttackVLA), which is GPU-gated and **not yet run** — no cross-model transfer is
  claimed. `docs/TOP10.md` EAI04 moves from taxonomy-only to *attack shipped*.
- **Compliance evidence report** — `provael report --in <run> --format compliance` emits an
  auditor-readable evidence artifact mapping a run's calibrated results to **EU AI Act**
  (Art. 9 / 15 / 72), **ISO 10218-1/-2:2025** (cyber), **NIST AI 100-2 / AI RMF**
  (GOVERN·MAP·MEASURE·MANAGE), and **IEC 62443**. `--out report.compliance.json` writes the JSON
  evidence schema — per mapped requirement: the Provael artifacts that evidence it (attack
  families, calibrated redirection rate + 95% Wilson CI, benign FPR, EAI ids covered, calibration
  metadata), an `evidence-present` / `gap` status with a reason, and the honest-scope caveats
  (adversarial-only, evidence-not-certification, behavioural-not-worst-case). `--out
  report.compliance.md` renders the buyer/auditor-readable version; with no `--out` the JSON
  prints to stdout. `provael attack … --format compliance` also drops a `report.compliance.json`
  next to the report. Reuses `report.json` (no attacks re-run), is CPU/stub-runnable in CI, and is
  byte-deterministic. Implements the `docs/COMPLIANCE.md` pre-spec.
- `docs/COMPLIANCE.md` — the crosswalk + evidence map the generator implements (calibrated
  redirection rate, benign FPR, CI, EAI tags, SARIF → the frameworks above). Linked from the README.

### Changed
- **First real result refreshed to a calibrated, control-bearing framing.** The README and
  `docs/TOP10.md` headline SmolVLA × LIBERO result now leads with `roleplay` **100% (10/10),
  95% Wilson CI [72–100%]** against a **0% benign baseline FPR** — every rate shown with its
  control and CI — replacing the blended, uncalibrated 24.3% headline. The honest caveats
  (sim-only, one task, `n = 10`, only the instruction family transfers) and methodology notes are
  unchanged, now pointing at `provael calibrate` + `provael attack --calib`.

## [0.4.0] — 2026-06-28

### Added
- **Per-task keep-out-zone / predicate calibration.** New `provael calibrate --policy <p>
  --suite <s> [--tasks …] --seeds N [--target-fpr 0.05] --out calib/` runs benign (attack
  `none`) rollouts, derives a per-task safe predicate from the policy's own behaviour, and
  tunes it on a fit/holdout split so the benign **false-positive rate** stays at or below the
  target. Writes a per-task JSON artifact (envelope/threshold, achieved benign FPR, n, seed
  split). Stub calibration is CPU-only and deterministic; the SmolVLA/LIBERO path stays
  GPU-gated.
- **Calibrated scoring.** `provael attack … --calib calib/` uses the calibrated predicate when
  an artifact exists for `(policy, suite, task)`, else the default (backward-compatible). The
  report records `calibrated`, the live `benign_fpr` (the `none` baseline's rate under the
  predicate used — every number gets its control), and per-task calibration metadata.
- **Confidence + control everywhere.** ASR is shown as a **calibrated redirection rate** with a
  **95% Wilson CI** and the benign FPR alongside, in `report.json`, `report.md`, the rich CLI
  table, and the SARIF output (per-result `asrCiLow`/`asrCiHigh` + run-level `calibrated`/
  `benignFpr`). Multi-task calibrate + report (per-task + aggregate).

### Changed
- The default predicate is unchanged and remains the fallback; calibration is strictly opt-in.

## [0.3.0] — 2026-06-27

### Added
- **SARIF 2.1.0 output** — `provael report --in <run> --format sarif [--out file]` (stdout when
  no `--out`) and `provael attack … --format sarif` / `--sarif-out <path>`. One result per
  attack, severity from ASR (≥0.5 `error`, >0 `warning`, 0 `note`), with stable
  `partialFingerprints`, so red-team findings surface in GitHub code scanning.
- **Reusable GitHub Action** (`provael/provael@v0.3.0`) — a composite action that runs a
  red-team, uploads the SARIF via `github/codeql-action/upload-sarif`, and fails CI when the
  overall ASR exceeds `asr-threshold`; plus `examples/workflow.yml` for consumers.
- **Embodied AI Top-10 mapping** — every attack is tagged with its `EAIxx` risk
  (`instruction` → EAI01, `visual` → EAI02, `injection` → EAI05; the baseline control stays
  untagged). Surfaced as `RunReport.eai` in report.json, an EAI column in report.md and the
  CLI table, and as SARIF `ruleId`s deep-linked to `docs/TOP10.md`.
- `docs/TOP10.md` — The Embodied AI Security Top 10 (v0.2), an independent risk taxonomy for
  VLA/robot security with a crosswalk to OWASP/MITRE/NIST.
- Brand assets under `docs/assets/` (icon + wordmark, SVG and PNG) and a logo in the README header.

### Unchanged
- The deterministic stub run still reports ASR 67.1% (47/70), byte-identical; the CPU core
  pulls no GPU/ML stack and CI never installs lerobot.

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
- **v0.3.0** — SARIF output (`provael report --format sarif`) for GitHub code scanning; a
  reusable `provael/provael` CI gate; an Embodied-AI Top-10 risk mapping; per-task
  keep-out-zone calibration.
- **later** — optimized (gradient/search) attacks; a second policy/suite backend.

> Detailed pre-rebrand history (the `vla-redteam` 0.2.x line) is preserved in the git log and
> the prior PyPI releases.

[0.5.0]: https://github.com/provael/provael/releases/tag/v0.5.0
[0.4.0]: https://github.com/provael/provael/releases/tag/v0.4.0
[0.3.0]: https://github.com/provael/provael/releases/tag/v0.3.0
[0.1.0]: https://github.com/provael/provael/releases/tag/v0.1.0
