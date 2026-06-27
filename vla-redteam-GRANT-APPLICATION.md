# Grant application draft — vla-redteam (open VLA robustness evaluation)

_Tailored for Manifund / LTFF / EA-aligned AI-safety funders. Two versions below: a short Manifund-style
pitch and a longer LTFF-style application. Edit the **[BRACKETS]** before submitting. Be honest — these
reviewers reward calibrated, non-hyped asks and penalize overclaiming._

---

## A. Manifund-style short pitch (~250 words)

**Project:** vla-redteam — an open, reproducible, CPU-runnable benchmark for how easily Vision-Language-
Action (VLA) robot policies can be redirected into unsafe behavior by perturbed instructions/observations.

**Ask:** **$[15,000–30,000]** for **[3–4] months** part-time to take it from a working prototype to a
calibrated, multi-task, multi-model leaderboard standard.

**Why it matters:** VLAs (SmolVLA, π0, OpenVLA) now map free-form language + pixels directly to robot
motor actions — a new, physically-consequential attack surface. The academic literature (RoboPAIR,
BadVLA, AttackVLA, Embodied Red Teaming) shows the risk is real, but the tooling is fragmented, GPU-heavy,
and not standardized. There is no *accessible, baseline-controlled, reproducible* way for the community to
measure and compare how robust a given policy is. vla-redteam fills that gap: its core runs on a laptop
(deterministic stubs, no GPU), real policies sit behind one extra, and it reports Attack Success Rate as
**lift over a benign baseline** with deterministic, auditable reports.

**Status (honest):** Apache-2.0, on PyPI, 88 tests, a first real result on SmolVLA × LIBERO
(instruction-reframing attacks redirect the arm 60–100% vs a 0% benign baseline). Limitations: one task,
an uncalibrated keep-out predicate, templated (not optimized) attacks, one model backend.

**Deliverables with this grant:** (1) per-task **calibrated hazard zones** so ASR is a real hazard rate;
(2) **multi-task, multi-suite** coverage; (3) a **second policy** to prove model-agnosticism; (4) a public
**submission flow** so others contribute results; (5) a short write-up. All open-source.

**Me:** [Sattyam Jain] — built vla-redteam solo; [prior project acquired]; [arXiv paper on VLA red-teaming].

---

## B. LTFF-style application (longer)

### One-sentence summary
Fund part-time work to turn vla-redteam — an open, CPU-first harness measuring VLA robot-policy
susceptibility to instruction/observation attacks — into a calibrated, multi-model robustness leaderboard
the embodied-AI community can trust and contribute to.

### The problem and why it's neglected
Embodied foundation models are moving from research into robots, and they condition physical actions on
natural-language goals and camera input. That channel is manipulable: a reframed instruction or doctored
observation can redirect a policy into unsafe motion. This is **safety-relevant** (physical harm, not just
text), **timely** (VLA deployments projected to grow sharply over the next two years; EU AI Act Art. 15 and
ISO 10218:2025 now name adversarial robustness; DARPA's SAFRON program targets exactly this), and
**under-served on the tooling side**: the existing work is excellent but lives as heavyweight, GPU-scale
research repos and papers. There is no lightweight, reproducible, **baseline-controlled** measuring stick
or shared leaderboard — the kind of common yardstick that accelerated LLM-safety progress (e.g. HELM,
garak, Inspect). vla-redteam aims to be that for embodied policies.

### What exists today (verifiable)
- Apache-2.0, `pip install vla-redteam`, CLI `robopwn`; 88 tests; strict typing; deterministic reports.
- CPU-first deterministic core (no GPU/model needed to learn/extend the tool); real SmolVLA via LeRobot +
  LIBERO behind an optional extra.
- First real result (SmolVLA × LIBERO, 10 seeds): instruction-reframing attacks 60–100% vs 0% benign
  baseline; templated visual/scene-text attacks did not transfer — an honest null.
- A Hugging Face Space leaderboard scaffold.

### Honest limitations (what this grant fixes)
One task; an **uncalibrated** keep-out predicate (so ASR ≠ a calibrated hazard rate yet); **templated**
(not optimization-based) attacks; a single model backend. These are exactly the milestones below.

### Deliverables and milestones
1. **Calibrated hazard zones (month 1):** derive per-task benign EE envelopes from rollouts; define
   semantically-meaningful keep-out regions disjoint from benign behavior; commit configs + justifications.
   → ASR becomes a defensible hazard rate.
2. **Multi-task / multi-suite coverage (month 1–2):** LIBERO object/goal/spatial/10, several tasks each;
   per-task and aggregate ASR with mean±std.
3. **Second policy adapter (month 2):** add a second real VLA to demonstrate model-agnosticism.
4. **Public submission flow + leaderboard v1 (month 3):** schema-validated PR submissions; CI-rebuilt
   leaderboard; documentation so external groups can submit their checkpoints.
5. **Write-up (month 3–4):** a short report/blog positioning the tool honestly next to prior art, plus an
   updated PRIOR_ART comparison.

### Theory of impact
A trusted, open, low-friction robustness benchmark (a) gives robot-policy builders a cheap pre-deployment
check, (b) standardizes how the field reports embodied-policy robustness, and (c) surfaces which attack
classes actually transfer to real policies — concentrating effort where it matters. Even a modest-adoption
outcome produces a reusable public good and a clearer picture of embodied-AI risk.

### Budget (itemized)
- Maintainer time: **$[12,000–24,000]** for **[3–4] months** part-time at **$[rate]**.
- GPU/sim compute (RunPod/Lambda, real rollouts across tasks/models): **$[1,500–3,000]**.
- Misc (domain, docs hosting — minimal): **$[100]**.
- **Total: $[15,000–30,000].**

### Track record
[Sattyam Jain] — built and shipped vla-redteam solo (design, real SmolVLA×LIBERO integration found and
fixed by running, release automation); [prior project pyAGI — acquired]; [arXiv paper red-teaming VLAs].
Demonstrated bias toward verified, honest results (the project ships its own limitations prominently).

### Risks and honest priors
- **Adoption risk:** comparable academic tools often see modest adoption; mitigated by CPU-accessibility,
  honest methodology, and a zero-friction submission flow. If external pull stays low after the write-up,
  the work still yields a reusable public benchmark and a clear risk readout.
- **Field is competitive:** stronger optimized attacks exist (BadVLA/AttackVLA); this project deliberately
  competes on *accessibility, reproducibility, and standardization*, not attack strength.
- **Scope discipline:** part-time, milestone-gated; no commercialization is assumed or required.

### What success looks like in 4 months
≥2 policies × multiple LIBERO suites with calibrated zones on a public leaderboard, at least one external
submission, and a write-up the community can cite — a credible open robustness yardstick for VLA policies.
