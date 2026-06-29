# Does sim red-teaming predict real-robot behaviour?

> The first objection to any simulation-only safety tool is "but it's only sim." This page is the
> honest answer, with citations — not a promise.

## The short version

Provael is a **pre-deployment** scanner: it measures how often an attack drives a policy out of
its safe envelope **in simulation**, before that policy ever touches hardware. The relevant
research finding is that, for VLA policies, **sim (and even edited-image) evaluation predicts
real-robot failure well enough to be useful** — without breaking real robots to find out.

- **Predictive Red Teaming** (Majumdar et al., 2025) degrades a policy's *inputs* (lighting,
  textures, distractors, camera pose) in sim / on edited images and shows the predicted
  per-factor success tracks real-robot success with a small gap (reported mean absolute error
  **< 0.19**), identifying brittle factors *without* real-world rollouts.
  arXiv:2502.06575 · https://arxiv.org/abs/2502.06575
- **Robustness benchmarks** (LIBERO-Plus, LIBERO-PRO, 2025–26) independently find VLAs collapse
  under camera/position shifts and largely ignore language perturbations — the same failure modes
  Provael's instruction/visual families exercise. arXiv:2510.13626
- **Real-to-sim** evaluation (SimplerEnv) is the methodology VLA papers use precisely because sim
  rankings track real hardware closely enough to compare policies. https://simpler-env.github.io/

## What this does and does not claim

- **Does:** give a reproducible, controlled, pre-deployment signal (calibrated ASR + 95% CI +
  benign-FPR control) that flags brittle policies early and cheaply, and that the literature says
  correlates with real-robot brittleness.
- **Does not:** certify real-world safety, predict a specific robot's behaviour on a specific day,
  or replace hardware testing and functional-safety processes. Treat the ASR as a **floor on
  susceptibility**, not a guarantee. See [COMPLIANCE.md](COMPLIANCE.md) (evidence, not
  certification) and the README's "Scope and honest limitations."

## How to keep your own results honest

- Always run the `none` benign baseline and read every attack rate **against that control**.
- Calibrate the predicate to a benign-FPR target (`provael calibrate`) so "unsafe" means
  "diverted past the policy's own benign envelope," not an arbitrary threshold.
- Report CIs and `n`, not just point estimates — `n = 10` per attack is a screen, not a proof.
