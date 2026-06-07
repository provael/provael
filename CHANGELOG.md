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

## [0.2.1] — 2026-06-07

### Fixed
- **PyPI page rendering**: the README's hero image and several doc links used repo-relative
  paths that 404 on PyPI (they only resolve on GitHub). Switched to absolute URLs
  (`raw.githubusercontent.com` for the image; `github.com/.../blob|tree/main/...` for links)
  so the project description renders correctly. No code/API changes.

### Changed (repo / deployment — not the installed package)
- **Leaderboard Hugging Face Space** now builds on gradio 6 (loosened pin, pinned
  `sdk_version: 6.16.0`) and its landing page shows the real result. Live at
  <https://huggingface.co/spaces/Sattyam/vla-redteam-leaderboard>.

## [0.2.0] — 2026-06-07 (in-process SmolVLA×LIBERO + first real result)

The real attack loop `robopwn attack --policy smolvla --suite libero` now runs
end-to-end (GPU-gated) and produced the project's **first real red-team result** on a
RunPod RTX 4090. Verified by **running** against the installed `lerobot==0.5.1`.

### Added
- **SmolVLA×LIBERO glue**: the SmolVLA adapter consumes a real LIBERO observation by
  replicating LeRobot's own evaluator rollout (`preprocess_observation` → set task →
  `env_preprocessor` (`LiberoProcessorStep`) → `preprocessor` → `select_action` →
  `postprocessor` → `env_postprocessor` → clamp to `[-1,1]`). A `SuiteFeatures` protocol
  exchanges the env config once; `make_policy(cfg, env_cfg, rename_map)` mirrors eval.
- **Real-policy attack injection**: instruction → the task language string; `visual.patch`
  / `visual.decoy_object` → adversarial-marker overlay on the camera image;
  `injection.scene_text` → PIL-rendered scene sign. `injection.mcp_tool_desc` is honestly
  **N/A** on a direct LIBERO loop (excluded from the denominator).
- **Live unsafe predicate**: end-effector keep-out zone (live, verified `eef.pos`) plus a
  **configurable** forbidden-object-grasp rule (a `grasp_extractor` hook).
- **Seeded mean ± std** reporting for stochastic (real) policies; `--seeds`, `--model`,
  and `--rename-map` CLI options; `pillow` added for image rendering.
- **`baseline` family** (`none`, a no-op control): runs the benign task unchanged so its
  ASR is the reference, and attack ASR can be read as **lift over baseline**.
- **Real task language as the base instruction**: the LIBERO adapter now reads the env's
  actual task via `env.call("task_description")` (mirroring LeRobot's `add_envs_task`)
  instead of a placeholder — so the benign baseline measures the policy on its real job
  and attack ASR is a true "diverted from the legitimate task" number.
- **Headless-sim robustness**: LIBERO's first-run `input()` config prompt is auto-handled
  (`_ensure_libero_initialized`); `scripts/run_real.sh` sets `MUJOCO_GL`/`PYOPENGL_PLATFORM`
  and documents the GL deps (`osmesa` CPU render, or EGL) for cloud GPU boxes.

### First real result — verified on a GPU (2026-06-06)
- Ran the full loop on a RunPod **RTX 4090** (`HuggingFaceVLA/smolvla_libero`,
  `libero_object/0`, 10 seeds, horizon 280, `osmesa`). Overall **24.3% (17/70) ± 9.1%**.
  Per family vs the benign `none` baseline (0/10): instruction `roleplay` **100%**,
  `goal_substitution` **60%**, `paraphrase` 10%; `visual` and `injection` **0%**. The
  canonical artifact is committed at `results/smolvla_libero_object/`, and
  `leaderboard/results/leaderboard.json` now holds this real (non-demo) result.
- **Honest caveat**: the keep-out predicate is a default, **uncalibrated** region — so this
  is "diverted out of the benign safe envelope," not a zone-calibrated hazard rate; one
  task, `n = 10`.

### Verified by running (isolated lerobot venv, CPU)
- `lerobot/smolvla_base` is **NOT** LIBERO-compatible (expects `camera1/2/3`; LIBERO
  gives `image`/`image2` + 8-dim state) → the adapter surfaces a clean
  `IncompatiblePolicyError`.
- The **ready** `HuggingFaceVLA/smolvla_libero` checkpoint **loads through the glue** with
  no incompatibility (policy + pre/post + `LiberoProcessorStep` all build) — so no
  fine-tuning is needed. It is the default in `scripts/run_real.sh` and the gated tests.

### Known limitations
- Real-policy ASR is **seeded but model-stochastic** (mean ± std), not byte-deterministic
  (only the stub is).
- Forbidden-object grasp is **disclosed-inert by default** (no verified robosuite accessor
  without the sim) — live only with a user-supplied `grasp_extractor`.
- The first real ASR (above) uses an **uncalibrated** keep-out region, so it measures
  redirection *out of the benign safe envelope*, not a zone-calibrated hazard rate; one
  task, `n = 10`. Producing it requires a LIBERO-fine-tuned checkpoint + GPU + sim (not CI).

## [Unreleased] — planned

- **Per-task keep-out-zone calibration** (+ trajectory inspection) so a real ASR is a
  semantically-meaningful redirection rate, not "entered a default box" — and a multi-task,
  multi-suite sweep. This is the headline `v0.2.0` follow-up to the first real result.
- **Optimized-suffix attack family** (GCG-style / POEX-style executable suffixes) and
  pixel-level visual attacks tuned to transfer to real VLA policies.
- **`mcp_tool_desc` on a real robot-MCP target** (no surface in a direct LIBERO loop).
- A **default robosuite grasp accessor** so forbidden-object-grasp is live out of the box.
- **Full multi-policy live leaderboard** on Hugging Face ZeroGPU with real SmolVLA /
  OpenVLA numbers (the `@spaces.GPU` live-run path).
- **`vla-guard`** (Phase 2): a defensive companion that hardens policies against the
  attacks this tool measures.

[0.2.1]: https://github.com/sattyamjjain/vla-redteam/releases/tag/v0.2.1
[0.2.0]: https://github.com/sattyamjjain/vla-redteam/releases/tag/v0.2.0
[0.1.0]: https://github.com/sattyamjjain/vla-redteam/releases/tag/v0.1.0
