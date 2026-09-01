# AI2 `vla-evaluation-harness` bridge — interface notes

> Status: **NOTES ONLY.** No benchmark has been run through this bridge. Nothing here is a
> measurement, and `src/provael/suites/ai2_bridge.py` is registered scaffolding, not a working
> suite. Read at v0.5.0 (`4aeb436`); the roadmap's "~18 benchmarks" is a v0.4.0 figure.

## What was read

[`allenai/vla-evaluation-harness`](https://github.com/allenai/vla-evaluation-harness), Apache-2.0.
Claims verified by reading the source at the tags named, not from the README.

| Fact | Value | Where |
| --- | --- | --- |
| PyPI distribution | **`vla-eval`**, not `vla-evaluation-harness` (that name 404s) | PyPI; import is `vla_eval` |
| Benchmarks at **v0.4.0** | **18** | `git ls-tree -d v0.4.0 src/vla_eval/benchmarks/` |
| Benchmarks at v0.5.0 | 20 (adds `robocasa365`, `robodojo`) | same, at HEAD |
| `predict` signature | `predict(self, obs: Observation, ctx: SessionContext) -> Action` | `model_servers/predict.py:176` |

The v0.4.0 set: `behavior1k calvin duobench kinetix libero libero_mem libero_plus libero_pro
maniskill2 mikasa molmospaces rlbench robocasa robocerebra robomme robotwin simpler vlabench`.

## Concept mapping

| Provael (`suites/base.py`) | AI2 harness | Fit |
| --- | --- | --- |
| `tasks() -> list[str]` | `Benchmark.get_tasks() -> list[Task]`; `Task` is an open dict, conventionally `{"name", "suite"}` | clean — flatten to a string key |
| `reset(task, seed) -> Observation` | `StepBenchmark.reset()` | **partial** — see seeding below |
| `step(action) -> (obs, done, state)` | `StepBenchmark.step()` + `check_done()` + `get_step_result()` | obs and done map; **`state` does not** |
| `is_unsafe(state) -> bool` | *nothing* | **no equivalent, and no input for one** |
| `calibration_signal(state)` | *nothing* | blocked by the same gap |

`predict()` is a method you **implement** on a model server, not one you call. The harness runs the
policy as a separate process over WebSocket; `Orchestrator.run()` owns the loop via
`SyncEpisodeRunner.run_episode(...)`.

## Seeding: not per-episode from the caller

There is **no `seed=` argument on the runner API**. The seed is constructor-level, set in YAML
(`params.seed`), and the orchestrator only *warns* when it is omitted. Per-episode variation is
derived inside each benchmark from `task["episode_idx"]` — and inconsistently: `duobench` and
`robocasa365` do `seed + episode_idx`, while LIBERO pins `env.seed(self.env_seed)` and indexes a
fixed `initial_states` file instead.

Provael's contract is `reset(task, seed)` with the seed supplied per episode, and its determinism
tests assume a report is a pure function of that seed. The harness cannot honour that signature
directly; a bridge would have to express a Provael seed as an `episode_idx` and accept that what
"seed" means then differs per benchmark.

Worth carrying: the harness ships **no determinism or reproducibility tests** (24 test files, none
matching `determinis|reproduc`), and warns rather than fails on an unset seed. Matched-pair
rollouts need Provael's own verification, not the harness's assurance.

## The finding: `is_unsafe` has no state to evaluate

**Provael's keep-out predicate is not expressible against the harness's public surface.**

`get_step_result` for LIBERO returns exactly `{"success": step_result.done}`
(`benchmarks/libero/benchmark.py:287`). The only per-step channel is a SQLite recorder, and it is
field-filtered per benchmark: LIBERO's is
`_ALL_RECORD_FIELDS = frozenset({"reward", "done", "success"})` (`:92`).

The end-effector pose **exists** — `benchmarks/libero/benchmark.py:268` reads `robot0_eef_pos` — but
it is assembled inside `make_obs` and flows **outward to the model server**. It never returns to a
caller. So the harness will tell a bridge whether the task succeeded and nothing about where the arm
went, which is precisely the signal Provael scores on.

This is not a small gap. It means a bridge inherits ~18 benchmarks' *tasks* while losing the
predicate that makes a Provael run a safety measurement rather than a success-rate measurement.
Everything in `scoring/` that reads a spatial state — keep-out zones, `calibration_signal`, the EAI02
/ EAI04 / EAI06 predicates — is unreachable through the published API.

Three ways round it, none free:

1. **Subclass the benchmark and override `make_obs`.** `benchmark:` is an unrestricted import string
   (`resolve_import_string("module:Class")`, no allow-list), so a Provael subclass can live entirely
   outside `vla_eval` with no fork. It can capture the pose on the way past. Per-benchmark work —
   the multiplier is lost.
2. **Widen `_ALL_RECORD_FIELDS`** upstream so pose is recordable. Needs an upstream change.
3. **Model-server proxy.** A `PredictModelServer` that wraps the real policy sees
   `obs["images"]["agentview"]` and `obs["task_description"]`, with `ctx.step` / `ctx.is_first` /
   `ctx.episode_id` for scheduling. This is the natural home for **attacks** — it perturbs exactly
   what the policy sees — but it does not solve the predicate, because it is on the wrong side of
   the loop to observe env state.

The honest reading: the harness is a strong fit for delivering *perturbed inputs* and a poor fit for
*observing unsafe outcomes*. A bridge is therefore two pieces of work, not one, and only the first
is cheap.

## Benign control arm: yes, expressible

The most important question for this project, and the answer is positive. Work items are a
deterministic `task x episode` enumeration, so running the same benchmark class twice — same
`params.seed`, same `episodes_per_task`, once through a perturbing proxy and once not — visits the
same initial states. Two `vla-eval run` invocations, or two entries in one config's `benchmarks:`
list distinguished by `subname`.

Subject to the determinism caveat above: the harness does not test this, so the pairing must be
verified rather than assumed.

## Prior art already in the harness

`libero_pro` and `libero_plus` are **perturbation** benchmarks — systematic distribution shift along
swap / object / language / task / environment axes, ~10,030 variants in `libero_plus`. That is the
same family Provael's `attacks/controls.py` borrows its benign-variation framing from. They are
robustness benchmarks, not adversarial ones: the perturbations are fixed and published, not searched
against a policy. Useful as control arms; not a substitute for an attack.

## What is not known

The interface was read, never executed — running it needs Docker plus per-benchmark GPU simulator
dependencies. In particular it is unverified whether a perturbing proxy round-trips cleanly through
the msgpack/JPEG codec: `protocol/image_codec.py` does a JPEG round-trip for some servers
(`jpeg_roundtrip: true`), which could blunt small-magnitude pixel perturbations. For an L-inf
budgeted attack like `gradient_patch` that is not a detail — it could silently destroy the
perturbation being measured. Check before trusting any visual-family number through this path.
