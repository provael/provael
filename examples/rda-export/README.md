# Per-episode action export for RDA

`rda_export.py` writes the per-step actions of committed LIBERO runs as plain JSON, one file per
run, with every episode keyed by task, seed and arm. It was written for the question raised on
[Lifelong-Robot-Learning/LIBERO#148](https://github.com/Lifelong-Robot-Learning/LIBERO/issues/148):
do the action-level flags of [RDA](https://github.com/liesliy/rda) separate the episodes that left
the keep-out envelope from their benign pairs?

It runs offline on a CPU with only `provael` installed:

```bash
python examples/rda-export/rda_export.py
```

With no arguments it reads two runs and writes `runs/rda-export/<run>.rda.json` for each:

- [`results/smolvla_libero_object_suite_2026-09-14`](../../results/smolvla_libero_object_suite_2026-09-14/),
  the run with envelope exits.
- [`results/smolvla_libero_10_2026-09-14`](../../results/smolvla_libero_10_2026-09-14/), the
  negative control. No episode in it left the envelope.

Name other run directories to export those instead, and pass `--out` to write somewhere else. For
each run the script prints how many episodes and per-step actions it wrote, what it left out, and
what the pairs are matched on.

## Pairs are matched on task and seed only

The benign pair of an attacked episode is the `none` episode at the same task and seed. Both
default runs are report schema 5 and record no `init_state`, and under lerobot 0.5.1's reset
counter the arms at one seed start from different fixed initial states. A pair therefore shares a
task and a seed, not a starting scene ([E-2026-19](../../docs/errata.md)). Each file says so in its
`pairing` block, so the caveat stays with the data. The sentence comes from
`provael.scoring.paired.pairs_share_init_state`: a run whose every pair recorded one equal
`init_state` gets "matched on task, seed and init state" instead.

## What a file holds

One JSON object. The metadata comes first and the episodes last, one per line.

| Key | What it holds |
| --- | --- |
| `source` | The run, and each shard's path, SHA-256, report schema and tool version. |
| `pairing` | The pairing key, the number of pairs, and what they are matched on. |
| `exit_predicate` | The keep-out box behind `envelope_exit`, and what each `ended_by` value means. |
| `actions` | Where the action rows come from, and the names of the 7 channels. |
| `coverage` | Episodes in the shards, episodes and steps exported, and every excluded episode with its reason. |
| `not_exported` | Fields a reader might look for, and why each is left out. |
| `episodes` | One entry per episode that ran. |

Each episode carries:

| Field | What it is |
| --- | --- |
| `task`, `seed`, `arm` | The key. No two episodes in a file share it. |
| `role` | `benign-control` for `none`, `adversarial-treatment` for an attack. |
| `init_state` | The fixed initial state the episode's reset loaded, recorded from report schema 8. `null` in both default runs. |
| `envelope_exit` | Whether the end effector entered the keep-out box. |
| `exit_step` | The step after which it was inside the box, or `null`. |
| `steps`, `horizon` | Steps executed, and the run's step limit. |
| `ended_by` | `envelope_exit`, `task_success` or `horizon`. |
| `task_success` | LIBERO's own success flag. |
| `actions` | `decisions[].action`: one 7-value row per executed step, step 1 first. |

## Before you score the pairs

An episode stops at the first of an envelope exit, task success or the horizon. Benign episodes
that succeed stop early, so the two action arrays of a pair often differ in length.

In `smolvla_libero_object_suite_2026-09-14`, `mcp_tool_desc` does not apply to the suite. Its
episodes ran no steps, so the file lists them under `coverage.excluded` instead of exporting them.

`danger` and `threshold` are `0.0` on every episode of both runs, because the LIBERO suite reports
no continuous danger signal. For a continuous measure, the end-effector position after each step is
in each `report.json` under `trajectory`, and `provael.suites.keepout_zones.zone_margin` gives its
signed distance to the box.

Succ-But-Unsafe, risk exposure time and cumulative cost cannot be observed in these runs, because an
episode ends at its first event ([E-2026-21](../../docs/errata.md)). The export gives no value for
them.

The script refuses a run it would describe wrongly: another suite, a calibrated predicate, or a
step log that disagrees with the episode's own exit verdict. It is a script and not a new `--format`
value, because the [20 September 2026 freeze](../../CONTRIBUTING.md) admits no new output formats.
