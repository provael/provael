# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-03

First public cut — **Part 1**. A model-agnostic harness that red-teams VLA policies in
simulation and reports an Attack Success Rate (ASR). The entire core runs and is tested
on a plain CPU with no GPU and no model/dataset download.

### Added
- **Core engine**: `PolicyAdapter`, `SuiteAdapter` (with an `is_unsafe` predicate), and
  `Attack` abstractions; a deterministic `runner` (policy × suite × attacks × seeds);
  pydantic v2 result types (`AttackResult`, `RunReport`).
- **Deterministic CPU stubs**: `StubPolicy` (manipulable via a documented trigger-token
  lexicon) and `StubSuite` (one-task env with a SHA-256, cross-platform per-seed unsafe
  threshold), so ASR is a real, exact, reproducible number with no model.
- **`instruction` attack family** (templated, auditable): `RolePlayAttack`,
  `GoalSubstitutionAttack`, `ParaphraseAttack` — inspired by RoboPAIR and POEX
  (see [PRIOR_ART.md](PRIOR_ART.md)).
- **Scoring**: ASR with per-attack and per-task breakdowns, guarded against zero
  attempts.
- **Reports**: stable `report.json` (sorted keys, no wall-clock → byte-deterministic)
  and `report.md`, plus a Rich console summary and the headline ASR line.
- **`robopwn` CLI**: `attack`, `list-policies`, `list-attacks`, `report`, `version`.
  Clean, actionable errors (exit code 2) for a missing `[lerobot]` extra or an unknown
  policy/suite/attack — never a traceback.
- **Verified LeRobot adapter (gated)**: loads `lerobot/smolvla_base` via
  `SmolVLAPolicy.from_pretrained` + `make_pre_post_processors` + `build_inference_frame`
  + `select_action`, written **after introspecting** the installed `lerobot==0.5.1`
  (symbols and signatures confirmed, not guessed). Kept entirely out of the default
  install behind the optional `[lerobot]` extra and an `ROBOPWN_INTEGRATION=1` gate.
- **Docs & CI**: README (with a real "Verified environment" block), SAFETY.md,
  PRIOR_ART.md, and a GitHub Actions workflow running ruff + mypy + pytest on Python
  3.12, CPU-only, never installing lerobot.

### Known limitations
- Only the `instruction` attack family ships. The `StubPolicy`/`StubSuite` are
  deliberate test fixtures, not models of real VLA behaviour.
- The LeRobot adapter's `act()` is verified at the symbol/signature level but not
  executed in CI (it is GPU-gated). The full simulator obs→features wiring is Part 2.

## [Unreleased] — planned for 0.2

- **Optimized-suffix attack family** (GCG-style / POEX-style executable suffixes).
- **Visual** and **observation-injection** attack families.
- **Full LIBERO `SuiteAdapter`** (today the documented path is `lerobot-eval
  --env.type=libero`).
- A **Hugging Face ZeroGPU leaderboard** of ASR across open VLA policies.

[0.1.0]: https://github.com/vla-redteam/vla-redteam/releases/tag/v0.1.0
