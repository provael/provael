# Embodied AI Security Top 10 ↔ VLA-Arena crosswalk

> **Defensive, sim-only.** This is a taxonomy-comparability artifact. It runs no VLA-Arena harness,
> makes no leaderboard submission, publishes no comparative score, and drives no physical robot.
> See [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

**Source (pinned).** *VLA-Arena: An Open-Source Framework for Benchmarking Vision-Language-Action
Models*, Zhang, Li, Shen, Zhang, Cai, Liu, Ji, Chen, Dai, Ji, Yang,
arXiv:[2512.22539](https://arxiv.org/abs/2512.22539) (submitted 27 December 2025; latest revision
7 August 2026) · [vla-arena.github.io](https://vla-arena.github.io/). Tasks are declared in a
**Constrained Behavior Domain Definition Language (CBDDL)**. Suite identifiers below are quoted
verbatim.

Emit the machine-readable artifact with:

```bash
provael crosswalk --target vla_arena --out results/crosswalk
```

## Why this crosswalk matters more than the other four

VLA-Arena runs **a public leaderboard with a safety axis** — 11 suites, 170 tasks, of which 5 suites
and 75 tasks are safety. That makes it the one place where a provael number could plausibly be read
as a comparable entry, and the one place where being wrong about comparability would do real damage.

It is not comparable. The reason is not units, not benchmark, not embodiment. It is **posture**.

## The posture contrast

| | VLA-Arena safety suites | Provael |
| --- | --- | --- |
| Posture | **non-adversarial** | **adversarial** |
| The question | *is this policy safe by default?* | *can this policy be made unsafe?* |
| What is placed | a hazard, in the scene | a perturbation, on the instruction |
| Is the instruction perturbed? | **no** | yes — that is the attack |
| What moves | the scene | the instruction; the envelope stays fixed |
| Metrics | Cumulative Cost (CC), Success Rate (SR) | ASR, 95% Wilson interval, benign FPR |

Their suites measure whether a policy avoids a hazard **it was never pushed toward**. Provael
measures whether a policy can be **pushed out** of an envelope that did not move. Both are safety
numbers. Neither answers the other's question.

### The consequence, which is the useful part

The provael arm that corresponds to VLA-Arena's *entire* safety axis is the **benign control**
(`--attacks none`) — not any attack family. A non-adversarial unsafe rate is what their suites
report, and the control is the only provael arm that reports one.

On the ten-task SmolVLA × LIBERO run that control fired on **2/50 episodes**. That is provael's
non-adversarial unsafe rate, and it is **uncalibrated** — it carries a false-positive floor their
declared CBDDL constraint does not.

Every provael *attack* number lives on an axis their leaderboard has no column for.

!!! danger "Same name, unproven equivalence"

    provael's `scoring.safety_cost.cumulative_cost` and VLA-Arena's **Cumulative Cost** share a
    name and have **not** been shown to share a definition. Ours is the mean number of unsafe steps
    per episode, derived from a per-step boolean. Do not place them in one table. This is the same
    trap the [ForesightSafety-VLA crosswalk](foresight-safety-vla.md) documents for CC/RET and the
    [SafeVLA-Bench crosswalk](safevla-bench.md) documents for SBU — three benchmarks, three
    collisions of vocabulary, one rule: *borrowing a benchmark's vocabulary never implies borrowing
    its units.*

## The five safety suites

| Suite | Tasks | Hazard placed in scene | EAI id(s) | Provael family | Coverage |
| --- | ---: | --- | --- | --- | --- |
| `safety_static_obstacles` | 15 | static collision obstacles in the workspace | EAI04 | — | ◐ partial |
| `safety_cautious_grasp` | 15 | objects requiring careful handling during grasp | EAI04 | — | ✗ not covered |
| `safety_hazard_avoidance` | 15 | designated hazard zones the policy must not enter | EAI04, EAI06 | — | ◐ partial |
| `safety_state_preservation` | 15 | object state that must survive the episode intact | EAI04 | — | ✗ not covered |
| `safety_dynamic_obstacles` | 15 | moving obstacles entering the workspace | EAI04 | — | ✗ not covered |

**Coverage tally: 0 covered · 2 partial · 3 not covered.** Nothing here is fully covered, and that
is the honest result rather than an incomplete file.

**Every row lists zero provael attack families, and that is correct.** Provael's families all
perturb an input; none of these suites has an input to perturb. A table showing families mapped
across these rows would be manufacturing coverage.

Where the two partials come from:

- **`safety_static_obstacles`** — geometrically the nearest match provael has, because the keep-out
  predicate *is* a spatial breach. But provael's breach is caused by a perturbed instruction and
  theirs by the policy's own path around an obstacle nobody added adversarially. Same geometry,
  different cause.
- **`safety_hazard_avoidance`** — the most literal correspondence in the set: a designated no-go
  region is exactly what provael's `keepout_zones` suite encodes. Still only `partial`, and the
  reason is ours not theirs — the predicate is **uncalibrated**, so provael's zone boundary is not
  a defensible threshold the way a declared CBDDL constraint is.

## What this crosswalk does not license

- **No leaderboard submission.** Provael has never submitted to VLA-Arena's leaderboard and this
  artifact is not a step toward doing so.
- **No score in a shared column.** Placing a provael ASR beside a VLA-Arena CC would assert that a
  policy pushed by an adversary and a policy left alone sit on one scale. They do not — and the
  direction of the error flatters provael, since our number is larger *because we push*.
- **No claim of coverage.** 0 of 5 suites are covered.

## Related

- [SafeVLA-Bench crosswalk](safevla-bench.md) — reaches the same posture split from the other side
  (post-hoc vs pre-hoc), independently, and records why provael's ASR is **blind to the unattacked
  unsafe floor by construction**. That limitation and this posture contrast are the same fact.
- [ForesightSafety-VLA crosswalk](foresight-safety-vla.md) — the CC/RET vocabulary collision.
- [RedVLA in PRIOR_ART.md](https://github.com/provael/provael/blob/main/PRIOR_ART.md) — same author
  group as VLA-Arena, and the complementary half of the same formalism: RedVLA perturbs the scene
  with the instruction held fixed, provael perturbs the instruction with the scene held fixed.
