# Embodied AI Security Top 10 ↔ SafeVLA-Bench crosswalk

> **Defensive, sim-only.** This is a taxonomy-comparability artifact. It runs no SafeVLA-Bench
> harness, publishes no comparative scores against their numbers, and drives no physical robot. See
> [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

!!! warning "mapping_status: `aspirational` — nothing here is implemented"

    Unlike the [RoboJailBench](robojailbench.md) and [ForesightSafety-VLA](foresight-safety-vla.md)
    crosswalks, **there is no `provael crosswalk --target safevla` and no emitted JSON.** This page
    documents a mapping we intend to build and the one blocker that stops it being honest today.
    Everything below is a design note, not a capability. Do not cite it as coverage.

## What this is (and is not)

**Source (pinned).** *SafeVLA-Bench: A Benchmark for the Success-Safety Gap in Vision-Language-Action
Models*, Fan, Xu, Sokolsky, Lee, Kong (University of Notre Dame; University of Pennsylvania),
arXiv:[2606.00773](https://arxiv.org/abs/2606.00773)
(submitted 30 May 2026) · [safevla.org](https://safevla.org). Quotations below are verbatim from the
abstract.

**Not [SafeVLA](https://arxiv.org/abs/2503.03480) (2025)**, which is an alignment *defense* with a
near-identical name. Two different works. See [PRIOR_ART.md](https://github.com/provael/provael/blob/main/PRIOR_ART.md).

## Why this crosswalk is worth building

Both instantiate on **LIBERO**, and provael's one measured real-policy result is SmolVLA ×
`libero_object`. A shared substrate is what separates a tractable crosswalk from a hypothetical one:
the same policy, on the same tasks, can in principle carry both an SBU and an ASR.

They "formalize task-aware safety requirements as **Signal Temporal Logic (STL)** specifications and
report native success with two unsafe-success metrics: **Succ-But-Unsafe (SBU)** … and **Violation
Severity Index (VSI)**".

## The two measure different failures

| | SafeVLA-Bench | provael |
| --- | --- | --- |
| When it acts | **post-hoc** — scores rollouts already produced | **pre-hoc** — perturbs the input first |
| Who causes the failure | **nobody**; the policy's own behaviour under ordinary instructions | **an adversary**, by construction |
| Safety definition | STL specifications over the trajectory | a keep-out predicate, currently **uncalibrated** |
| Denominator | rollouts of the native benchmark task | matched `(task, seed)` pairs against a benign twin |
| Headline | SBU, VSI | ASR with a 95% interval and a benign control |

**Neither is a substitute for the other.** A policy can score well on SBU and still have a high ASR;
a policy with a low ASR can be routinely unsafe on its own. A safety case citing only one is
answering half the question.

## The blocker, stated plainly

provael already has a field called `succ_but_unsafe`
([`scoring/asr.py`](https://github.com/provael/provael/blob/main/src/provael/scoring/asr.py)) whose
docstring names SafeVLA-Bench, and it computes the same per-episode quadrant: task-success **and**
unsafe. That shared name is exactly what makes a premature crosswalk dangerous.

**It does not share their units.** Theirs is an STL-violation judgement over a trajectory; ours is a
boolean from an **uncalibrated** keep-out predicate — on the ten-task LIBERO run the benign control
itself fired on 2/50 episodes, so our "unsafe" carries a false-positive floor their STL judgement
does not. Placing the two figures in one column would repeat precisely the error the
[ForesightSafety-VLA crosswalk](foresight-safety-vla.md) exists to avoid: *borrowing a benchmark's
vocabulary never implies borrowing its units.*

**Calibrating the predicate is the prerequisite**, and it is not done —
[`provael calibrate`](../measure-2-7.md) has never been run on LIBERO. Until it has, an SBU emitted
by provael and an SBU reported by SafeVLA-Bench are two different quantities wearing one name, and
publishing them adjacently would mislead in the direction that flatters us.

## What implementing it would take

1. Calibrate the keep-out predicate on LIBERO so "unsafe" has a defensible threshold.
2. Express at least one of their STL clauses as a provael danger predicate, and say which.
3. Emit `crosswalk.safevla.json` behind `provael crosswalk --target safevla`, carrying a
   `comparability` field per row — the same shape the other two crosswalks use, where the
   comparability column is the point of the table rather than a footnote.

Only step 3 is code. Steps 1 and 2 are measurements, which is why the status is `aspirational` and
not `in-progress`.

## Their finding a reader of our numbers should see

Independent of anything we measured: "high-SR tabletop baselines still leave **13 to 15 percent**
unsafe-episode rates, and **36 to 56 percent** of successful RoboCasa-365 rollouts violate at least
one active safety clause."

A policy can be *unattacked* and still unsafe at those rates. **provael's ASR is blind to that floor
by construction** — it measures lift over a benign control, so a policy already unsafe 15% of the
time with no adversary present does not show up in our headline at all. That is a real limitation of
our metric, not a criticism of theirs.
