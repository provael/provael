# vla-redteam — launch posts (honest framing, no overclaim)

_Rule: lead with the honest result and the limitations. This community punishes hype and rewards
candor — and candor is exactly your differentiator vs the louder academic baselines. Post the write-up
first (blog/LinkedIn), then HN/Reddit pointing at it. Don't claim novelty or SOTA._

---

## 1) Hacker News — "Show HN"

**Title:**
`Show HN: vla-redteam – measure how easily a robot VLA policy is redirected (CPU-first)`

**First comment (post immediately after submitting):**

> I built vla-redteam (CLI: robopwn), an Apache-2.0 tool that red-teams Vision-Language-Action robot
> policies in simulation and reports an Attack Success Rate — how often a perturbed instruction or
> observation drives the policy into an unsafe motion, measured as lift over a benign baseline.
>
> Why: VLAs map free-form language + pixels straight to motor actions, so that input channel is an
> attack surface. The research (RoboPAIR, BadVLA, AttackVLA, MIT's Embodied Red Teaming) shows it's
> real, but the tooling is GPU-heavy and fragmented. I wanted something you can actually run on a
> laptop and reproduce.
>
> The honest part: the whole core runs on CPU with deterministic stubs (no GPU/model). Real SmolVLA
> (via LeRobot) on LIBERO is one `pip` extra. First real result — SmolVLA × LIBERO, 10 seeds:
> instruction-reframing attacks redirected the arm 60–100% of the time vs a 0% benign baseline, while
> my templated visual/scene-text attacks did NOT transfer to the real model (0%). So the signal is
> entirely in the language channel, for now.
>
> What it is and isn't: it's an open, reproducible, baseline-controlled measuring stick — not a
> stronger attack than the literature (BadVLA/AttackVLA optimize; mine are simple templates) and not a
> calibrated hazard rate yet (one task, a default keep-out zone). Those are the next milestones, and
> they're written up front in the README's limitations.
>
> Repo: https://github.com/sattyamjjain/vla-redteam · `pip install vla-redteam`
> I'd love feedback on the methodology (especially the keep-out predicate calibration) and pointers to
> VLA checkpoints to add to the leaderboard.

---

## 2) LinkedIn (you've launched here before — this is the honest v2)

> I open-sourced **vla-redteam** — a small tool that asks a blunt question about robot foundation models:
> **how easily can a perturbed instruction redirect a Vision-Language-Action policy into an unsafe
> motion?**
>
> VLAs (SmolVLA, π0, OpenVLA) turn language + camera input into robot actions. That makes the
> instruction/observation channel a real, physical attack surface. vla-redteam perturbs that channel in
> simulation and reports an Attack Success Rate — as **lift over a benign baseline**, so the number
> means something.
>
> First real result (SmolVLA × LIBERO): simple instruction-reframing attacks redirected the arm
> **60–100%** of the time vs a **0%** benign baseline. Notably, my templated *visual* and *scene-text*
> attacks did **not** transfer to the real model — an honest null that tells you where the real risk
> (and the real work) is.
>
> Design choices I care about: it runs **CPU-first** (deterministic, no GPU needed to use or extend),
> it's **Apache-2.0**, and it ships its **limitations up front** (templated attacks, one task, an
> uncalibrated predicate). It's meant to be the *accessible, reproducible measuring stick* for embodied-
> policy robustness — not a stronger attack than the excellent academic work it builds on.
>
> Repo + `pip install vla-redteam`: https://github.com/sattyamjjain/vla-redteam
> Building toward a community leaderboard. If you work on VLAs or robot safety, I'd love your eyes on
> the methodology. #robotics #AIsafety #VLA #opensource

---

## 3) Reddit — r/robotics and r/MachineLearning

**Title:** `[P] vla-redteam: an open, CPU-first harness for measuring how easily VLA robot policies get redirected`

**Body:**

> I made an open-source tool (Apache-2.0) that red-teams Vision-Language-Action robot policies in sim
> and reports an Attack Success Rate as lift over a benign baseline.
>
> The premise: VLAs condition motor actions on language + pixels, so a reframed instruction or doctored
> observation can steer the policy. Lots of great papers on this (RoboPAIR, BadVLA, AttackVLA, Embodied
> Red Teaming) but the tooling is heavy. I wanted a reproducible, laptop-runnable version + a shared
> leaderboard.
>
> First real result (SmolVLA × LIBERO, 10 seeds): instruction-reframing attacks 60–100% vs a 0% benign
> baseline; my templated visual/scene-text attacks did NOT transfer (0%). Honest scope: templated (not
> optimized) attacks, one task, an uncalibrated keep-out zone — all stated in the README.
>
> Core runs on CPU with deterministic stubs; real SmolVLA via LeRobot + LIBERO behind a `pip` extra.
> Repo: https://github.com/sattyamjjain/vla-redteam · `pip install vla-redteam`
>
> Looking for: methodology critique (esp. keep-out-zone calibration), and VLA checkpoints to add. Not
> claiming SOTA attacks — aiming for the open, reproducible robustness yardstick.

---

## 4) X / Twitter thread (optional, short)

1/ Open-sourced vla-redteam: how easily can a perturbed instruction redirect a Vision-Language-Action
robot policy into an unsafe motion? It measures Attack Success Rate as lift over a benign baseline.
`pip install vla-redteam`

2/ First real result (SmolVLA × LIBERO, 10 seeds): instruction-reframing attacks redirect the arm
60–100% vs a 0% benign baseline. My templated visual/scene-text attacks didn't transfer (0%) — the
risk, for now, is in the language channel.

3/ Honest by design: CPU-first + deterministic core (no GPU to use it), Apache-2.0, and limitations up
front (templated attacks, one task, uncalibrated zone). It's the accessible measuring stick, not a
stronger attack than BadVLA/AttackVLA. Repo: github.com/sattyamjjain/vla-redteam

---

## Timing / etiquette
- Post the **write-up first**, then HN (Tue–Thu, ~8–10am ET tends to do well), then Reddit, then X.
- Reply to every comment for the first few hours — engagement drives ranking and is where the real
  feedback (and contacts) come from.
- Cross-post into the **LeRobot/Hugging Face Discord** and tag/cc the prior-art authors as collaborators,
  not competitors.
