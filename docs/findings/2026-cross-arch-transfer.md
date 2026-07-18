# Cross-architecture transfer of templated attacks on VLA policies (2026-07)

> **Defensive, sim-only.** This is a red-team measurement artifact. It drives no physical robot and
> ships no real-world-harm payload — the battery perturbs only the observation/instruction a policy
> receives inside a simulator. See [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

## Question

When a templated attack redirects one VLA policy, is that a property of the **attack** or an artifact
of one **codebase's glue**? If the *same* battery moves policies from different architectures, the
vulnerability is about policy behaviour, and a buyer can't dismiss it as "our stack is different."
This study measures that, honestly, with the numbers we actually have.

## Method

The harness (`provael study cross-arch`, `studies/cross_arch_transfer/run.py`) runs the shared
**instruction / visual / injection** battery plus the benign `none` control against each architecture
through the *same* adapter → runner → scoring path — it **reuses** `provael.runner` and
`provael.scoring.asr`, so ASR, the 95% **Wilson CI**, and the **benign false-positive-rate** control
are computed by the same code every Provael run uses. Nothing about ASR is reimplemented for this
study.

Architectures: a deterministic **CPU stub** (always run, byte-stable, no GPU/network); **SmolVLA**
(LeRobot flow-matching); **π0** (served by Physical Intelligence's own `openpi` stack — a different
framework, same flow-matching action head). The two real backends are gated behind
`PROVAEL_INTEGRATION=1` + the `[lerobot]`/`[openpi]` extra. Because `[openpi]` and `[lerobot]` pin
conflicting numpy majors, each real backend is run in its **own environment** and the per-architecture
reports are merged offline (`merge_reports`).

## Findings

Every number below states the transfer-test it comes from. Absence of a number is reported as
**pending**, never filled with a fixture value.

### CPU-stub reference — a fixture property, **not** transfer

The deterministic stub (`policy=stub`, `suite=stub`, 10 episodes/attack, seed 0):

| family | ASR (95% Wilson CI) | n | benign-FPR |
| --- | --- | --- | --- |
| instruction | 70.0% [52–83%] | 30 | 0.0% |
| visual | 70.0% [48–85%] | 20 | 0.0% |
| injection | 60.0% [39–78%] | 20 | 0.0% |

These are properties of the deterministic test fixture, not a real VLA. **No cross-architecture
transfer is claimed from them** — they exist to prove the harness computes the table, deterministically
and GPU-free, so the real rows drop in unchanged when measured.

### SmolVLA (LeRobot flow-matching) — one real architecture, measured previously

From the repo's own SmolVLA × LIBERO transfer-test (sim-only, one task, n=10, against a 0% benign
baseline; see [README](https://github.com/provael/provael/blob/main/README.md) and [the Embodied AI Security Top 10](../TOP10.md)):

- **instruction transfers**: `roleplay` redirected the real policy **100% (10/10), 95% CI [72–100%]**;
  `goal_substitution` **60%**.
- **visual and injection do not**: both produced **0% measurable lift** on the real model — treated as
  stub-validated scaffolding pending stronger (e.g. optimised) perturbations, not a real-transfer
  claim.

This harness reproduces that measurement path; it did not itself re-run SmolVLA for this document, so
those figures are cited from the prior run, not re-measured here.

### π0 (openpi flow-matching) — **run pending**

The π0 leg is **not yet run**: it needs `provael[openpi]`, `PROVAEL_INTEGRATION=1`, and a running
openpi policy server, in an environment separate from the LeRobot one. **No π0 number is claimed.**
The harness emits it as `pending` until that run happens.

## What transfers, honestly

On the single real architecture measured so far (SmolVLA), **only the instruction family transfers**;
visual and injection do not. Whether that pattern — instruction-yes, perception-no — **holds across
architectures** is exactly the open question this harness exists to answer, and it stays open until π0
is run. We make **no "first" claim** and no cross-architecture claim ahead of the data. The attack
ideas are prior art (RoboPAIR, BadRobot; see [PRIOR_ART.md](https://github.com/provael/provael/blob/main/PRIOR_ART.md)); what is ours is the
small, reproducible, model-agnostic measurement.

## Why this matters for assurance and insurers

Two dates are closing in on anyone shipping AI-driven machinery into the EU. The **Machinery
Regulation (EU) 2023/1230 applies from 20 January 2027**, and its Annex III essential health-and-safety
requirements already carry **cybersecurity** obligations — protection against corruption (1.1.9) and
safety/reliability of control systems (1.2.1). Separately, the Commission must adopt delegated acts
adding **AI-specific health-and-safety requirements to the Machinery Regulation's Annex III by 2 August
2028**. Between those dates, a Notified Body assessing a robot — or an insurer pricing its liability —
will want pre-market evidence that the learned policy resists instruction-channel manipulation, with a
stated confidence interval and a benign control. A **cross-architecture** result strengthens that
evidence specifically: it shows a weakness is a property of the policy class, not one vendor's glue, so
it cannot be assured away by swapping frameworks. This artifact is that evidence in machine-readable
form (`results/cross_arch_transfer/summary.json`) — a measurement, **not** a conformity declaration or
legal advice.

## Reproduce

```bash
provael study cross-arch                      # CPU-stub table (deterministic, no GPU)
python studies/cross_arch_transfer/run.py     # + writes results/cross_arch_transfer/

# real legs (each in its own env, gated):
pip install 'provael[lerobot]'  # SmolVLA env
PROVAEL_INTEGRATION=1 provael attack --policy smolvla --suite libero \
    --attacks none,instruction,visual,injection --seeds 10
pip install 'provael[openpi]'   # π0 env (+ a running openpi server)
PROVAEL_INTEGRATION=1 provael attack --policy openpi --suite <lerobot-free image source> \
    --attacks none,instruction,visual,injection --seeds 10
```
