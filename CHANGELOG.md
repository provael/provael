# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-03

First public release. A model-agnostic harness that red-teams VLA policies in
simulation and reports an Attack Success Rate (ASR). The entire core runs and is tested
on a plain CPU with no GPU and no model/dataset download; real policies and the LIBERO
simulator are isolated behind the optional `[lerobot]` extra and an
`ROBOPWN_INTEGRATION=1` gate, and CI never installs them.

### Added
- **Core engine**: `PolicyAdapter`, `SuiteAdapter` (with an `is_unsafe` predicate), and
  `Attack` abstractions; a deterministic `runner` (policy × suite × attacks × seeds);
  pydantic v2 result types (`AttackResult`, `RunReport`).
- **Deterministic CPU stubs**: `StubPolicy` (manipulable via a documented trigger-token
  lexicon over the instruction *and* a fixed allow-list of observation channels) and
  `StubSuite` (one-task env with a SHA-256, cross-platform per-seed unsafe threshold),
  so every attack yields a real, exact, reproducible seed-0 ASR with no model.
- **Three attack families** (templated, auditable, CPU-testable):
  - `instruction` — `RolePlayAttack`, `GoalSubstitutionAttack`, `ParaphraseAttack`
    (RoboPAIR / POEX-inspired). Seed-0 ASR **21/30**.
  - `visual` — `PatchAttack`, `DecoyObjectAttack` (observation-space markers; BadVLA
    -inspired). Seed-0 ASR **14/20**.
  - `injection` — `SceneTextInjection`, `MCPToolDescInjection` (indirect / embodied
    prompt injection; POEX-inspired). Seed-0 ASR **12/20**.
  - Combined seed-0 ASR across all three: **47/70**. See [PRIOR_ART.md](PRIOR_ART.md).
- **Scoring & reports**: ASR with per-attack and per-task breakdowns (zero-division
  guarded); stable `report.json` (sorted keys, no wall-clock → byte-deterministic) and
  `report.md`, plus a Rich console summary.
- **`robopwn` CLI**: `attack`, `list-policies`, `list-attacks`, `report`, `version`, and
  `leaderboard build`. Clean, actionable errors (exit code 2) for a missing `[lerobot]`
  extra or an unknown policy/suite/attack — never a traceback.
- **Verified LeRobot SmolVLA adapter (gated)**: loads `lerobot/smolvla_base` via
  `SmolVLAPolicy.from_pretrained` + `make_pre_post_processors` + `build_inference_frame`
  + `select_action`, written **after introspecting** the installed `lerobot==0.5.1`
  (symbols and signatures confirmed, not guessed).
- **Verified LIBERO `SuiteAdapter` (gated)**: wraps the real LeRobot LIBERO env via the
  introspected `make_env` / `make_env_config` / `LiberoEnv` API (`{suite: {task_id:
  VectorEnv}}`, action dim 7, `info["final_info"]["is_success"]`). Configurable embodied
  red-team predicate (`LiberoRedTeamRules`): default end-effector keep-out zone, optional
  forbidden-object grasp. LIBERO is benign manipulation — we measure *redirection*, not
  harm (see [SAFETY.md](SAFETY.md)).
- **ASR leaderboard (v0, static-data)**: `robopwn leaderboard build` aggregates
  `report.json` files into a ranked `(policy × suite × family) → ASR` table
  (deterministic). A Gradio Space (`leaderboard/`, ZeroGPU-compatible) renders the
  committed `results/*.json` with no GPU; data is clearly labelled stub/demo until real
  SmolVLA / OpenVLA runs are added.
- **Release engineering**: tag-triggered PyPI publish via OIDC trusted publishing
  (`.github/workflows/release.yml`) and a GitHub Release from the CHANGELOG.
- **Docs & CI**: README (with a real "Verified environment" block), SAFETY.md,
  PRIOR_ART.md, and a GitHub Actions workflow running ruff + mypy + pytest on Python
  3.12, CPU-only, never installing lerobot.

### Known limitations
- The `StubPolicy` / `StubSuite` are deliberate test fixtures, not models of real VLA
  behaviour. The visual/injection attacks target the stub's observation channels; against
  a real policy they only transfer insofar as the policy reads the perturbed channel
  (pixel-level visual attacks on real models are future work).
- The LeRobot SmolVLA adapter and the LIBERO `SuiteAdapter` are verified at the
  symbol/signature level but not executed in CI (GPU-gated). The full LIBERO
  observation→features wiring and the robosuite grasped-object accessor are deferred.
- The leaderboard ships demo (stub) data only until real-model runs are added.

## [Unreleased] — planned

- **Optimized-suffix attack family** (GCG-style / POEX-style executable suffixes) and
  pixel-level visual attacks that transfer to real VLA policies.
- **Full multi-policy live leaderboard** on Hugging Face ZeroGPU with real SmolVLA /
  OpenVLA numbers (the `@spaces.GPU` live-run path).
- **Full LIBERO integration**: observation→features wiring so `--policy smolvla --suite
  libero` runs end-to-end in-process, plus the robosuite grasped-object predicate.
- **`vla-guard`** (Phase 2): a defensive companion that hardens policies against the
  attacks this tool measures.

[0.1.0]: https://github.com/sattyamjjain/vla-redteam/releases/tag/v0.1.0
