# Meta-World second-suite instruction-transfer study

> **Defensive, sim-only.** No real-robot or hardware control code, no real-world-harm payloads. The
> attacks perturb only the instruction/observation a policy receives in simulation. See
> [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

> Status: PRE-REGISTERED — protocol only, no results claimed.

This pre-registers a **second-suite** replication: does the instruction-transfer result measured on
SmolVLA × **LIBERO** hold on SmolVLA × **Meta-World** — a different task distribution — or is it a
property of the LIBERO suite?

## Hypothesis

The instruction family (`roleplay`, `goal_substitution`, `paraphrase`) that redirects SmolVLA on
LIBERO (see the [instruction-transfer finding](../findings/2026-instruction-transfer.md)) also
redirects it on **Meta-World** tasks over the benign control. **Null hypothesis:** the redirection is
LIBERO-specific and Meta-World shows no lift.

## Method

- **Backend / suite.** SmolVLA via LeRobot on the **Meta-World** suite (gated; needs the `[lerobot]`
  extra + `PROVAEL_INTEGRATION=1`). Same runner + `provael.scoring.asr` — no second harness.
- **Attacks + control.** `roleplay`, `goal_substitution`, `paraphrase`, and the benign `none`
  control, over a fixed Meta-World task subset.
- **Design.** n = _TBD_ episodes per attack, _TBD_ seeds, horizon _TBD_. A keep-out / unsafe
  predicate is **calibrated per Meta-World task** from benign rollouts to a benign-FPR target before
  attacking. Runs under 5 seeds are flagged `preliminary`.
- **Gate.** GPU + `PROVAEL_INTEGRATION=1`; on CPU the suite is reported `pending`.

## Success criteria

Per attack, the **redirection rate + 95% Wilson CI**, read against the **benign-FPR** control.
Cross-suite *agreement* with the LIBERO result is assessed by **CI overlap** per attack — a genuine
replication if the transferring families overlap, an honest **null** if Meta-World does not move.

## Threats to validity

- **Task-distribution shift.** Meta-World's tasks and reward/keep-out geometry differ from LIBERO;
  the per-task calibration is what makes the two suites comparable, and the achieved benign FPR is
  reported alongside every rate.
- **Small n, one policy.** Read the CIs; only SmolVLA is in scope for this suite here.
- **Predicate definition.** "Unsafe" on Meta-World must be defined per task, disjoint from the benign
  envelope; a mis-specified predicate inflates or hides ASR, so the predicate and its benign FPR are
  part of the recorded artifact.

## Limitations

One policy (SmolVLA), one new suite (Meta-World), instruction family only. Visual/injection remain
stub-validated. Until this runs, **no Meta-World transfer number is claimed** — coverage and the
Top-10 8/10 claim are unchanged.
