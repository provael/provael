# Reproduction request — one run, everything needed to attempt it

An independent rerun of a published result is a stronger signal than another registered attack,
and this page exists so that attempting one needs no private instructions. It points at **one**
result — the corrected sample, generated from the published body — and keeps three different
activities apart, because they answer three different questions:

| level | what you do | what it establishes |
| --- | --- | --- |
| **1 · verify** | check the digests (and the signature, where one exists) of the committed artifacts | that the artifacts you hold are the ones this repository published — origin and integrity, not validity |
| **2 · regenerate** | rebuild the derived artifacts (README tables, aggregate, delivery pack, evidence manifest) from the committed shards | that the published numbers follow from the stored per-episode records; no model runs |
| **3 · re-execute** | run the policy in the simulator again with the pinned inputs and compare | whether the finding holds under a fresh execution — the only level that is a scientific reproduction |

A completed level 1 or 2 is not evidence that the finding holds; say which level you did.

## The sample

`examples/delivery-pack/smolvla-libero-object-2026-09-14/` — SmolVLA (`HuggingFaceVLA/smolvla_libero`)
on the ten LIBERO-Object tasks, five seeds per (task, arm), horizon 280, measured with provael
0.41.2 on 14 September 2026 from the shards in `results/smolvla_libero_object_suite_2026-09-14/`.
Its `REPRODUCE.md` lists the pinned inputs; its `shards.txt` and `evidence-manifest.json` carry the
digests; its `README.md` states the decision under the example protocol and the provenance gaps the
shards have (they ran on 0.41.2 and record no repository, commit, lock digest or precision — known,
labelled, not backfilled).

## What to expect at level 3

- `roleplay` well above the benign floor: 42/50 here (84%), task-clustered 95% interval
  [62%, 100%], against `none` at 1/50; McNemar exact p ≈ 1e-12. `goal_substitution` 7/50 and
  `paraphrase` 1/50; `patch`, `decoy_object`, `scene_text` at or near the floor (1–2/50);
  `mcp_tool_desc` not applicable on this suite (0 attempts, never 0%).
- Clean task success on the benign arm above 0.9 (48/50 here).
- **Uncertainty.** The policy samples its actions and cross-seed spread on LIBERO is roughly 14
  percentage points; the earlier run of the same configuration on 0.32.0 gave 44/50 for `roleplay`
  and 15/50 for `goal_substitution`. Compare intervals, not points; a `goal_substitution` figure
  anywhere in [6%, 34%] is consistent with both committed runs.
- **Hardware and time.** One task per container: ~1.5 GPU-hours per task on an NVIDIA L4, ~15
  GPU-hours for the ten; the workstation run used an RTX 2000 Ada. The Modal driver is
  `examples/gpu-ci/modal_libero_suite.py`; the per-task command shape is in the pack's `REPRODUCE.md`.
- **Known limits.** Linux only for the LIBERO simulator; `lerobot[libero]==0.5.1` with the torch it
  pins; the default (uncalibrated) keep-out predicate — a calibrated run is a different
  measurement; the shards record no resolved checkpoint revision, so pin one and record it.

## Report what you found

Open an issue with the **Reproduction result** template
([`.github/ISSUE_TEMPLATE/reproduction-result.yml`](https://github.com/provael/provael/issues/new?template=reproduction-result.yml)).
It asks for the level, the exact environment (versions, hardware, checkpoint revision, simulator
build), the per-arm counts, and whether you read the result as agreeing, disagreeing, or null. A
disagreement or a null is as welcome as an agreement and gets the same investigation: the first
thing compared is the environment diff, not the conclusion. Results are recorded in the
[reproduction register](errata.md#reproduction-register) with the level you reported; a request
that has been prepared, like this page, is not an external validation and is never counted as one.

Do not attach private checkpoints or data; a reproduction of the public result on the public
checkpoint is what this page asks for.
