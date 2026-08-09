# SmolVLA × LIBERO-Object — full 10-task suite screen

**350 measured episodes (400 records) · 10 tasks · 8 arms · 5 seeds · 9 August 2026 · provael 0.32.0**

The first result in this project measured on **more than one task**. Everything published
before it measured `libero_object/0` alone, which is why
`cluster_bootstrap_ci` returned `None` for all of them — it refuses below two tasks by design.

## Result

| arm | pooled | McNemar | Holm | task-clustered 95% CI | verdict |
| --- | ---: | ---: | ---: | --- | --- |
| `roleplay` | **44/50 (88%)** | p=4.6e-13 | 2.7e-12 | **[72%, 100%]** | **survives** |
| `goal_substitution` | **15/50 (30%)** | p=9.8e-4 | 4.9e-3 | [6%, 54%] | **survives** |
| `paraphrase` | 3/50 (6%) | p=1.0 | 1.0 | [0%, 12%] | rejected |
| `patch` | 0/50 (0%) | p=0.5 | 1.0 | [0%, 0%] | rejected |
| `decoy_object` | 0/50 (0%) | p=0.5 | 1.0 | [0%, 0%] | rejected |
| `scene_text` | 0/50 (0%) | p=0.5 | 1.0 | [0%, 0%] | rejected |
| `mcp_tool_desc` | **0 attempts** | — | — | — | **not applicable to this suite** |

Benign control: **2/50 (4%)** pooled false-positive rate.
Clean-task-success: **84%** mean, range 40%–100% across tasks.

## What the artifacts are

`libero_object_<n>/report.json` — one per task, ten in total. Each is the report provael wrote
for that shard, **with `decisions[]` removed**: the per-step action traces are 1.9 MB per task
and 19 MB is not a reasonable thing to put in a git history. Every field the statistics consume —
`task`, `attack`, `seed`, `success`, `task_success`, `applicable`, `steps` — is retained, and
re-running `paired.py` over these files reproduces `aggregate.json` exactly. The untrimmed
artifacts are on the Modal Volume `provael-libero-runs`.

`aggregate.json` — the cross-shard analysis. It is deliberately **not** shaped like a
`report.json`: each shard's report is the attestable artifact whose digest is a pure function of
its own config, and stitching ten into an eleventh would produce a file that looks signable and
is not.

## Four things that qualify this result

**The predicate is uncalibrated.** `"calibrated": false` on every shard — the same default
keep-out box on all ten tasks, never fitted to any of them. It shows: the benign arm tripped it on
tasks 4 and 5 (20% each). McNemar handles that correctly by discarding concordant pairs, and
`benign_only` counts are reported per arm rather than hidden, but a calibrated predicate would
be a better measurement. `provael calibrate` exists and has never been run on LIBERO.

**It is not reproducible run-to-run.** `"stochastic": true`. SmolVLA's flow-matching sampler is
not fully seeded, so provael's determinism contract covers the stub path and not this one. An
earlier pilot at identical config gave `goal_substitution` 1/4 on one run and 0/4 on the next.
Treat every number here as one draw.

**`mcp_tool_desc` was never applicable.** It has 50 episode records like every other arm, but they
carry `applicable: false` and `steps: 0`, and scoring excludes them from `attempts` — hence 0
attempts rather than 0%. It is listed above as *not measured* rather than as a null, because those
are different claims and the table would otherwise imply seven measured nulls when there are six.
This is also why the run is **350 measured episodes out of 400 records**: quoting 400 as the
measured n would overstate it by 14%.

**One suite, one checkpoint.** `libero_object` only, `HuggingFaceVLA/smolvla_libero` only. Nothing
here speaks to `libero_spatial`, `libero_goal`, `libero_10`, or any other policy.

## Reproducing it

```bash
PROVAEL_STAGE=full modal run examples/gpu-ci/modal_libero_suite.py
```

Ten containers, one per task, ~2 h wall clock, 15.4 GPU-hours, ~$12 on an L4. Sharding is a
survivability decision: `provael attack` cannot resume, so a single container that dies late loses
everything, while ten lose one task.
