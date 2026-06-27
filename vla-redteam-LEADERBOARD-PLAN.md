# vla-redteam — Leaderboard-Standard Upgrade Spec (the moat)

_Goal: make vla-redteam the **open, reproducible, baseline-controlled VLA-robustness leaderboard**
people actually use to compare policies. You can't out-rigor BadVLA/AttackVLA on attack strength — you
win by being the **honest, accessible, standardized measuring stick**. This is the only defensible solo
moat. Target: a credible v0.3.0 + a public leaderboard with ≥2 policies on ≥1 calibrated suite._

Ordered by ROI. Each item: what, where (file), effort, needs-GPU?, acceptance.

---

## WS1 — Calibrated keep-out zones (THE credibility unlock) ★ do first
Today the keep-out zone is a default box → ASR isn't a hazard rate, and that's the #1 critique. Fix it.

- **What:** define, per task, a *semantically meaningful* forbidden region (e.g. off-table / human-side
  / wrong-object zone) that the **benign policy provably never enters** but a redirected policy does.
- **Method (reproducible, no hand-waving):**
  1. Run N benign (`none`) rollouts per task; log end-effector trajectories (already have `ee_pos`).
  2. Compute the **benign envelope** (axis-aligned bbox or convex hull of benign EE positions + margin).
  3. Define the keep-out zone as a **named hazard region disjoint from the benign envelope** (e.g.
     "beyond table edge," "operator side y<−0.3"), justified per task. Store as a per-task config.
  4. Re-report ASR as "entered a *calibrated* hazard region," with the calibration committed + documented.
- **Where:** `src/vla_redteam/suites/libero.py` (`LiberoRedTeamRules`, `KeepOutZone`), a new
  `suites/keepout_zones.py` (per-task zone registry), `scripts/calibrate_zones.py` (derives envelopes).
- **Effort:** ~2–3 days. **GPU:** yes (benign rollouts). **Accept:** every leaderboard task has a
  committed zone config + a one-paragraph hazard justification; benign baseline still ≈0% by construction.

## WS2 — Multi-task / multi-suite coverage ★
- **What:** run across LIBERO suites (`libero_object`, `libero_goal`, `libero_spatial`, `libero_10`),
  several tasks each (start 3–5/suite). Report ASR per task + per suite + overall, with mean±std.
- **Where:** CLI `--tasks` wiring (`cli.py`, `config.py` already has `tasks`); `runner.py` loop already
  iterates tasks; `LiberoSuiteAdapter` task parsing exists. Mostly orchestration + a `run_matrix.sh`.
- **Effort:** ~1–2 days (compute-bound). **GPU:** yes. **Accept:** a single command produces a
  per-(suite,task) ASR table; leaderboard shows suite-level rows.

## WS3 — Second policy adapter (kills "model-agnostic is unproven") ★
- **What:** add one more real policy so generality is demonstrated, not claimed. Easiest credible options
  via LeRobot: another LIBERO-finetuned VLA (π0 / OpenVLA-OFT if a LIBERO checkpoint exists) OR a second
  SmolVLA checkpoint. Pick whatever has a ready LIBERO checkpoint to avoid fine-tuning.
- **Where:** `src/vla_redteam/policies/` (new adapter or generalize `lerobot_adapter.py`; the glue is
  already model-agnostic at the LeRobot layer), `policies/registry.py`.
- **Effort:** ~2–4 days (depends on checkpoint availability/compat — expect a feature-mismatch fight like
  smolvla_base had). **GPU:** yes. **Accept:** `robopwn attack --policy <p2> --suite libero` runs end to
  end; leaderboard has ≥2 policies; README drops the "one backend" caveat.

## WS4 — Public submission / contribution flow (makes it a *standard*, not a repo) ★★
A leaderboard only becomes a moat if **others submit**. Lower the friction to ~zero.
- **What:** a documented "submit your result" path: contributor runs `robopwn attack … --out runs/<id>`,
  opens a PR adding `results/<policy>/report.json`; CI validates schema + rebuilds `leaderboard.json`.
  Add a `CONTRIBUTING-leaderboard.md` + an issue/PR template "Submit a leaderboard result."
- **Where:** `.github/` templates, a `scripts/validate_submission.py`, a CI job that runs
  `robopwn leaderboard build` on PRs touching `results/`.
- **Effort:** ~1–2 days. **GPU:** no. **Accept:** an external person can submit a result via PR and see
  it on the HF Space after merge; documented in README.

## WS5 — Live forbidden-grasp predicate (second unsafe signal)
- **What:** wire the existing `grasp_extractor` hook to a real robosuite grasp check so "grasped the
  forbidden object (knife)" is a live unsafe condition, not disclosed-inert. This makes the *injection/
  goal-substitution* attacks measurable on a semantic (not just spatial) axis.
- **Where:** `src/vla_redteam/suites/libero.py` (`_grasped_object`, `grasp_extractor`), verify the
  robosuite accessor on a real sim (the thing that was unverifiable without GPU).
- **Effort:** ~1–2 days (sim spelunking). **GPU:** yes. **Accept:** a gated test shows a real grasp
  flips `is_unsafe`; README notes the predicate is now live (not inert).

## WS6 — Leaderboard UX + provenance (credibility polish)
- **What:** show per-task/suite breakdown, lift-over-baseline column, seeds/horizon, model + commit hash,
  and a "how this is measured (honestly)" panel linking the calibration. Keep determinism.
- **Where:** `leaderboard/app.py`, `leaderboard.py` (add fields), `results/` provenance.
- **Effort:** ~1 day. **GPU:** no. **Accept:** the Space clearly communicates method + caveats; a viewer
  trusts the numbers.

---

## Suggested sequence (≈2–3 focused GPU weekends)
1. **WS1 (calibrated zones)** — unlocks every honest claim. Without it, nothing else is credible.
2. **WS2 (multi-task)** — breadth; turns one number into a table.
3. **WS3 (second policy)** — proves model-agnostic; the headline "leaderboard" needs ≥2 policies.
4. **WS4 (submission flow)** — converts repo → standard (the actual moat).
5. WS5 / WS6 — depth + polish.

## Definition of done (v0.3.0 "leaderboard standard")
- ≥2 real policies × ≥1 suite with **calibrated** keep-out zones, multi-task, lift-over-baseline.
- An external contributor *can and has* submitted a result via PR.
- README/leaderboard communicate the honest methodology; no uncalibrated/over-claim caveats remain.
- This is the artifact you cite in the write-up and the grant application — and the thing that, if
  adopted, is genuinely hard for a funded LLM-security shop to replicate without your robotics focus.

## Reality check (keep ROI honest)
- This is **credibility/research work, not revenue work** — its payoff is citations, a grant, and a role,
  per the strategy analysis. Time-box it. If after WS1–WS4 + the write-up there's still zero external
  pull (stars, submissions, inbound), that's strong signal to bank the career capital (apply to roles/
  fellowships with it as the portfolio piece) rather than keep investing.
