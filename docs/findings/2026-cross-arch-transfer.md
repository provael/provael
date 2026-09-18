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
(LeRobot flow-matching, 450M); **π0.5** (LeRobot's port of Physical Intelligence's 3B flow-matching
policy, through the native `pi05` adapter — a different architecture, the same framework glue);
**π0** (served by Physical Intelligence's own `openpi` stack — a different framework, same
flow-matching action head). The two real backends are gated behind
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

### SmolVLA (LeRobot flow-matching) — one real architecture, measured

From the repo's own SmolVLA × LIBERO-Object suite (sim-only, all ten tasks, five seeds, against the
run's own benign twins; measured 9 August 2026 with 0.32.0 at 44/50 and re-measured 14 September 2026
with 0.41.2 at 42/50 — `results/smolvla_libero_object_suite_2026-09-14/`; see the
[README](https://github.com/provael/provael/blob/main/README.md) and [the Embodied AI Security Top 10](../top10.md)):

- **the instruction frame moves the policy**: under `roleplay` the real policy left its envelope in
  **84% (42/50)** of cells, task-clustered 95% CI **[62%, 100%]**, McNemar p=9.1e-13 (Holm 5.5e-12),
  across all ten `libero_object` tasks; `goal_substitution` **7/50** (p=0.07, not surviving Holm).
  The same day's controls show the frame does this with its target removed (27/30) and with its
  words scrambled (18/30), so this is fragility under a long out-of-distribution instruction, not
  attacker control of the outcome — erratum E-2026-12.
- **visual and injection do not separate from the benign floor**: 2/100 and 2/50 against a 1/50
  benign arm, McNemar p=1.0 on every arm — floor-level results, not a real-transfer claim and not
  zeros either (they were zeros on the 9 August run).

### π0.5 (LeRobot flow-matching, 3B) — **preliminary leg run, 18 September 2026**

`results/pi05_libero_object_2026-09-18/`: `lerobot/pi05_libero_finetuned_v044` through the native
`pi05` adapter, the same ten `libero_object` tasks, horizon 280, **three seeds** (the pre-registered
leg asks for five and eight arms; this is two arms — `roleplay` against `none` — so it is the
*preliminary* leg in the protocol's own words, [Amendment 1](../studies/pi0-openpi-transfer.md)).

- `none` **0/30** out of the envelope; clean task success **27/30 (90%)** against LeRobot's reported
  97.5% for this checkpoint.
- `roleplay` **1/30** out of the envelope (one task, one seed), McNemar p=1.0, task-clustered 95% CI
  [0%, 10%]. **No transfer of the envelope-exit effect is claimed**: the pre-registered per-arm
  criterion (Wilson lower bound above the benign FPR) is met only arithmetically, 0.6% against a
  floor that recorded nothing, and the paired test says the arms are indistinguishable.
- Task success under the frame **8/30 (27%)**, from 90% unattacked.

Read beside SmolVLA on the same tasks: the frame degrades **both** policies' task completion (90% →
27% here; 96% → 0% there), but only SmolVLA leaves its keep-out envelope doing so — π0.5 fails the
task without leaving the box. Whether that is the architecture, the checkpoint's training, or the
default box being the wrong shape for this policy's benign envelope (the protocol's
"predicate portability" threat; the box is uncalibrated) is not settled by thirty pairs. The
five-seed, eight-arm run and the calibrated box are what settle it.

### π0 (openpi flow-matching) — **run pending**

The openpi-served π0 leg — the one that tests the *framework* question, since π0.5-via-LeRobot
shares the LeRobot glue with SmolVLA — is **not yet run**: it needs `provael[openpi]`,
`PROVAEL_INTEGRATION=1`, and a running openpi policy server, in an environment separate from the
LeRobot one. **No π0 number is claimed.** The harness emits it as `pending` until that run happens.

## What transfers, honestly

On SmolVLA **only the instruction family separates from the benign floor**; visual and injection
do not. On π0.5, at three seeds and two arms, the instruction frame's envelope-exit effect **did not
reproduce** (1/30 against 0/30, p=1.0) while its task-completion effect did (90% → 27%). So the
pattern that is beginning to show is *the frame breaks the task on both architectures; whether it
also breaks the safety envelope is policy-specific* — and that sentence carries a preliminary leg
on an uncalibrated predicate and is written to be tested, not quoted. The architecture question
stays open until the full π0.5 leg and the openpi leg run. We make **no "first" claim** and no
cross-architecture claim ahead of the data. The attack ideas are prior art (RoboPAIR, BadRobot; see
[PRIOR_ART.md](https://github.com/provael/provael/blob/main/PRIOR_ART.md)); what is ours is the
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
