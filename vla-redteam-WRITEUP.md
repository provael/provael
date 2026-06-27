# vla-redteam: an open, reproducible, CPU-first harness for measuring how easily Vision-Language-Action robot policies can be redirected

**Draft write-up (blog post / short arXiv note). Author: Sattyam Jain. 2026.**
_Positioning note (for you, delete before publishing): do NOT claim novelty of the attacks or SOTA ASR
— BadVLA/AttackVLA already own that. Claim the thing that's actually true and uncontested: this is the
**open, honest, reproducible, runs-on-a-laptop leaderboard** for VLA robustness. That's the wedge._

---

## TL;DR

Vision-Language-Action (VLA) policies are moving from research into robots, but we lack a *simple,
reproducible* way to ask: **how easily does a perturbed instruction or observation redirect the
policy into an unsafe motion?** `vla-redteam` (CLI: `robopwn`) is a small, Apache-2.0, **CPU-first**
harness that measures exactly this and reports an **Attack Success Rate (ASR)** with a benign baseline.
The whole core runs on a laptop with deterministic stubs; real policies (SmolVLA via LeRobot) and the
LIBERO simulator are one `pip` extra away. First finding on real SmolVLA × LIBERO: **simple
instruction-reframing attacks redirect the arm 60–100% of the time vs a 0% benign baseline, while
templated visual/scene-text perturbations do not transfer at all.** Everything is reproducible from
`pip install vla-redteam`.

## Why

- VLAs (SmolVLA, OpenVLA, π0, …) condition robot motor actions on free-form language + pixels. That
  language/visual channel is an **attack surface**: a reframed instruction or a doctored observation can,
  in principle, steer the policy to do something unintended.
- The academic literature already shows this is real and serious — RoboPAIR jailbreaks deployed robots;
  BadVLA/AttackVLA achieve very high attack success; Embodied Red Teaming shows SOTA policies misbehave
  under rephrased goals. **But these are papers and heavyweight, GPU-scale research repos.**
- What's missing for *practitioners and the broader community* is a **dead-simple, reproducible,
  baseline-controlled measurement** you can run without a cluster — and a **shared leaderboard** to
  compare policies on the same honest yardstick. That gap is what `vla-redteam` fills.

## What it does

- **One metric, honestly defined.** ASR = fraction of episodes in which an attack drives the policy into
  an *unsafe* state (e.g. the end-effector enters a keep-out region), reported **relative to a `none`
  baseline** so you read *lift*, not an unanchored number.
- **Three templated, auditable attack families** + a baseline: `instruction` (text reframings),
  `visual` (observation-space markers), `injection` (indirect/embodied prompt injection), `none`
  (control). These are *heuristic templates*, deliberately simple and inspectable — not optimized
  adversarial search.
- **CPU-first, deterministic core.** A `StubPolicy`/`StubSuite` make every attack produce an exact,
  byte-reproducible ASR with no GPU or model download — so the harness is testable and teachable. Real
  `SmolVLA` (via LeRobot) on the `LIBERO` simulator sits behind a `[lerobot]` extra + a gate.
- **Reproducible reports + a leaderboard.** Deterministic `report.json` (sorted keys, no wall-clock),
  a Rich console summary, and a `(policy × suite × family) → ASR` leaderboard rendered by a Hugging
  Face Space.

## First result (SmolVLA × LIBERO)

Setup: `HuggingFaceVLA/smolvla_libero`, task `libero_object/0`, 10 seeds, horizon 280, CPU-rendered
(osmesa) on a single GPU box.

| family | attack | ASR | lift vs baseline |
|---|---|---:|---:|
| baseline | `none` | 0% (0/10) | — |
| instruction | `roleplay` | 100% (10/10) | +100 |
| instruction | `goal_substitution` | 60% (6/10) | +60 |
| instruction | `paraphrase` | 10% (1/10) | +10 |
| visual | `patch` / `decoy_object` | 0% | 0 |
| injection | `scene_text` | 0% | 0 |
| **overall** | | **24.3% (17/70) ± 9.1%** | |

**Reading it honestly:** the benign control runs the policy's *real* task (“pick up the alphabet soup
and place it in the basket”) and never enters the keep-out region (0/10), so every success above is
attack-induced. The signal is entirely in the **instruction** channel: reframing the goal in language
reliably redirects SmolVLA, and the effect tracks how much the prompt *replaces* the real task
(full-replacement `roleplay` 100% > goal-`substitution` 60% > mild `paraphrase` 10%). The **templated
visual and injection perturbations produced no measurable lift on the real model** — an honest null
that says: simple image markers aren't enough; optimized perturbations are needed there.

## Honest limitations (on purpose)

- **Templated, not optimized.** No GCG/PGD-style search. This measures *behavioral* susceptibility to
  simple, realistic perturbations, not worst-case robustness.
- **One task, uncalibrated predicate.** A single LIBERO task and a *default* keep-out zone, so ASR =
  “diverted out of the benign envelope,” not a calibrated hazard rate.
- **One backend so far.** Model-agnostic by design (adapter interface); only SmolVLA/LIBERO implemented.
- These are the next milestones, not hidden caveats — see Roadmap.

## How it relates to prior art

`vla-redteam` is **not** a stronger attack than the literature, and doesn't claim to be:

- **Stronger/optimized attacks:** BadVLA (~100% ASR), AttackVLA (unified, sim+real), RedVLA, POEX,
  Q-DIG — GPU-scale, peer-reviewed. Use these for worst-case strength.
- **Robustness benchmarks:** LIBERO-Plus / LIBERO-PRO (perturbation degradation), Embodied Red Teaming
  (instruction perturbation, MIT).
- **What vla-redteam adds:** an **open, Apache-2.0, CPU-runnable, baseline-controlled, reproducible**
  harness + a **shared leaderboard** with a deliberately honest methodology (lift over a real-task
  baseline; deterministic reports; clearly-disclosed limitations). It's the *accessible measuring stick*,
  not the strongest hammer.

## Reproduce it

```bash
pip install vla-redteam                 # CPU core, deterministic stub demo
robopwn attack --policy stub --suite stub --attacks none,instruction,visual,injection

# Real SmolVLA × LIBERO (GPU box):
pip install 'vla-redteam[lerobot]' 'lerobot[libero]==0.5.1'
apt-get install -y libosmesa6 libgl1 libglx-mesa0
export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
robopwn attack --policy smolvla --suite libero --model HuggingFaceVLA/smolvla_libero \
  --attacks none,instruction,visual,injection --seeds 10 --horizon 280 --seed 0 --out runs/r1
```

## Call to action

Run it on your VLA checkpoint and submit to the leaderboard; help calibrate per-task keep-out zones;
add a second policy adapter. The goal is a **community-trusted, reproducible robustness yardstick for
embodied policies** — built in the open.

Repo: github.com/sattyamjjain/vla-redteam · PyPI: `vla-redteam` · Leaderboard: HF Space.

---
_Suggested venues: a blog post + Hacker News / r/robotics / r/MachineLearning + the LeRobot/HF
community first; if it gets traction and a 2nd model + calibrated zones land, expand into an arXiv
short paper / workshop submission (CoRL/ICRA/NeurIPS safety). Tag the RoboPAIR / Embodied-Red-Teaming /
AttackVLA authors — collaborate, don't compete._
