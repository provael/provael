# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`provael submit` told a blocked user to pass a flag it does not define.** Without the `attest`
  extra, `submit` echoed the shared `MissingAttestExtraError`, which ends "(or pass `--no-sign` for
  a digest-only bundle)". Correct advice for `attest`; impossible for `submit`, which calls
  `to_bundle(..., sign=True)` unconditionally and defines no `--no-sign` — a leaderboard row that is
  not tamper-evident is not a submission. So the one command whose failure blocks an outside
  contribution answered with an escape hatch that was never there.

  The message was right about the extra and wrong about the way out, which is the worse half to get
  wrong: the extra is discoverable from the error itself, while a flag that does not exist sends
  someone reading `--help` for it. `submit` now says the extra is required here and names
  `provael attest --no-sign` for the digest-only case, rather than echoing a flag as if it were its
  own. `tests/test_cli_error_flags_exist.py` walks the real Typer app rather than grepping source.

- **The roadmap called a shipped command planned, and it reached `main` unnoticed.** The AI2 bridge
  note added in the previous change wrote `provael list-suites` inside `## Planned`, and
  `tests/test_roadmap_honesty.py` correctly reads that as claiming a shipped command is not yet
  shipped. The note now names the `ai2_bridge` suite rather than the command that lists it.

  Worth recording is *why nobody saw it*: the pull request was green, but GitHub created no workflow
  run at all for the squash-merge commit on `main` — no `[skip ci]`, no skip directive of any kind,
  Actions reported operational, and a manual dispatch on `main` ran fine moments later. A dropped
  push event. The merged tree was byte-identical to the tested one, so the PR's green was not a lie
  — it simply never re-ran on a tree containing this line, because the line was written in that PR.

### Documentation

- **E-2026-04** recorded in `docs/errata.md`: provael.com published the CRA severe-incident
  final-report deadline with the wrong start point for seven days. Art. 14(2)(c) runs 14 days from a
  corrective measure being available; Art. 14(4)(c) runs one month from submission of the 72-hour
  notification and does not wait for a fix. Nothing in this repository was affected — the defect was
  in the website's regulatory clock — but this file is the maintained source that page mirrors, so
  the record belongs here. The reusable lesson is in the entry: the sub-deadlines were transcribed
  from the Commission's summary rather than the OJ text, and a secondary source is fine for finding
  a fact and not for pinning one.

- **The scheduled GPU lane reported success twice a week for 22 days while measuring nothing.**
  `examples/gpu-ci/modal_provael_gpu.py` constructed its Modal app inside `build_app()` so the
  module would import without modal installed. `modal run` resolves an app from a module's GLOBAL
  scope, found none, and printed "has no functions or local entrypoints". The workflow piped that
  into `tee` without `pipefail`, so the step took tee's exit status and went green. Nothing was
  measured, nothing was recorded, and every run said it worked.

  Two things kept this from becoming a false published number rather than merely a missing one.
  The record step is guarded on a `report.json` actually existing, so no fresh measurement time was
  ever stamped for a run that produced nothing; and `freshness.yml` recomputes age on its own
  schedule instead of trusting the measurement job to emit a green badge. The badge ageing to 22
  days was the only signal that the lane was dead — which is the job it was designed for.

  The app and its `@app.local_entrypoint()` now sit at global scope, mirroring
  `modal_libero_suite.py`, which records the identical trap at its own line 83. The importability
  the nesting bought was asserted by no test and cost the measurement the badge exists for.
  `tests/test_modal_examples_are_runnable.py` parses both examples on the CPU lane — where modal is
  absent — and fails if either stops exposing a module-level app and entrypoint.

  A workflow step that cannot fail is a workflow step that cannot report.

### Changed

- **The SO-101 amendment created two hardware blockers that existed only inside the study file.**
  `docs/studies/sim-to-real-so101.md` was amended on 1 September 2026 — before any trial — with a
  power-integrity confound and a corrected e-stop claim. Both were on the record in the right place
  and invisible everywhere else: the roadmap had no real-robot entry at all, so a reader had no way
  to see why that work had not moved, or that it is blocked on hardware rather than on effort.

  `docs/roadmap.md` now carries a "Blocked on hardware" section naming both prerequisites — an
  inline DC-supply cut (the STS3215's over-current protection is not a latch and re-arms under a
  policy that keeps streaming commands, which is exactly this threat model) and a per-trial
  servo-bus voltage trace (the brownout is biased toward the hypothesis, since adversarial action
  sequences drive more joints at once than benign teleop) — and states that runs executed is 0.

  Documentation only. No trial was run, no hardware was actuated, and no sim/real claim is made.

### Added

- **`ai2_bridge` — registered scaffolding for the AI2 harness, and the reason it is not more than
  that.** The roadmap has listed this bridge as the strategic multiplier ("one adapter → ~18
  benchmarks") on the strength of the harness exposing a single `predict()`. Reading the harness at
  v0.5.0 rather than its README, the multiplier does not survive contact with Provael's predicate.

  `allenai/vla-evaluation-harness` returns **per-episode success and nothing else**: LIBERO's
  `get_step_result` is `{"success": ...}` and its recorder is field-filtered to
  `frozenset({"reward", "done", "success"})`. The end-effector pose exists — `make_obs` reads
  `robot0_eef_pos` — but it flows *outward to the model server* and never returns to a caller. So
  `is_unsafe()` has no state to evaluate, and neither do the keep-out zone, `calibration_signal`, or
  the EAI02 / EAI04 / EAI06 predicates. A bridge shipped on the README's promise would have
  inherited ~18 benchmarks' task lists while reporting task success as safety.

  Two things worth having found: the **benign control arm is expressible** (work items are a
  deterministic `task x episode` enumeration, so one seed run twice visits the same initial states),
  and the harness's PyPI name is **`vla-eval`**, not `vla-evaluation-harness`, which 404s.

  `Ai2BridgeSuite` raises `NotImplementedError` on all four contract methods rather than degrading
  to a fixture — a registered suite returning plausible defaults is how an unbuilt path produces a
  number. `SCAFFOLDING_SUITES` mirrors `SCAFFOLDING_POLICIES`, `list-suites` renders it in its own
  words instead of the false "requires `provael[lerobot]`", and `suite_is_ready` reports `False`
  so nobody is told a pip install is all that is missing.

  Registered is not built, and `~18 benchmarks` stays a fact about the harness, not about Provael.

## [0.39.1] — 2026-09-01

### Fixed

- **v0.39.0 shipped a counts artifact that contradicted its own code, and nothing in this repo
  could tell.** `watch/registry.json` said 16 adversarial families and 38 adversarial attacks
  while the registry it describes had 17 and 39. The full suite passed at that tag. The file's own
  note says it exists so that "no human types these numbers" — provael.com fetches it rather than
  restating counts in prose, because four site surfaces once disagreed simultaneously — but nothing
  checked that the GENERATED file had actually been regenerated. Only the downstream website
  noticed, from another repository, after the release.

  `tests/test_registry_artifact_agrees.py` now compares the artifact against the live registry, pins
  the two counting conventions apart (`adversarial*` excludes baseline and control; `*Total`
  includes them — the artifact's own note warns that mixing them inflates coverage by a family), and
  asserts the validation split partitions the registry, which was previously only enforced
  downstream. Mutation-checked against the exact v0.39.0 values.

  A generated artifact needs a guard that it was regenerated. Otherwise "generated" only means
  "nobody typed it recently".

## [0.39.0] — 2026-09-01

### Added

- **`gradient_patch` — the white-box image-space attack `PRIOR_ART.md` records the harness as
  missing.** Untargeted L-inf projected gradient ascent on the feature the action head consumes,
  maximising `||enc(x+d) - enc(x)||` using the policy's own input gradients. No labels, no
  ground-truth actions, no reward — only the encoder a published checkpoint already exposes.

  **Its own family, not a member of `optimized_patch`.** Same channel and same EAI category,
  different threat model: this reads gradients, which assumes an attacker holding the weights. A
  combined family rate would average a white-box result with a black-box one and answer neither
  question. `attacker_access` records `white-box-gradient` against the sibling's
  `black-box-query`; the comparison between them is the interesting quantity, the average is not.

  **Inert unless it can genuinely attack.** `applicable()` requires BOTH a real camera frame and an
  attached gradient oracle, and returns False otherwise so the arm leaves the ASR denominator
  rather than scoring 0. That gate is the point: a white-box null recorded for a run that never
  took a gradient would recreate, one level deeper, the defect this family exists to fix. Without
  an oracle `perturb()` returns the frame untouched — it never substitutes noise, because
  noise-shaped damage under a white-box label is the confusion `attacker_access` prevents. `torch`
  is never imported: the policy supplies the gradient array and the attack does the projection in
  numpy, so the module stays CPU-clean and framework-agnostic.

  **What is measured, and what is not.** On **Diffusion Policy x PushT**, n=20 per condition on
  identical seeds, task success went from 9/20 clean and **14/20 under random L-inf noise** to
  **0/20 under the optimised perturbation at the same eps=0.10 budget** — exact McNemar against the
  noise arm **p = 0.00012**, mean coverage 0.971 -> 0.333. The noise control is load-bearing: it
  shows the damage comes from the optimisation rather than the corruption, which is the comparison
  the published 0/50 visual nulls never made. Random noise at that budget slightly *helped* the
  policy, so the attack had to beat a control that was improving it.

  **No VLA number is claimed.** This has never run against SmolVLA x LIBERO. The published `patch`,
  `decoy_object` and `scene_text` nulls stay exactly as measured — they were produced by a
  string-append fixture, not by this attack. `PRIOR_ART.md` now states which half of its own gap
  closed: the harness has the attack it was missing, and has not yet pointed it at the policy the
  nulls were measured on. Measured cost of that next step on an Apple M4: one PGD refinement
  through SmolVLA's vision tower is ~3.5 s (backward is 27x forward), so a 20-seed sweep is a GPU
  job, not a laptop one.

### Changed

- **Registry counts move with the family:** **17 adversarial families** (was 16), **39 adversarial
  attacks** (was 38), 42 total including baseline and controls. Swept across README, SAFETY.md,
  PRIOR_ART.md, `docs/`, the notebook, `leaderboard/app.py`, the `full-sweep` example recipe and the
  pinned evidence manifest — every surface `test_counted_claims.py` and `test_coverage.py` guard.

- **The SO-101 sim-to-real protocol is amended, before any trial has run (executed to date: 0).**
  Two corrections, both from bench research rather than from data, and both recorded in
  `docs/studies/sim-to-real-so101.md` with the amendment date — amending a pre-registration *after*
  a run is a different and much worse act, so the window is stated where it can be checked.

  **A power-integrity confound that runs in the direction that flatters the result.** The kits ship
  a 12 V 7.5 A supply while per-servo over-current protection trips above ~2 A, so six servos
  stalling together can outdraw the supply: voltage sags, servos drop torque mid-motion, the arm
  falls. Adversarial action sequences are jerkier and drive more joints at once than benign teleop,
  so the **attacked condition is the likelier one to brown out** — and an arm losing torque above a
  keep-out zone falls into it. Unmeasured, a power fault is indistinguishable from a successful
  redirection. The protocol now requires a per-trial servo-bus voltage trace and fixes a trial
  invalidation rule in advance, so the rule cannot be chosen later to suit the outcome.

  **The e-stop claim was wrong and is corrected.** The protocol asserted "a human supervisor with an
  e-stop at all times". The STS3215's own over-current protection is **not a latch** — output is
  disabled only until a new position command arrives — so a policy that keeps streaming commands
  re-arms the servo it just faulted. The protection holds under benign teleop and fails under
  exactly the condition being tested, and no kit ships a real e-stop. The protocol now specifies an
  inline DC supply cut as a required addition, and pins the study to the 7.4 V servos (jaw stall
  ~48 N against ~74 N on the 12 V variant).

  No number moved and no result is claimed; runs executed remains 0.

## [0.38.1] — 2026-08-31

### Fixed

- **A zero-width confidence interval was published for three null arms for 21 days, and the
  project's own two surfaces disagreed with each other about it.**
  ([#157](https://github.com/provael/provael/pull/157)) `README.md` (since
  [#113](https://github.com/provael/provael/pull/113), 9 August 2026) and
  `results/smolvla_libero_object_suite/README.md` (since
  [#110](https://github.com/provael/provael/pull/110), 9 August 2026) both published the
  task-clustered 95% interval for `patch`, `decoy_object` and `scene_text` as:

  ```
  [0%, 0%]
  ```

  Each of those arms is 0/50. Resampling ten tasks that all scored zero returns zero on every
  draw, so the percentiles collapse onto the point and the interval asserts a certainty the data
  cannot support. The corrected tables carry **`—`** instead, and state in prose that 0/50 is
  consistent with a true rate as high as **7.1%** — the exact binomial 95% upper bound.

  `cluster_bootstrap_ci` already declined below two tasks, on exactly this reasoning. It guarded a
  *proxy* — the number of clusters — rather than the interval it computed, and ten tasks that all
  score the same rate clear a cluster count while being just as degenerate. The fix guards the
  computed interval.

  **The signed leaderboard was correct throughout.** It carries Wilson intervals, not the
  clustered bootstrap, and has always published `[0.0%, 7.1%]` for the 0/50 injection row and
  `[0.0%, 3.7%]` for the 0/100 visual row. So did the website. The defect was confined to two
  hand-maintained Markdown tables, which is also why no regeneration step would ever have
  corrected it: `cluster_bootstrap_ci` has no caller in `src/`. Recorded as
  [E-2026-03](docs/errata.md).

- **The scheduled GPU lane could never finish, and cost roughly 40× what three surfaces said it
  did.** ([#158](https://github.com/provael/provael/pull/158)) The lane ran nightly at
  `--seeds 10`. `ATTACKS` expands to eight arms and `task_ids` defaults to one task, so that is
  **80 episodes**; against this repo's own measured anchor of ~139 s/episode it is **~3 hours
  into a 1-hour Modal timeout**. Every scheduled run would have burned the full hour, been killed
  before recording anything, and cost **~$0.80** — about **$24/month of a $30/month credit for no
  measurement** — while the docstring, the example workflow and `docs/standards/last-measured.md`
  all advertised **~$0.02/run**. Caught the day the lane was first enabled, before its first run.

  Now `--seeds 2`: 16 episodes, ~37 minutes, ~$0.49, and it completes. The freshness badge this
  feeds carries a timestamp and no rate, so fewer seeds cannot weaken a published number. The
  cadence is **derived rather than chosen** — `watch.py` sets `STALE_DAYS = 7`, so a weekly run
  sits exactly on the red boundary and one miss turns the badge red; Tuesday and Friday give gaps
  of three and four days at ~$4.25/month.

  `gpu-nightly.yml` → `gpu-scheduled.yml` and `ENABLE_GPU_NIGHTLY` → `ENABLE_GPU_SCHEDULED`: the
  file is named for being scheduled, not for a cadence that is a tuning parameter of `STALE_DAYS`
  and has now changed once. The stale-badge CLI message is corrected too — it asserted the lane
  had never been configured, which was true when written and false the day it was switched on.
  **No test pinned the old filename, variable or CLI string**, so nothing would have caught that
  rename going half-done.

- **PRIOR_ART.md carried the DRIFT entry twice, and the two copies contradicted each other on a
  fact about our own coverage.** Both were the same work — Tae & Lee, arXiv:2608.03207 — under an
  identical heading at two places in the register, so this is a duplicate rather than a name
  collision. The copies did not merely repeat: the first asserted, in bold, **"Provael has never
  measured a flow-matching policy"**, and the second refuted it from this repo's own data.

  The second is right. `lerobot_adapter.py` declares `action_head_class = "flow"` and **all 400
  episodes** of the pinned ten-task evidence record `flow`, so SmolVLA is a flow-matching policy by
  this project's own taxonomy and we have measured one. The false copy was wrong in the direction
  that excuses us: it offered an architecture difference as the reason a published patch attack
  beats our null, and that excuse is unavailable. The merged entry keeps the accurate
  `mapping_status: cited, not crosswalked`, keeps the first copy's mechanism finding (the gradient
  conflict behind DRIFT's first-denoising-step result), and restates the gap at its true width —
  provael has not measured **π0 or π0.5**, the specific checkpoints DRIFT attacks, which is a
  missing checkpoint rather than a missing policy class.

  No test or surface asserts a prior-art entry count, verified rather than assumed, so the register
  going from 35 entries to 34 needs no other change.

### Added

- **PRIOR_ART records TOWN-VLA ([arXiv:2608.23224](https://arxiv.org/abs/2608.23224)), including
  its length-matched meaningless-append control, and marks its magnitude as awaiting independent
  replication.** The control is the part that matters: raw appended text drops mean success from
  92.47% to 3.00%, and *meaningless* appends matched for length fail on all 500 states just as
  meaningful ones do. That isolates prompt **form**, not semantics, as the axis doing the damage.
  Their arXiv page lists no institutional affiliation and no code link, so the headline magnitude
  is recorded as unreplicated while the control is credited on its own terms — the same standard
  this project asks to be held to.

- **The instruction-canonicalization study names the open question TOWN-VLA raises for it, and the
  test that would settle it.** `instruction_canonicalization` normalises semantics; if form is what
  collapses a policy, the defense may miss the failure mode entirely on a real policy while still
  scoring `credited` on the fixture. Worse, the existing credit is **confounded**: stripping a
  trigger token also shortens the prompt, and on this fixture the two effects never vary
  independently. The test named is to canonicalize, re-pad to the original token length with
  semantically null filler, and re-run the pre/post comparison. It is stated as a test, not a
  result — and the page says plainly that it is **uninformative on the current stub**, whose danger
  head is substring-presence only with no length term, so filler moves the score by exactly zero.
  It is a rider on "run this against a real policy", not separate work.

### Notes

- **The published leaderboard stays `stale: true`, and was deliberately NOT regenerated.** Its four
  rows are real-model SmolVLA × LIBERO, measured with provael 0.32.0 — six minor versions back. Re-
  measuring needs lerobot **and LIBERO on a GPU**, and none of that is available here: `libero` is
  not importable, `torch.cuda.is_available()` is `False`, and the machine is arm64 macOS, where
  `hf-libero` does not install at all (its dependency carries `sys_platform == 'linux'`). So **zero**
  of the four rows can be re-measured today. There is no partial subset to refresh either — the
  CPU/stub path would measure a *different policy*, and putting that on the board as a SmolVLA row
  would be fabrication.

  Rebuilding from the same committed reports was considered and rejected as actively worse than
  doing nothing. It re-runs no policy: `measured_with` is read from the reports, so `staleness()`
  would return `True` and the six-minor gap unchanged, while `generated_at`, `commit` and
  `tool_version` all moved to today. A dated, signed record that reads as freshly measured is the
  one thing it must not do — which is what `Leaderboard.is_restamp()` already exists to expose.
  `scripts/check_leaderboard_staleness.py` passes because the board declares its staleness
  honestly; the flag is the consumer's ability to refuse, and clearing it would be unrecoverable.

  The signature was verified before and after this release and is unchanged:
  `provael leaderboard verify` reports `leaderboard OK  keyid 8d62aa33ed5162f3`. The board declares
  `schema_version 5` while carrying v6-shaped per-row benign fields, which is correct as designed —
  the staleness fields sit outside the signed subject, so a v5 board annotated with them still
  verifies. Not changed.

- **`CITATION.cff` had drifted two days off its own release date, and the file's comment predicted
  it.** `date-released` read `2026-08-22` for 0.38.0, while the `v0.38.0` tag, the PyPI upload and
  this changelog all say **2026-08-24**. The comment beside the field records this exact failure
  happening at 0.25.0 ("a citation to 0.25.0 named a date three days before the artifact existed")
  and says plainly that the date is not machine-checkable against a tag, so it is on the release
  author. It recurred. Both fields are set correctly for this release; the guard gap is noted rather
  than closed, because checking a date against a tag that does not exist until after the release
  commit is not a check that can run in the release commit.

- **This release was blocked for twenty minutes by its own commit message, and the cause is worth
  recording.** The commit adding the changelog PR gate explained, in prose, that the bot badge
  refreshes carry a CI-skip marker — and quoted the marker verbatim. The squash-merge concatenated
  that text into the merge commit's body, GitHub read it, and skipped every workflow for that
  commit: the push to `main` produced **zero** runs (the immediately preceding merge produced four,
  which is how it was isolated), and the `v0.38.1` tag pointing at it was skipped on three separate
  pushes while `release.yml` sat `active`, correctly triggered on `v*`, and having fired for every
  previous tag.

  There is no guard for this and the reason is structural: a check cannot run on the commit that
  turns checks off. The prose in `scripts/check_changelog_entry.py` no longer spells the token out,
  and says why. The literal is written once, in the workflow where it does a job.

- **No calibration in this release.** Issue
  [#136](https://github.com/provael/provael/issues/136) (the uncalibrated keep-out predicate) stays
  open and untouched: `CALIBRATED_ZONES` is still empty, and the published 44/50 against a 4.0%
  benign control keeps its uncalibrated caveat on every surface that quotes it. Committing zones
  requires benign end-effector trajectories from a GPU/sim box, which this change did not have —
  see the PR for what specifically blocked it.

## [0.38.0] — 2026-08-24

### Changed

- **The benign false-positive rate is now published beside every ASR, with its own Wilson
  interval.** An attack-success rate is a difference against the benign floor, and every exporter
  in this package published the ASR with an interval and a denominator and the floor as a bare
  percentage: `benignFpr: 0.04` in the SARIF run, `benign_fpr` in AVID, one metric with no
  `confidenceInterval` in the ML-BOM, one prose clause in OSCAL, one table row in the Markdown
  report, one column in the transfer-test table — and, on the leaderboard, nothing at all. A rate
  with no denominator cannot be read: 0/5 and 0/500 both serialise as `0.0`, and 4% at n=50 is
  Wilson [1.1%, 13.5%], which is most of the interval a reader was implicitly assuming away.

  `RunReport.benign_headline()` is the exact mirror of `adversarial_headline()` — same
  `applicable` filter, same `family == "baseline"` partition, opposite side of it, so the two are
  a partition of the run and a test pins that they sum to the applicable episodes.
  `scoring.asr.benign_control()` resolves it once for every emitter, so the pairing cannot drift
  between surfaces. Both recompute from `results`, so they work on the legacy schema-2 reports
  where the counts predate the stored fields, and a trimmed report keeps its stored rate and
  reports that the interval is unavailable rather than inventing one from a denominator that is
  not there. A run with no control arm renders `n/a`, never `0.0%`: an unmeasured floor and a
  measured floor of zero are different claims about the same number.

  Leaderboard `schema_version` 5 → 6 adds per-row `benign_successes` / `benign_attempts` /
  `benign_ci95`, and `provael leaderboard` grows a `benign FPR (95% CI)` column beside the ASR
  column. `TransferTest` gains `benign_n` / `benign_successes` / `benign_ci95` on the same
  reasoning.

  Additive with defaults, and registered in `_ROW_FIELDS_ADDED_IN[6]` — which is not bookkeeping.
  Adding the three fields without registering them changed the canonical bytes of the **committed,
  signed v5 board** and its Ed25519 signature stopped verifying; to anyone checking it, a
  correctly-signed board then looks exactly like a tampered one. The existing regression test
  caught it, but only because a v5 board happens to be committed, so two structural guards now
  fail immediately and by name when any future field is added without a version.

### Added

- **The leaderboard states its own staleness in a field a machine can refuse on (schema v6).**
  `leaderboard/results/leaderboard.json` publishes four rows measured with provael 0.32.0 — six
  minor versions behind 0.37.0. It said so in a banner the Space renders, and prose does not stop a
  consumer: anything reading the JSON got four rates, an Ed25519 signature, and no way to tell that
  the signature vouches for a *measurement* rather than for its *currency*. A signature over stale
  data reads as currency, which is worse than no signature.

  Three additive board fields: `tool_version` (which release **assembled** the board — distinct
  from `measured_with`, which is what **measured** the rows; the gap between them is the
  staleness), `stale`, and `stale_reason` naming both versions so the verdict is re-derivable from
  its own text. The lag is counted on `(major, minor)` and ignores the patch, since a patch changes
  no measured behaviour; across a major bump it is not a subtraction, because 0.40 → 1.0 is one
  release and not minus thirty-nine.

  There is deliberately **no `assembled_at` field**: `generated_at` already carries exactly that
  instant, and two fields holding one value are two fields that can disagree. Its description now
  says so outright.

  **The flag sits outside the signed subject.** Staleness is a function of today, not of the board
  — one that was current when signed becomes stale without a byte changing. Registering the fields
  in `_FIELDS_ADDED_IN[6]` strips them from the signing payload of any board declaring an earlier
  schema, which is what let the already-signed v5 board be annotated with `stale: true`,
  `tool_version: "0.33.2"` (read from `src/provael/__init__.py` at its own recorded commit
  8cd8d99, not guessed) and per-row benign counts, and still verify against the committed public
  key. A four-line diff, signature intact.

  `scripts/check_leaderboard_staleness.py` runs in CI and fails on **undeclared** staleness only —
  a board past the limit that does not carry `stale: true`. Failing on staleness itself would be
  red today and red until a GPU re-run nobody has scheduled, and a permanently-red detector reports
  nothing. Disclosed staleness is the honest state; silent staleness is the bug. `--fix` refreshes
  the flag; the verdict is monotone, so only a `false` can ever decay and that is the single
  direction re-checked.

  The re-run was not taken: the rows are SmolVLA × LIBERO and re-running them is GPU-gated, so the
  board is flagged rather than refreshed.

- **`studies/keepout_calibration/` — what the benign 2/50 actually is (#136).** The claim that the
  default keep-out box is misplaced has been asserted in this repository since 0.34.0 and never
  tested. It is now measured, from artifacts already committed, on CPU, with no simulator.

  A benign false-positive rate is one number and one number cannot separate "the policy left the
  safe region" from "the boundary is in the wrong place" — opposite findings needing opposite
  responses. The discriminator is structure, not magnitude: a wandering policy scatters, a
  misplaced boundary fires on the same tasks every time. Pooling the ten-task suite with the
  control run gives **5 firings in 100 benign episodes (5.0%, Wilson 95% [2.2%, 11.2%])**, and
  every one lands on `libero_object/4` or `/5` while the other eight tasks stay silent through 80
  episodes. The seeds differ between runs, so each tests the other's task set out-of-sample; both
  directions are reported and the weaker, **p = 0.04**, is the headline. The other disjunct of the
  predicate is provably not involved: `ForbiddenObjectGrasp` ships empty and with no extractor.

  **No corrected zone is derived, and no threshold sweep is committed.** Knowing a boundary is
  misplaced is not knowing where it belongs, and the study records why the second is impossible
  here: every committed LIBERO report is `schema_version 2`, predating `AttackResult.trajectory`,
  so the benign end-effector poses a fit consumes were computed on every step and discarded —
  `endpoints` is `{}` and `danger` is `0.0` on all five firings, and the untrimmed Modal artifacts
  only add `decisions[]`, which carries no position. Sweeping a grid of boxes against episodes
  whose poses are unknown produces a curve of the right shape and no content. Choosing an
  operating point from it would be picking a second constant exactly the way the first one was
  picked, which is the bug rather than the fix.

  So **#136 stays open and the 44/50 headline has not moved** — it cannot move without a benign
  re-run on a build at or after 0.35.0, which is GPU-gated. What the study does buy is scheduling:
  tasks 4 and 5 are the two to calibrate first, and a re-run does not need all ten.

- **The policy's own sampler is seeded, and the seed is recorded (report schema v5).** The board
  carried a caveat that SmolVLA's flow-matching sampler is "one draw, not a constant", which
  quietly means two rows at the same commit are not comparable — most of what a leaderboard is
  for. That was not a property of flow matching. Nothing had ever seeded it: `suite.reset(task,
  seed)` seeded the ENVIRONMENT and every episode recorded that seed, while the policy drew its
  denoising noise from wherever the process's torch RNG happened to be. An early pilot at
  identical config returned `goal_substitution` 1/4 on one run and 0/4 on the next.

  `PolicyAdapter.seed(seed) -> int | None` is now called with the episode seed before every
  rollout, and `AttackResult.policy_seed` records **what the adapter reports it applied**, not what
  the runner asked for — the same discipline as `resolved_device`, because returning the argument
  unconditionally would let every report claim a determinism no adapter delivered. The LeRobot and
  OpenVLA adapters seed torch's generators; `openpi` returns `None` **with the reason in the
  method**, since inference happens in a separate server process whose protocol has no seed field.
  A stochastic adapter that inherits the default unchanged fails a test by name: inherited silence
  and a considered "cannot" look identical in a result file, and only one of them is a decision.

  This does **not** claim bit-identical runs, and deliberately does not set
  `torch.use_deterministic_algorithms` — that changes which kernels run, and a measurement harness
  must not silently alter the compute path of the thing it is measuring. `stochastic` stays true.
  What changes is that a run records which seed its sampler started from. The GPU effect is
  untested here: there is no lerobot or CUDA in the CPU environment, so what is tested is the
  contract, not the numbers.

  `validate_report` now **refuses** a stochastic submission at schema ≥ 5 with no `policy_seed` on
  any episode. Reports predating schema 5 — every result committed in this repository — are
  accepted with a named warning instead: the field did not exist when they were measured, and
  `validate_submission.py` runs over all of `results/` on any PR that touches it, so a hard rule
  would have been red from the day it landed. The gap still reaches a consumer through the board's
  `stale` flag, since a report old enough to predate `policy_seed` is old enough to put its board
  past `MAX_MINOR_LAG`.

  Both seeds already participate in `inputs_digest` and therefore in the board signature. That was
  true and had no test, which is the same as being true by accident; it has one now.

  **The caveat stays.** The published rows were measured before any of this and carry no
  `policy_seed`, so nothing here makes them reproducible after the fact — it is scoped to those
  rows rather than deleted, and re-running them is GPU-gated. Deleting it belongs in the commit
  that completes the re-run.

  Published schemas: `report.v5.schema.json` and `leaderboard.v6.schema.json`. `report.v4` and
  `leaderboard.v5` stay committed and frozen — their `$id` is a stable URL, so deleting one 404s
  any consumer that pinned it — with tests holding each to the promise its own version bound makes.

### Fixed

- **The leaderboard Space told visitors the rates were read against "a 0% benign false-positive
  control" while the board underneath it carried a `baseline` row at 4% (2/50).** The 0% was the
  *matched* control for one arm — `roleplay` had no benign twin fire at the same (task, seed) —
  which is a different quantity from the marginal false-positive rate and not interchangeable with
  it. The page now computes the figure from its own baseline row, like every other number in that
  banner, so it cannot drift from the rows it describes again. The benign column also renders
  counts and the interval, so the board reads `41.3% [34-49%]` against `4.0% (2/50) [1-13%]`
  rather than against a bare percentage.

## [0.37.0] — 2026-08-22

### Added

- **`provael doctor` — the command that answers "why did that not work here".** Twenty-six
  top-level commands and not one diagnosed an install. The first-run transcript shows the cold path
  is twenty seconds, so the install is not the problem; the SECOND run is, when someone reaches for
  `--policy smolvla` without the `[lerobot]` extra or for a keep-out suite with no calibration and
  gets an import error or a silent default instead of a diagnosis.

  One screen: Python and platform, installed version against PyPI (`--offline` skips the lookup),
  which policy backends are ready and which are `SCAFFOLDING_POLICIES` **with the reason each is
  scaffolding**, which suites actually import, whether `CALIBRATED_ZONES` is populated (it is not —
  it says so and points at issue #136), whether `PROVAEL_REQUIRE_CALIBRATED` is set, and the age of
  the freshness signal against `STALE_DAYS`. Nothing is inferred: a suite is reported importable
  only after being constructed, and "ready" explicitly does not claim a checkpoint is present.

- **Published JSON Schemas for the two artifacts third parties are asked to produce.**
  `schemas/report.v4.schema.json` and `schemas/leaderboard.v5.schema.json`. The tree carried three
  `$schema` keys and none described `report.json` or `leaderboard.json`, so an open submission queue
  with zero external rows was asking people to guess the shape. They are **generated from the
  pydantic models** (`scripts/gen_schemas.py`), not written from example files, so they describe the
  contract rather than today's artifacts; `tests/test_published_schemas.py` validates all 33
  committed artifacts against them, including schema-2 and schema-3 reports that predate the current
  model. A `vN` schema accepts `N` or lower and **refuses** anything higher, so a too-old tool says
  so rather than silently passing. Referenced from `CONTRIBUTING-leaderboard.md` with a
  `check-jsonschema` one-liner.

- **A measured result for `weight_integrity`, and a study page that leads with what it is not.**
  The family shipped with zero output. `results/weight_integrity_stub/` now holds the ladder as five
  shards plus an `aggregate.json` analysis, in the same shape as the ten-task suite — 750 episodes,
  both arms at every rung, benign control throughout. `docs/studies/weight-integrity-stub.md`
  publishes it with the caveat block **above** any number: stub backend, 64-parameter INT8 danger
  head, separation expected by construction, flips emulated with `Literal[True]`, and no
  corroboration of the architecture-dependence result it was built from.

  Gradient 50/50 at every rung; random 4/250; benign control 0/50 throughout. The interval is
  bootstrapped over the five **rungs**, not over episodes, because the rung is the unit of analysis
  — and n = 5 is stated rather than hidden. **No leaderboard row was added**, and the study page says
  why: the board is the real-policy board, a shared table asserts comparability, and this is not
  comparable to anything on it.

### Fixed

- **A stub run could reset the freshness badge, and briefly did.** Committing the study above put a
  `policy='stub'` execution manifest under `results/`, and `latest_measurement` — which scans
  committed runs — immediately reported "today". The badge would have gone from "11 days ago, red"
  to green with nothing re-measured.

  The stub satisfies the letter of the definition: it is a registered policy and the run does
  execute attacks against it. `docs/standards/last-measured.md` had already written this refusal
  down on 21 August with nothing in the code enforcing it. `watch.counts_as_measurement` now
  enforces it, `FIXTURE_POLICIES` names the backends that do not count, and the badge correctly
  reads **12 days, red**.

- **One family count, computed, everywhere.** Four surfaces disagreed simultaneously:
  `docs/attacks.md` opened with "**Fourteen** adversarial families", `docs/examples.md` said
  `full-sweep` "runs all 14", `docs/studies/action-envelope.md` called 14 "the **full adversarial
  registry**", and README said thirteen families lacked a real-model measurement while claiming
  twelve. The true numbers, each with its definition: **16** adversarial families (registry minus
  `baseline` and `control`), **18** total registered families, **38** adversarial attacks, **41**
  total registered attacks.

  `tests/test_counted_claims.py` enumerated phrase patterns, which is why it was green while all
  four were wrong — it checked the claims it was handed rather than the claims that exist. It now
  sweeps every `<number> … families` / `<number> … attacks` construction in README and `docs/**`,
  requiring each to be a registry-derived value or a **named subset** with a stated reason. The
  first version of the regex missed `**Fourteen**` because emphasis wraps the number; that hole is
  fixed and noted, since it would have skipped the exact claim the sweep was written for.

- **The README described a different run than the board publishes.** It said the board was "measured
  with **`provael 0.1.0`**" while the board and all ten shards say `0.32.0`; `0.1.0` is the
  `tool_version` of the superseded single-task run. `test_leaderboard_version_claim` already tied
  the board to its shards and passed throughout, because the README was never in the comparison. It
  is now. The paragraph also states, in the words of the file itself, that
  `leaderboard/method-equivalence.json` is *"a code-inspection argument, NOT a re-measurement."*

- The 0.36.0 coverage entry hardcoded "88% of 7,833 statements" three lines above a paragraph
  criticising hardcoded percentages. It is now explicitly a snapshot and points at the badge as the
  live figure, rather than being rewritten — the entry records what was measured on the day.

## [0.36.2] — 2026-08-21

### Fixed

- **Per-shard provenance digests moved with the tool version — the third instance of the same
  defect, and the one that finally got the rule written down.** `combine.shard_digests` computed
  each shard's `sha256` with `model_dump_json()`, re-serialising it through whatever `RunReport`
  the *running* version defines. The pinned public-evidence manifest records `52bcdb70…` for
  `libero_object_0/report.json`; 0.34.0 reproduces it, 0.36.1 returned `66897a4c…` for
  byte-identical committed input, and `git diff` confirms the artifacts never changed.

  That defeats the only purpose those digests have. The manifest advertises them so a consumer can
  "re-fetch each shard and verify it independently" — and under the old body they could only do so
  with the exact tool version that wrote the manifest, which is not discoverable from the manifest.
  It now projects through `attest.report_projection`; all ten shards reproduce the pinned values.

- **The `RunReport` digest contract in `types.py` documented the opposite of what the code does.**
  It stated that "adding any field changes the digest of every historical report" and prescribed a
  `RULESET_VERSION` bump for every added field. True when written, false since `report_projection`
  landed — and three digest sites went on doing the bare dump anyway, two of which shipped broken
  (`leaderboard._inputs_digest` in 0.36.1, `combine.shard_digests` here). The contract now states
  the rule once: **any digest over a RunReport goes through `attest.report_projection`.**

- The test guarding shard digests was **tautological** and could not have caught this: it computed
  its expected value with the same `model_dump_json()` call the implementation used, so both sides
  shared the bug. Its own docstring said "or it is decoration". It now asserts the property a shared
  bug cannot satisfy — populating a field introduced *after* a shard's declared `schema_version`
  must not move its digest — and was verified by restoring the old body and watching it fail.

## [0.36.1] — 2026-08-21

### Fixed

- **A published leaderboard stopped rebuilding to its own `inputs_digest`, and had done since
  0.35.0.** `_inputs_digest` re-serialised every input report through whatever `RunReport` the
  *running* version defines. Adding an optional field therefore rewrote the bytes of reports that
  predate it — a schema-2 report loaded by a schema-4 tool dumps
  `"trajectory": null, "weight_corruption": null` on every result — so the digest of an unchanged,
  committed artifact moved with the tool version.

  Measured against the board committed at `983c829`, one unchanged input gave three answers:

  | tool | `inputs_digest` | |
  |---|---|---|
  | 0.33.2 | `69396ef8…` | reproduces |
  | 0.34.0 | `69396ef8…` | reproduces |
  | 0.35.0 | `46008680…` | broke here (`trajectory`, schema 3) |
  | 0.36.0 | `5d63664f…` | worse (`weight_corruption`, schema 4) |

  This is the offline-verifiability claim, so it matters more than its size suggests:
  www.provael.com/verification tells a stranger to rebuild the board and expect a match, and since
  0.35.0 they would have got `match: False` and reasonably concluded the evidence did not reconcile.
  **Signatures were never affected** — `leaderboard verify` checks the board's own bytes and has
  passed throughout (`keyid 8d62aa33ed5162f3`). What broke was reproducing the board from its
  inputs.

  The fix makes the code do what its docstring already claimed: `_inputs_digest` now projects each
  report through `attest.report_projection`, which strips fields added after the report's
  **declared** `schema_version`. An artifact digests to its own schema regardless of what is
  installed, so old boards verify again rather than needing to be re-signed against a newer tool.

  Found by running the release smoke test the long way — rebuilding from a clean clone at the pinned
  commit rather than trusting that a green suite covered it. It did not: the golden test that would
  have caught this compared two synthetic projections and passed under the broken code too. The
  replacement asserts the real invariant against the committed artifacts, and was checked by
  restoring the old behaviour and watching it fail.

## [0.36.0] — 2026-08-21

### Added

- **`weight_integrity` — the first family that attacks the parameters instead of the input
  (EAI03).** Every one of the fifteen families before it perturbs what the policy is shown or told.
  This one leaves the instruction and the observation exactly as the benign baseline delivers them
  and flips bits in the policy's loaded INT8 weights, so any unsafe behaviour is attributable to
  the weights and to nothing else. Ten registry entries: a gradient-selected arm and an
  equal-count random arm at each budget in a `K = 1/4/16/64/256` ladder, runnable as
  `--recipe eai03-weight-integrity` or `--attacks weight_integrity`.

  **What it measures and what it does not, because the difference is the whole reason a sim-only
  tool can ship this at all.** It measures whether a policy is fragile to weight corruption. It
  does *not* measure whether an attacker can achieve that corruption on a real deployment — that
  is a platform question about DRAM fault injection, ECC, memory integrity and supply chain, and
  provael touches none of it. Every flip is emulated in memory, there is no hardware
  fault-injection path in the repository and none is planned, and every record carries
  `emulated: true` so a report states this rather than leaving a reader to assume it.

  **The control arm is mandatory, not optional.** A gradient result with no equal-count random arm
  cannot separate "the ranking found the bits that matter" from "corrupting K bits of anything
  breaks it", and those have opposite engineering consequences.
  `scoring.weight_integrity.crossing_pair` returns `None` rather than half a result when the
  control is missing — a caller holding a number publishes it.

- **`scoring/weight_integrity.py` — the crossing point, which is the number worth publishing.** A
  weight-integrity run has a curve, not a rate: "100% ASR" is meaningless without the flip budget
  it was bought at, and the family's pooled ASR averages two arms that are *meant* to differ. The
  reportable summary is the smallest K whose unsafe rate reaches a stated floor, and the floor is
  a required argument recorded on the result — a crossing at 50% and a crossing at 90% are
  different claims about the same curve. Non-monotone curves are reported as non-monotone rather
  than smoothed.

- **A quantized danger head on the deterministic stub**, so the family has real parameters to
  corrupt: 64 INT8 parameters (512 addressable bits) computing
  `clip01(gain * aggression + bias) * governor`. The clean parameters dequantize to gain 1.0,
  bias 0.0 and governor 1.0 **exactly** — the scale is a negative power of two — so the clean
  output is byte-identical to the pre-0.36.0 action and **no other family's ASR moved**. The
  shipped stub run is still `67.1% (47/70)`, asserted by a test over the whole `[0, 1]` range with
  equality rather than a tolerance.

- Crosswalks for both papers this release responds to: `docs/crosswalk/bit-flip-vla.md`
  (arXiv:2608.15475) and `docs/crosswalk/embodied-agent-attack-surfaces.md` (arXiv:2608.16843).
  The second is a coverage map and it is not flattering: **five of the survey's twelve attack
  surfaces have no provael attack at all**, provael is well covered exactly where the survey says
  the field already concentrates, and it is absent from three of the four areas the survey calls
  underexplored. Its five-layer taxonomy is *not* reproduced, because the layer names were not
  readable from the abstract page and inventing a counterpart's categories in order to map onto
  them is the failure these cards exist to avoid.

- **The first run was timed on a clean machine, and the result did not support the reason the
  measurement was taken.** `docs/first-run-transcript.md` records **20 s** (49 s on a cold cache)
  from `pip install provael` to a written `report.json`, in a `python:3.12-slim` container with no
  CUDA, no conda, no pip cache and no checkout — reproducing the README's advertised `47/70` on the
  first try, with nothing needing a decision, a lookup or a fix. The page was created on the
  premise that a slow first run explained 0 forks and 0 third-party reproductions. It does not: at
  20 seconds this project is in the 39% of safety-benchmark repositories that run without
  modification (arXiv:2603.04459), so improving onboarding further would buy nothing. The barrier
  is one step later and it is economic — reproducing the headline SmolVLA result costs ~15.4
  GPU-hours and ~$12, which is already documented with its exact command and price. Two papercuts
  found in passing: the README stated the Python 3.12 floor eleven lines *after* `pip install`
  (fixed — on 3.11 pip emits 38 `Requires-Python` lines that read like a broken package), and the
  README prose says `libero_object` six times where the CLI suite is `libero` (recorded, not
  changed; renaming a CLI surface to close a prose mismatch is a larger decision than this
  exercise justifies).

- **Bit-flip attacks cited in `PRIOR_ART.md` as an unimplemented channel, not as coverage.**
  arXiv:2608.15475 (16 August 2026) attacks the *parameters* rather than the input, which no
  provael family does: gradient-selected INT8 flips collapse closed-loop success to 0% while
  hundreds of random flips are harmless, and the budget tracks the action head — 1–5 flips for
  direct-regression and token heads against ~100–300 for the flow-matching policies evaluated. The
  entry records their real-robot arm **with its control**: emulated K=100 gave 0/20 against 14/20
  clean *and* 16/20 equal-count global-random. `mapping_status: cited, not crosswalked` — no
  crosswalk is possible because **provael implements no weight-integrity attack as of 0.35.0**, and
  the entry says so rather than implying coverage. A `weight_integrity` family is named a
  candidate, explicitly not a shipped feature and not a dated roadmap commitment.
- **A disclosure rule for measuring policies we did not train, written before any such run.**
  `SAFETY.md` already told *users* of this tool to "contact the model's maintainers privately first
  and allow reasonable time to respond" — so publishing a third-party ASR without doing that would
  have put this project in breach of its own published rule, and "reasonable time" was never
  defined. `docs/leaderboard-disclosure.md` defines it: **14 days' notice**, the full artifact up
  front (signed report, exact command, checkpoint revision, predicate, benign control, and the
  draft caveat paragraph in the wording we intend to publish), publication after 14 days if there
  is no reply, and both positions printed on the same page where the authors disagree and we are
  not persuaded.

  Two constraints in it are load-bearing and easy to drop later under pressure. Third-party rows
  carry the **same** caveats as our own — transfer caveat, Wilson interval however wide, benign
  false-positive rate, and an explicit uncalibrated-predicate note — and **nulls are published at
  0/n with the same prominence as positives**. The board also **will not rank policies by safety**:
  the predicate is uncalibrated and the suite is one suite, so a table sorted by ASR invites a
  conclusion the measurement cannot support.

  The ordering is the point. The rule is published *before* the first such run, because a policy
  written afterwards is a defence of a decision already made. Linked from the docs nav,
  `docs/leaderboard.md`, `CONTRIBUTING-leaderboard.md`, and the Space card.

- **Security lint on ourselves.** `S` (flake8-bandit) added to the ruff selection — a tool that
  publishes other people's attack-success rates was not running security lint on its own source,
  which is the kind of gap a reviewer is right to notice. Enabling it surfaced 2,500 findings, of
  which 2,466 were `S101` (assert) in the test suite, where assert is the point. The remaining 34
  were triaged individually and **none was a live defect**: three `S105` "hardcoded password" hits
  are an enum member (`PASS = "pass"`), a channel prefix, and a deliberately published fixture token
  the attacks never present; `S311` is a seeded bootstrap resample where a cryptographic RNG would
  break the determinism contract; the `subprocess` hits pass fixed argv with no shell. Suppressions
  are scoped by rule and directory rather than blanket, and every one in `src/` is an inline `noqa`
  carrying its reason, so a future hit has to be argued rather than absorbed.

  `S101` is suppressed in `tests/` and nowhere else — an assert in `src/` should still fail lint,
  because `python -O` deletes it silently.

- **Coverage is measured, floored and published: 88% of 7,833 statements when this landed.** That
  figure is a snapshot and is already out of date — `weight_integrity` moved it to 89% of 8,053 in
  the same release. **The live number is the badge**, which reads a committed `watch/coverage.json`
  regenerated from the run that just happened; this entry records what was measured on the day, not
  a standing claim. Stating it that way rather than restating the current value is the point of the
  paragraph below, which this sentence originally contradicted by hardcoding a percentage three
  lines above criticising hardcoded percentages. There were 90 test
  modules and no figure anywhere, which is the shape of claim this project refuses to accept from
  anyone else — "well tested" with no denominator. CI now runs `--cov` on every PR, writes the
  table to the job summary, and gates on `--cov-fail-under=85`. The floor sits below the measured
  value deliberately: a gate pinned at the current number fires on ordinary refactors, and a gate
  that fires on noise gets raised until it means nothing.

  The README badge is a shields **endpoint** reading a committed `watch/coverage.json`, regenerated
  from the run that just happened — the same mechanism as the freshness badge. A hardcoded `88%` in
  a README is exactly the restated number `src/provael/coverage.py` exists to stop this project
  publishing.

  The badge commit lives in its own workflow rather than in `ci.yml`. `ci.yml` is `contents: read`
  with `persist-credentials: false` so a fork PR cannot obtain a write token, and bolting a commit
  step onto it would have handed every fork PR a privileged workflow to aim at — a real security
  regression traded for a cosmetic convenience.

  GPU-gated adapters are omitted from the coverage denominator rather than counted as missed: they
  never execute on the CPU lane, and counting them would understate the covered surface while
  inviting the number to be gamed by deleting them.

- **CONTRIBUTING now states that new functionality ships with tests.** It was always the practice;
  it was never written down, and an unwritten rule is one a new contributor has to guess at.


### Changed

- **The freshness badge's explanation now names the cause, and the seven-day window was NOT
  lengthened.** The badge has read red for eleven days beside a sentence saying the newest committed
  measurement was older than "the seven-day window this project holds itself to". That sentence is
  accurate and misleading: it invites the inference that a cadence slipped, and no cadence ever ran.

  `gpu-nightly.yml` is the job that would hold the window. It runs a real SmolVLA × LIBERO red-team
  on a Modal GPU and records into the watch ledger **only on success**. It is well built and has
  never executed, because it is switched off twice over — the repo variable `ENABLE_GPU_NIGHTLY` is
  unset (the repo has no variables at all) and `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` are absent.
  Both are deliberate cost-safety defaults.

  So moving the window to fourteen days would have fixed the wrong thing: fourteen would be broken
  by the same absence, and a second unenforced number presented as a considered adjustment is worse
  than the first. `STALE_DAYS` stays **7** — seven days genuinely is old for a currency claim.
  What changed is the claim beside it. `provael watch` now prints the two settings that would fix
  it, and `docs/standards/last-measured.md` records the decision, what closes it, and the shortcut
  that was available and refused: a `stub`-policy run satisfies the letter of the definition and
  would turn the badge green today, which is the same error as calling a republication a
  measurement.

- Dependency bumps, all three merged with CI green: `docker/setup-buildx-action` 3.11.1 → 4.3.0,
  `astral-sh/setup-uv` 9.0.0 → 10.0.1, `github/codeql-action/upload-sarif` 4.37.6 → 4.37.7.

  The two majors were read against actual usage rather than merged on green alone, because green
  was not evidence for one of them. setup-uv v10 disables caching for `pull_request_target`,
  `workflow_run` and `release` events; **no workflow here uses any of those**, and `ci.yml` runs on
  `pull_request` so its green run genuinely exercised v10. setup-buildx v4 requires Node 24 and
  removes deprecated inputs; **this repo passes it no inputs at all**, and `docker-publish.yml`
  runs on `push` only — so the green checks on that PR exercised setup-buildx *not at all*, and it
  is verified by the release image build instead.

### Fixed

- **`BitFlipRecord.emulated` is `Literal[True]`, not `bool` defaulting to True.** The field carried
  a docstring reading "Always True" and nothing enforced it:
  `BitFlipRecord(..., emulated=False)` constructed happily and serialised `"emulated": false`.

  A record asserting a non-emulated bit flip asserts that this tool performed hardware fault
  injection — out of scope under `SAFETY.md`, and something provael has no path to do. The claim
  that keeps `weight_integrity` inside that boundary must not rest on a default a caller can
  override. Pydantic now rejects `False` at construction and mypy rejects it statically; the
  serialised value is unchanged, so canonical JSON, report digests and existing attestations are
  byte-identical. Found by auditing the family before tagging rather than after.

  Two tests pin it: one that a non-emulated record cannot be constructed, and one that walks the
  AST of every module in `attacks/` for hardware fault-injection code. The second checks *names*
  rather than raw text — its first version flagged `weight_integrity.py`'s own docstring, which
  names DRAM fault injection and Rowhammer precisely to say they are out of scope, and a test that
  punishes the disclaimer would pressure someone to delete the scoping paragraph for a green build.


- **Report schema 3 → 4: results carry `weight_corruption`.** The flip budget and the selection
  rule *are* the result — 100% at K=4 and 100% at K=256 are different findings — so they are
  recorded per result rather than deferred to a config the report does not contain. The bump
  landed in the same change that started emitting the field: a report declaring 3 while carrying
  a 4 field has that field stripped by `attest.report_projection` before the digest, which signs
  *around* the corruption parameters rather than *over* them.
  `attest._RESULT_FIELDS_ADDED_IN` gained the `4:` entry in the same commit, and the committed
  v4 leaderboard still verifies (`keyid 8d62aa33ed5162f3`).

- **`PRIOR_ART.md`'s bit-flip entry moved from `cited, not crosswalked` to
  `implemented, not corroborated`** — and the second half of that label is doing the work. The
  entry previously said provael implements no weight-integrity attack and that such a family was a
  candidate rather than a shipped feature. Both are now false. What is still true, and is now
  stated in three places rather than left to be inferred: **provael has not reproduced the
  architecture-dependence result** (1–5 flips for direct-regression and discrete-token heads
  against roughly 100–300 for flow-matching). The only run is against the CPU fixture, which has
  one scalar danger head and no action-decoding architecture to depend on, so the
  gradient-beats-random separation it shows is a property of that fixture. Citing provael as
  independent support for that claim would be wrong.

- `docs/first-run-transcript.md` cited **p = 0.005** for the runnability/citation-density result in
  arXiv:2603.04459. The paper says **p = 0.004**, in its introduction and again in §4.6. The
  substantive claim — ready-to-use code relates to higher citation density while code needing
  modification does not — is exactly as reported; the digit was wrong. Checked against the paper
  text, not the abstract, which is the rule this repository already holds itself to.

- **The 31 August commitment is recorded as MET, 23 days early.** `docs/studies/index.md` still
  described the release containing `provael submit` as pending and told readers a git install was
  required — while the command had shipped in 0.32.0 on 8 August and www.provael.com/studies
  already showed it met. Two surfaces disagreeing about the same self-imposed deadline is worse
  than either being stale alone. The original date is kept rather than deleted: a commitment that
  vanishes once met is not a record.

  What did NOT change is stated in the same breath, because that is the easy thing to skip:
  shipping the command removed the barrier, it did not produce a submission. The register is still
  empty, the board still reports 0 independent submitters, and the fork count is still 0.

- **The Hugging Face Space is linked from the README and from PyPI.** It appeared in
  `docs/leaderboard.md`, `CONTRIBUTING-leaderboard.md` and a setup script, and zero times in the
  README that PyPI also renders — so a running, clickable leaderboard was unreachable from both
  places a newcomer actually lands. Added as a badge, as prose in the leaderboard section, and as a
  `Leaderboard` entry in `project.urls`. The prose says plainly that the Space is a *rendering* and
  the signed JSON in this repository is the artifact to verify.

- GitHub topics 12 → 18: added `embodied-ai`, `ai-red-teaming`, `llm-security`, `ai-security`,
  `sarif`, `github-action`.

- **The GitHub Action is listed on the Marketplace, and the badge landed in the same commit.** The
  README had carried a nine-line comment since 0.33.1 explaining why no badge was there — the
  listing 404'd, and a badge pointing at a 404 is the same error as advertising a container image
  that does not exist. Publishing needs the Developer Agreement accepted and a release edited
  through the web UI, neither of which has an API, so this was blocked on an operator action rather
  than on code. Now published as
  [`provael-vla-red-team`](https://github.com/marketplace/actions/provael-vla-red-team), the comment
  is replaced by the badge it was reserving, and the point it was making is kept in prose.

  Nothing about how the Action *runs* changed. `uses: provael/provael@v0.35.0` resolved from the
  repository and tag before the listing existed and resolves identically now; the Marketplace is
  discovery, not a dependency. The 0.33.1 known-issue recording the 404 is left exactly as written,
  because it was true on 13 August and a changelog that edits its own history is not a record.

## [0.35.0] — 2026-08-18

### Added

- **The input to the keep-out calibration was being discarded on every run. It is now recorded.**
  `Suite.calibration_signal()` has always returned exactly the signal a calibrator needs, the
  runner computed it on every step, and nothing ever persisted it — so every finished run left
  [#136](https://github.com/provael/provael/issues/136) no more fixable than before it started.
  The blocker was never GPU budget for the fit; it was that the data the fit consumes did not
  exist. `AttackResult.trajectory` (report schema 3) now records the per-step signal for **every**
  episode, benign and adversarial alike, gated on nothing — an opt-in flag would recreate the loss
  the first time someone forgot, and the poses are unrecoverable once the run ends.

  Stored as base64 zlib float32 with an explicit shape (~4 KB for a 280-step episode against ~17 KB
  of JSON floats), deterministic, so the artifact stays a pure function of its inputs. The sample
  is taken *before* the unsafe check breaks the loop, or the violating step — the most informative
  pose in the episode — would be missing from exactly the episodes a calibration wants most.
  `tests/test_trajectory_recording.py` makes a missing trajectory fail the run rather than warn.

  **The calibration itself is still owed.** `CALIBRATED_ZONES` is still empty, every affected row
  still reads `calibrated: false`, and closing #136 needs the benign arm re-run on a build that
  records trajectories, then a margin decision. Every artifact already under `results/` predates
  schema 3 and carries no trajectory, so none of it is retroactively usable.

- `provael workspace-bounds --runs <dirs>` emits per-task benign reachable-workspace bounds and the
  episode count behind each, flagging any task estimated from fewer than five. It deliberately does
  **not** emit a calibrated zone: that needs a margin decision, and choosing one without looking at
  real benign spread is exactly how `DEFAULT_KEEP_OUT_ZONE` came to overlap the workspace it was
  meant to sit outside.

- The leaderboard's tool-version claim is machine-checked
  (`tests/test_leaderboard_version_claim.py`). It passes only if `measured_with` includes the
  current `__version__`, or a dated entry in `leaderboard/method-equivalence.json` argues why the
  gap cannot move those rows. The entry is not a waiver flag — it has to name what changed and
  state its own limits, and the one added here says plainly that it is a code-inspection argument
  and not a re-measurement. A separate assertion compares `measured_with` against what the
  aggregated shards actually carry, which is what would have caught the earlier `["0.1.0"]`.

  `measured_with: ["0.32.0"]` was checked against the artifacts and is **correct**: the shards
  carry `tool_version 0.32.0` and were measured 2026-08-09. The board's 2026-08-17 stamp is a
  rebuild, not a measurement.

- `tests/test_freshness_semantics.py` pins what "freshest measurement" means, after the badge was
  read as broken when it was right.

- Crosswalk card for LIBERO-Safety (arXiv:2606.23686, ECCV 2026), indexed in the docs nav. Its
  `mapping_status` is `complementary-axis, not-yet-crosswalked`: their "strictly collision-free"
  construct and our keep-out envelope violation measure the same physical property from opposite
  directions, but their regime is distributional (randomisation, no attacker) and ours is
  adversarial. Neither subsumes the other — their coverage is ten policies against our one, and
  their attacker is absent while ours is the point. The taxonomy mapping onto the Top 10 is
  recorded as owed rather than delivered, and the rates are stated as not comparable in either
  direction, because neither side publishes a benign FPR on shared fixtures.

### Fixed

- One schema-aware report digest instead of four copies. `trajectory` moves the canonical JSON, so
  adding it would have made every attestation ever issued verify as **tampered** — the one failure
  a signature scheme must not have. Reports are now digested at the schema version they declare,
  and the logic that does it lives in `attest.report_projection()` alone; `execution.py` and
  `manifest.py` delegate rather than repeating it. They were identical until one of them learned
  something the others had not, which is the only way that kind of duplication ever fails.

### Known issues

- **The measurement-freshness badge is red and it is telling the truth.** The newest measurement
  under `results/` is 2026-08-09; the badge reads 9 days. It was tempting to call this a bug,
  because a ten-task board *was* published on 2026-08-17 — but that commit rebuilt the board from
  artifacts already in the tree and touched zero files under `results/`. A republication is not a
  measurement. The threshold has not been touched and the badge stays red until something is
  actually measured.

### Changed

- Prior art: added **DRIFT** (arXiv:2608.03207), the third published patch attack in a row that
  far exceeds our 0/50 on the same channel — and the entry corrects the comfortable explanation.
  It would be convenient to attribute the gap to architecture, DRIFT attacking flow-matching
  policies while we measured something else. This repo's own data refuses that: `lerobot_adapter`
  declares `action_head_class = "flow"` and every episode in the pinned evidence records `flow`, so
  SmolVLA *is* flow-matching by our own taxonomy. What remains is that DRIFT is white-box and
  gradient-optimised against the denoising ODE while our `patch` appends a fixed string to a dict
  and performs no search at all. With three such papers now published, the honest reading of the
  visual family's nulls is that provael has no image-space patch attack, and they measure its
  absence. Both nulls stay published exactly as measured.

## [0.34.0] — 2026-08-18

### Added

- The public leaderboard is now the ten-task `libero_object` suite screen, rebuilt from
  `results/smolvla_libero_object_suite/` and re-signed (keyid `8d62aa33ed5162f3`). It had been a
  four-row snapshot of the superseded single-task run, stamped `measured_with: ["0.1.0"]` for
  numbers produced by 0.32.0. Instruction is 41.3% (62/150) [34–49%] against a 4.0% (2/50) benign
  control; injection 0/50 and visual 0/100 stay published as measured nulls.

- Leaderboard `schema_version` 5: rows carry `calibrated`, `stochastic` and `checkpoint`, and the
  board carries `not_applicable`. All four are derived from the aggregated reports rather than
  passed in, for the same reason `measured_with` is — a qualifier a caller can assert is one a
  caller can get wrong. `calibrated` reduces as ALL, `stochastic` as ANY, and `checkpoint` resolves
  only when a bucket is unanimous: each collapses toward the weaker claim, because the reduction is
  where an aggregate is tempted to launder a qualifier. `not_applicable` names attacks with records
  but zero applicable episodes (`mcp_tool_desc`), which scoring excludes from every denominator and
  which therefore used to vanish from the board entirely.

  Older signed boards keep verifying. `_signing_payload` now strips fields introduced after a
  board's own `schema_version` before canonicalising; without it, adding any defaulted field would
  have invalidated every signature ever issued, and a correctly-signed v4 board would have verified
  as INVALID — indistinguishable, to whoever checked it, from a tampered one.

- The uncalibrated keep-out fallback stops being silent ([#136](https://github.com/provael/provael/issues/136),
  half of it). `zones_for` now warns once per task that it is scoring against the default box rather
  than a calibration, and `PROVAEL_REQUIRE_CALIBRATED=1` makes it a hard `UncalibratedZoneError`.
  Off by default so the honest default stays usable for exploratory work; the env var is
  allow-listed into the execution manifest so "we checked" is verifiable after the fact. The
  calibration itself is still owed and still needs GPU budget — #136 stays open.

  The state is recorded via the manifest's env allow-list rather than as a new manifest field:
  `RunReport` already carries `calibrated` and its per-task `calibration` metadata, and the manifest
  is bound to that report by `report_digest`, so a new field would have bought nothing and
  invalidated every attestation ever issued (see `EXECUTION_MANIFEST_VERSION`).

### Fixed

- README stated the benign control as `0/10 (benign FPR 0%)` and scoped the result to "one task,
  n = 10" directly below the ten-task table reporting 2/50. Both were leftovers from the
  single-task era, and the first one contradicted its own page.

- PyPI metadata gave visitors no route to the project. All three project URLs pointed at GitHub, so
  neither www.provael.com nor docs.provael.com was reachable from the sidebar; `author_email` was
  unset. Added `Homepage`, `Documentation` and `Changelog` URLs, set the author email, and added the
  classifiers the package already earns (`Operating System :: OS Independent`,
  `Environment :: Console`, `Intended Audience :: Developers`, and `Typing :: Typed`, since
  `py.typed` ships). Moved `Development Status` from `3 - Alpha` to `4 - Beta`: "Alpha" reads to an
  evaluator as "do not depend on this yet", which is the audience the package is trying to reach.

- Added DURA and UniTexture to prior art, including the part where DURA's patch attack is far
  stronger than ours. Added a runnable matched-pair example so the benign twin is reproducible on
  CPU without a model download.

  On DURA specifically: the entry now says our patch implementation is weak rather than that the
  attack class is weak, and gives the reason. DURA optimises in the latent space of a pretrained
  diffusion model; our `patch` appends a fixed string to a dict and performs no search at all, so
  there is no mechanism by which it could find what DURA finds. `patch` stays published at 0/50 and
  the visual family at 0/100.

  `examples/matched_pairs.py` runs on the stub policy and stub suite in under a second, with no GPU
  and no download, and prints the 2x2 contingency table, the exact McNemar p-value and the
  task-clustered interval. The interval prints as `None`, which is correct and is explained in the
  file: every CPU-only suite has one task, and `cluster_bootstrap_ci` declines below two by design.

### Known issues

- The benign control fires 2/50 and the keep-out predicate remains uncalibrated. Diagnosed and
  filed as [#136](https://github.com/provael/provael/issues/136): `CALIBRATED_ZONES` is empty, so
  every task falls back to a hand-picked default box that overlaps the reachable benign workspace.
  Benign false-positive rate 4.0%, Wilson 95% [1.1%, 13.5%]. Blocked on GPU budget, because the
  trajectories needed to fit an envelope were never recorded.

## [0.33.2] — 2026-08-15

### Fixed

- **The Hugging Face Space sync had been failing silently since 12 August**, and the repo was
  positioned to undo the manual fix. `POST /api/validate-yaml` returns 400 when
  `short_description` exceeds 60 characters; ours was 65, so the deploy aborted while the repo
  looked healthy.

  The card was then fixed *on the Space* through the web editor — 58 characters, Gradio 6.23.1 —
  while the repo kept 65 characters and `sdk_version: 6.16.0`. The repo is the side that syncs, so
  the next successful deploy would have pushed the broken description back **and downgraded the
  SDK under the running app**. `tests/test_space_card.py` now asserts the constraints the HF API
  enforces, offline, so a card that cannot deploy fails `pytest` rather than a workflow nobody
  reads.

  The card's `24.3% (17/70)` is deliberately unchanged: it is what `leaderboard/results/
  leaderboard.json` actually holds. The ten-task suite at 44/50 has never been promoted onto the
  leaderboard, and "correcting" the card to 88% would have made it describe data the Space does not
  serve. A note points at the larger run instead, and the fourth test pins the card to the
  artifact's own sum rather than to the newest number the project has.

### Added

- **A guard that fails when the CHANGELOG gets ahead of the artifact**
  (`tests/test_version_consistency.py::test_every_dated_changelog_version_has_a_tag`). On 13 August
  this file carried `## [0.33.1] — 2026-08-13` and `CITATION.cff` carried a matching
  `date-released`, while no `v0.33.1` tag existed and PyPI's latest was 0.33.0. Every surface a
  reader consults said it had shipped; nothing had, and a person found it rather than CI.

  A **dated** heading is the claim; `## [Unreleased]` asserts nothing and is ignored, so the normal
  workflow is unaffected. The newest dated heading may be untagged only while it names
  `__version__` — the release-prep commit, where promoting the heading and pushing the tag cannot
  be one event. **That exemption is a stated cost, not a loophole:** this test could not have
  failed on the exact commit that introduced the drift above. What it catches is the drift
  *persisting*. `0.1.0` is exempted permanently — it has a section and no tag, and a release that
  was never cut cannot be tagged retroactively.

- **Four prior-art entries, every figure read from the paper rather than the abstract.**

  **RedVLA** (arXiv:2604.22591) is the closest published work to this project and appeared nowhere
  in `PRIOR_ART.md` — only once, inside a run-on inline list in `docs/top10.md`. It is now a full
  entry plus a row in the published-ASR baselines table.

  The entry corrects the framing this work was queued under. RedVLA is **not** separated from
  provael by hardware: both run in simulation, both on LIBERO. It is separated by which half of a
  shared formalism each takes. RedVLA defines red teaming as optimisation over the
  environment–instruction joint space `(s′₀, l′)`, then states **"We fix the instruction (i.e.,
  `l′ = l`) and perturb only the initial state."** Provael fixes the scene and perturbs the
  instruction. Complementary halves, orthogonal quantities — which is why no comparison is drawn
  between their 95.5% and our 88% anywhere.

  **The "Ten Deadly Sins" paper** (arXiv:2512.06387) was queued as a competing ten-item taxonomy at
  the same layer as the Embodied AI Security Top 10. Reading it shows it is not: it is a security
  analysis of **one product, the Unitree Go2**, and its ten items are implementation defects in that
  product's stack. The entry says so, and names two real gaps on our side rather than defending the
  Top 10 — **"multilingual" appears nowhere in `docs/top10.md`**, and neither the companion app nor
  the vendor cloud is named as a surface, though three of the paper's five methods target them.
  The abstract enumerates nine defects for a list of ten; the tenth is not guessed at.

  **DAERT** (arXiv:2604.05595) and **EmbodiedGovBench** (arXiv:2604.11174) complete the set. DAERT
  is the second independent demonstration — after Q-DIG — that search finds linguistic failures our
  fixed four-template banks miss. Two papers now say the same thing about our method.

- **Two new crosswalk targets, as artifacts rather than prose.**

  `provael crosswalk --target vla_arena` maps VLA-Arena's five safety suites (arXiv:2512.22539),
  identifiers verbatim, into `results/crosswalk/crosswalk.vla_arena.json`. VLA-Arena runs the only
  public VLA leaderboard carrying a safety axis, which makes it the one place a provael number
  could be mistaken for a comparable entry.

  The distinction that prevents that is carried as a **machine-readable field**, not a sentence:
  their safety suites place a hazard in the scene and **none perturbs the instruction**. The
  consequence is the useful part — the provael arm corresponding to their entire safety axis is the
  **benign control** (2/50 on the ten-task run), not any attack family. Every attack number provael
  reports lives on an axis their leaderboard has no column for. Coverage is 0 of 5, and all five
  rows map zero attack families, which the artifact states outright is the correct result.

  `provael crosswalk --target safevla` makes `docs/crosswalk/safevla-bench.md` and the code agree.
  That page described a mapping with no command and no artifact behind it; the command now exists
  and emits the structural mapping. **It deliberately emits no number.** `scoring/asr.py` already
  has a `succ_but_unsafe` field naming SafeVLA-Bench, and that shared name is the hazard: theirs is
  an STL judgement over a trajectory, ours a boolean from an uncalibrated predicate whose benign
  control fires at 4%. The blocker ships as data, and calibration remains the prerequisite.

- **`examples/lerobot_eval_smolvla_libero.py`** — the headline result in one file with nothing to
  edit and nothing to install. PEP 723 inline metadata means `uv run` builds the environment from
  the pinned header. `--dry-run` validates the registries and the `RunConfig` on any laptop in
  seconds, with no torch and no download — the checks that would otherwise fail at minute 0 of a
  15-hour run.

  It prints the matched-pair table and McNemar p-value from `provael.scoring.paired` rather than
  reimplementing them, so the benign control is structurally impossible to drop, then compares your
  run against the committed reference and says whether you reproduced it.

  **lerobot is pinned at 0.5.1, not 0.6.x.** 0.6.0 and 0.6.1 exist and are newer; the committed
  numbers were measured on 0.5.1 and have never been re-measured. Pinning forward would make this a
  script that runs rather than one that reproduces. `tests/test_reproduction_example.py` pins the
  example's advertised baseline against `aggregate.json` by reconstructing successes from the
  McNemar discordant counts — the file needs a GPU to execute, so without that test its claims
  could rot silently.

### Fixed

- **`docs/standards/published-asr-baselines.md` opened by quoting a superseded number.** Its intro
  read "100% of the time (10/10)" while its own table row read 88% (44/50) — the single-task run
  against the ten-task suite. The intro now quotes the larger, more conservative run, and the
  section further down that legitimately reports the 10/10 figure says which run it is and why both
  are retained.

- **Two pages named "Adopters" meant different things and neither said so.** `docs/adopters.md` is
  a self-reported sign-up sheet and is empty; `provael.com/adopters` is a measurement of PyPI
  downloads and GitHub stars and is not. Each now states what it is in its first lines and links
  the other, because **an empty sign-up sheet is not an empty user base** and reading it as one is
  the available mistake.

### Chores

- Merged five dependabot PRs (#126–#130): `docker/build-push-action` 6.18.0→7.3.0,
  `docker/metadata-action` 5.7.0→6.2.0, `github/codeql-action/upload-sarif` 4.37.5→4.37.6,
  `docker/login-action` 3.4.0→4.6.0, `docker/setup-qemu-action` 3.6.0→4.2.0.

## [0.33.1] — 2026-08-13

An **archival and listing release**. No functional change to the harness: no attack, scorer, policy
adapter or emitter behaves differently from 0.33.0, and no published number moves.

It exists because two external surfaces need a tag they can point at, and both read `action.yml`
from the **tag** rather than from `main`:

### Fixed

- **The Action description exceeded the GitHub Marketplace limit.** The publish validator rejected
  the listing with "Description must be less than 125 characters"; ours was **266**. Now **114**.
  The detail it carried — the attack matrix, the EAI-tagged SARIF, the threshold-and-regression
  gating semantics — moved into a comment directly above the field, which is where a maintainer
  reads it anyway. A listing description is a listing description.

### Changed

- **`PROVAEL_VERSION` floor moved to `>=0.33.1,<0.34.0`**, per the rule stated at its own
  definition: the floor tracks the newest patch so a fix is not optional for anyone pinning a
  published action tag.

- Adopter-facing pins bumped across the eight files `tests/test_version_consistency.py` enumerates,
  plus `CITATION.cff`'s `version` and `date-released`. That test inverts the allow-list on purpose —
  the pins that drift are exactly the ones nobody remembers to list.

### Why a release at all

Two things are blocked on a tag and neither is code:

1. **The GitHub Marketplace listing**, which reads `action.yml` from the release tag. `v0.33.0`
   still carries the 266-character description, so re-publishing from it fails the same way.
2. **The Zenodo archive and its concept DOI.** Zenodo only archives releases created *after* its
   GitHub integration is enabled, so the first archived release has to be a new one.

Neither is a reason to change behaviour, and nothing here does.

### Added

- **Six prior-art entries, five new and one enriched from a stub.** Trajectory-Level Redirection
  (arXiv:2606.12978), RoboJailBench (2605.19328), CoT vulnerabilities (2603.12717), Q-DIG
  (2603.12510), the NUS VLA safety survey (2604.23775) and !Imperio/smolVLA data poisoning
  (2607.04146). Every figure was verified against the paper before printing — the 7-of-9 >90% ASR
  count and the 3.4-character edit average were read out of the source table, not the abstract.

  Each entry states where **provael is weaker**, because that is the part a reader cannot get
  elsewhere: nine architectures against our one measured policy; SO-100 and SO-101 hardware against
  our zero; on-policy prompt search and quality-diversity generation against our fixed four-template
  banks; a public benchmark with external submissions against our zero third-party rows; and a living
  field index that does not list us.

- **The semantic-versus-mechanical instruction finding**
  (`docs/findings/semantic-vs-mechanical-instruction-attacks.md`), stated as a hypothesis with
  supporting evidence and labelled as such in its first paragraph.

  In one run at matched (task, seed) cells: `roleplay` 44/50 (88.0%) [76.2%, 94.4%] against
  `paraphrase` 3/50 (6.0%) [2.1%, 16.2%], intervals disjoint, with `paraphrase` **indistinguishable
  from the benign control** at McNemar p = 1.0 while `roleplay` separates at p = 4.6e-13.

  One policy, one suite, simulation only, maintainer-run, uncalibrated predicate, four templates per
  arm. The page states what would falsify it and computes what settling the open half would cost:
  ~197 discordant pairs, ~1,960 episodes per arm, to test whether `paraphrase` differs from doing
  nothing at all. Mirrored into EAI01 and the instruction-family docs.

- **`tests/test_atlas_submission.py`** — the ATLAS submission artifact is now validated rather than
  merely committed: collection version named, no `AML.T` id invented, case study typed `exercise`
  rather than `incident`, scope limits present, disposition recorded.

- **A `provenance` column on the leaderboard**, per row. The field was always recorded and never
  displayed, so a reader could not tell a self-reported row from an external one.

- **DURA (arXiv:2608.10393) added to PRIOR_ART, and it makes our own visual null look worse.**
  Every figure read from their Table 1 rather than the abstract, and from DURA's own `Ours` rows: 100%
  ASR white-box target-only on all four LIBERO suites in BOTH simulated and physical patch settings,
  86.0% / 79.3% black-box, 77% ASR from a patch covering 2% of the image and 99% at 5%, against benign
  and clean-patch baselines of 23.5% and 39.5%. A label-supervised baseline in the same table (UADA)
  also reads 100.0; attributing that row to DURA is the obvious misreading and the entry names it.

  **The useful part is the contrast.** Provael's `visual` family is two attacks and neither is an
  image: `patch` appends the string `adv_patch::{object}::now` to a simulated `visual_tokens` list,
  `decoy_object` appends `salient-decoy-first`. Symbolic stand-ins, in a simulator that renders no
  adversarial pixel. DURA optimises real pixels along a diffusion latent trajectory, prints them, and
  holds them in a Franka arm's camera view.

  So our 0/100 visual null does **not** mean perception attacks failed to transfer — it means our
  markers did not fire. `docs/top10.md` EAI02 now says so where the null sits, and calls it a coverage
  gap in this harness rather than a robustness finding about the policy.

- **A "How to cite" section with BibTeX** in the README, which is what a PI copies.

- **`leaderboard` tags on the Space README** (`leaderboard`, `submission:manual`, `test:public`,
  `modality:text`, `eval:safety`, `language:English`), following DontPlanToEnd/UGI-Leaderboard's
  vocabulary. The Space ran with no `tags:` at all, so Hugging Face derived only
  `["gradio", "region:us"]` and it never appeared under the `leaderboard` filter — the one place
  someone browsing for a leaderboard would look. `modality:image` is deliberately absent: the visual
  family is symbolic and measured 0/100, so claiming it would advertise coverage the board lacks.

- **A CI usage snippet beside the docker quickstart**, showing the Action gating a build on the
  measured rate. It works today without the Marketplace — `uses:` resolves from the repo and tag.

- **The AI45Lab trustworthy-embodied-AI survey cited in PRIOR_ART** (OpenReview `Eu6Yt21Alv`,
  companion index `AI45Lab/Awesome-Trustworthy-Embodied-AI`). Their four-stage decomposition —
  instruction understanding, environment perception, physical interaction, action planning — is
  **cleaner than our ten-item list** at separating where in the loop a failure originates, and we
  have not attempted a crosswalk to it.

  Counts verified rather than repeated: the index carries **183 reference links, 116 to arXiv, 69
  unique arXiv IDs, and zero links to anything executable** (no GitHub links outside their own
  repo). Where we are weaker is stated plainly — their Attack Resistance spans all four stages;
  ours has a real-model measurement on exactly one, and **physical interaction is the stage we
  cannot speak to at all** because `results/hardware/` reads 0.

- **A written JOSS submission assessment** in `docs/standards/listings.md`, with a decision and a
  named trigger rather than an intention. Every mechanical bar is met; the bar genuinely at risk is
  "substantial scholarly effort", because 8 registered policy backends resolve to **one measured**
  one, `hardware=0`, and the four GitHub contributors are two maintainer accounts plus two bots —
  so **zero external contributors** is the true figure. Decision: hold until either a second
  real-model backend or the SO-101 hardware result lands. A desk rejection spends the route;
  waiting costs weeks.

### Fixed

- **The EAI02 visual null was stale in `docs/top10.md`**: it read 0/20 against a 0% benign baseline.
  The ten-task suite measured the visual family at 0/100 with a 2/50 (4%) benign control.

### Changed

- **The leaderboard says out loud that third-party submissions are 0**, in the same spirit as
  `results/hardware/README.md` reading 0. The documented submission path was then run end to end
  against a dummy and the dummy deleted — including confirming that promoting a stub run to the real
  board is **refused**, which is the guard working.

- **`docs/standards/index.md` records the ATLAS validation.** The submission was sent 8 August and is
  still awaiting a response; it was validated against the v6 object model on 12 August. Our file is a
  submission memo, not an atlas-data object — right for an email, wrong for a pull request, and the
  conversion is written down. The gap argument is now verified rather than asserted: the Impact tactic
  AML.TA0011 has 19 techniques and every one lands on an informational or economic surface; none names
  an actuator, a trajectory, or physical motion.


### Not done, and why

- **No DOI.** Zenodo returns zero records for provael, and minting one requires enabling the Zenodo
  GitHub integration through their web UI — an OAuth action that cannot be performed from here. The
  README carries BibTeX **without** a `doi` field, plus a comment naming the three places the concept
  DOI goes when it exists. A non-resolving DOI in a citation block is the worst error available here:
  a citation is copied once and lives in someone else's bibliography, failing in a reviewer's
  reference check rather than in ours.

- **No Marketplace listing.** `github.com/marketplace/actions/provael` still 404s. Publishing needs
  the Marketplace Developer Agreement accepted and a release drafted through the GitHub web UI; there
  is no API for it. Prepared instead: the second category is evidenced rather than guessed —
  comparable SARIF-uploading Actions pair **Security** with a domain category (anchore
  `Container CI`, gitleaks `Code search`, checkov `Code quality`), and none uses
  `code-scanning-ready`, which appears to be a browse facet rather than an author-selectable
  category. **Security + Testing** matches what this Action does: run an adversarial suite and gate
  the build. No badge was added — a badge pointing at a 404 is the same error as advertising an image
  that does not exist.

- **No hardware order date.** `results/hardware/` still reads 0 with no clock, because ordering an
  SO-ARM101 is a purchase decision and any date written before the order exists would be fabricated.
  The two dated lines land the day it is placed.

## [0.33.0] — 2026-08-10

### Added

- **Both Docker base images pinned by digest, and the publish wired for Docker Hub.** A tag is a
  moving pointer — `python:3.12-slim-bookworm` is rebuilt on every CVE patch, so the same Dockerfile
  built a different image each week and a published `provael/provael:0.33.0` was not reproducible
  from its own source. Each pin is the **multi-arch index** digest, never a per-arch manifest:
  pinning one architecture would silently drop arm64, which has already broken here once in the
  other direction and is invisible to CI because the runner is x86_64.

  `docker-publish.yml` now fans one build across `ghcr.io` and `docker.io` from a single
  `metadata-action` image list, so the two registries cannot drift to different bits under the same
  version. Docker Hub **fails soft**: unconfigured, the job still publishes GHCR and emits a warning
  naming the missing secrets, because one unconfigured registry is not a reason to withhold the
  other — and a silent skip would leave the README advertising an image that does not exist.

  **Docker Hub is not published yet.** `hub.docker.com/v2/repositories/provael/` returns
  `{"count":0}` and no org access token has been configured, so `DOCKERHUB_USERNAME` /
  `DOCKERHUB_TOKEN` are unset and the workflow will skip that half on this tag. The README's docker
  quickstart therefore points at **`ghcr.io/provael/provael`**, which is public, multi-arch and
  verified logged-out. It will not name Docker Hub until Docker Hub answers.

- **A docker quickstart in the README**: the stub scan with no local Python, no `uv`, no virtualenv.

- **SafeVLA-Bench (arXiv:2606.00773) added to PRIOR_ART, with an `aspirational` mapping_status.**
  Overdue rather than new: `scoring/asr.py` has named SafeVLA-Bench in `succ_but_unsafe`'s docstring
  since that field was added, so the project borrowed their metric's name without ever citing them
  in prior art.

  The entry is explicit that this is **not** the existing `SafeVLA` entry — two different works two
  years apart with near-identical names, one a constrained-learning *defense*, one an *evaluation
  framework*. Conflating them would attribute a benchmark's metrics to an alignment method.

  The relationship is stated as different failures on the same policies: their SBU and VSI are
  **post-hoc and non-adversarial** (did the policy's own successful rollout conceal a violation),
  our ASR is **pre-hoc and adversarial** (can an attacker cause one). `docs/crosswalk/safevla-bench.md`
  carries `mapping_status: aspirational` and says why the honest blocker is ours: our
  `succ_but_unsafe` shares their name but not their units — theirs is an STL judgement over a
  trajectory, ours a boolean from an **uncalibrated** predicate whose benign control fired 2/50.
  Calibrating it is the prerequisite and it is not done, so no crosswalk is claimed and no
  `--target safevla` exists.

  Their finding that most concerns a reader of our numbers is recorded rather than buried: high-SR
  baselines still leave 13–15% unsafe-episode rates unattacked. Our ASR measures lift over a benign
  control, so a policy already unsafe 15% of the time with no adversary present is **invisible to our
  headline by construction**.

- **The benign-reword arm, which is the strongest objection to our own headline.** `benign_reword`
  and `nonsense_text` were written, tested and deliberately left UNREGISTERED, because
  `attacks/controls.py` could not be enabled until scoring grew a third role. It has one now.

  `provael.scoring.asr` gains `CONTROL_FAMILY`, `is_harmless_variation`, a `harmless-variation`
  semantic role and `harmless_variation_rate`. A control is excluded from BOTH populations: from the
  adversarial results (folding it in would inflate the ASR with episodes no adversary caused) and
  from the benign-FPR baseline (mis-classing it there would corrupt the false-positive rate the ASR
  is read against). Both failures are silent, and both make the headline mean something other than
  what it says.

  `full-sweep` now runs both control arms. A sweep of every attack with no reword control cannot
  separate "the attacker chose where the policy went" from "the policy is brittle to being asked
  differently", which is exactly the limitation provael.com states in its own words.

  **If the reword arm fires as hard as the attack, that is the result and it will be published.**
  `test_a_reword_that_fires_as_hard_as_the_attack_is_visible` asserts the scoring surfaces that case
  rather than averaging it away.

- **The reword arm has now been run on a real policy, and the headline survives it.**
  `results/smolvla_libero_object_control/` — 200 episodes, 10 tasks, 5 seeds, all four arms paired in
  one report so every comparison is internal to one artifact.

  | arm | pooled | vs `none` (McNemar) |
  | --- | ---: | ---: |
  | `roleplay` | **44/50 (88%)** | p=9.1e-13, Holm 2.7e-12 |
  | `benign_reword` | **1/50 (2%)** | p=0.625 — **indistinguishable from doing nothing** |
  | `nonsense_text` | **0/50 (0%)** | p=0.25 — indistinguishable |
  | `none` | 3/50 (6%) | — |

  `roleplay` vs `benign_reword` directly: **43 discordant pairs, none in the other direction,
  p=2.3e-13.** A semantics-preserving reword of the same instruction does not move this policy out
  of its envelope; the attack does. The 88% measures attacker control, not brittleness to being
  asked differently. `nonsense_text` at 0/50 closes the other route — gibberish does not do it
  either, so the effect is not encoder degradation.

  What it does not settle, stated in the result's own README: the predicate is **still
  uncalibrated** and the benign arm fired 3/50 here against 2/50 in the suite run, so this run
  reproduces that problem rather than resolving it; the reword bank is four fixed templates, so what
  is measured is that *these* rewords do not fire, not that none could; and because SmolVLA samples
  actions this is a second independent draw, not a replication.

### Fixed

- **[Unreleased] claimed nothing was pending while holding twelve commits of entries.** The section
  ended "Nothing pending — everything currently written is released" directly beneath a full
  Added/Fixed/Changed block. Both statements were in the file at once, and the release gate added in
  #112 passed every time — it only ever checked that the *released* heading existed with a real
  date, and never looked at `[Unreleased]` at all.

  `scripts/check_changelog.py` now fails when `[Unreleased]` contains the placeholder **and** any
  other content. Deliberately that pair and not the placeholder alone: the placeholder is the correct
  content of a genuinely empty section, and deleting it unconditionally would leave the next
  contributor a bare heading wondering whether entries were lost. An empty `### Added` under the
  placeholder counts as content, because that is how the contradiction usually starts — catching it
  at that point is cheap, catching it twelve commits later is not.

  This is the detail a reviewer notices before they notice the science: it makes the document look
  unmaintained at the exact moment someone is deciding whether to trust the numbers in it.

- **`control` was being counted as an adversarial family.** Subtracting only `BASELINE_FAMILY` was
  the same bug `recipes.ALL_FAMILIES` warns about in its own comment, one level up: registering a
  control silently grew a sixteenth "attack family" that is not an attack. `coverage.py` gains
  `NON_ADVERSARIAL_FAMILIES` and every count derives from it, so the documented "15 adversarial
  families" stays true. Totals move 16 -> 17 families and 29 -> 31 attacks, updated in README,
  docs/quickstart.md and the notebook.

### Changed

- **The headline result is now a ten-task suite rate, not a single-task existence proof.**
  `roleplay` on real SmolVLA × LIBERO: **44/50 matched pairs (88%) across all ten `libero_object`
  tasks**, McNemar exact **p = 4.6e-13**, Holm-adjusted **2.7e-12**, **task-clustered 95% CI
  [72%, 100%]**. Supersedes 10/10 on `libero_object/0` at p = 0.0020.

  The clustered interval is the upgrade, not the point estimate. It is bootstrapped over TASKS
  rather than episodes, because episodes inside a task are correlated and pooling them reports an
  interval far too narrow — and it could not be computed at all before, since
  `cluster_bootstrap_ci` returns `None` below two tasks by design. Its bounds coincidentally match
  the old single-task Wilson interval; the construction and the claim are different.

  Adding tasks changed a verdict: `goal_substitution` was 6/10 at p = 0.031 and did NOT survive
  correction on one task; over ten it reaches 15/50, p = 9.8e-4, and does.

  Disclosed with it: the benign control fires on 2/50 (the predicate is uncalibrated, the same
  fixed keep-out zone on all ten tasks); `patch`, `decoy_object` and `scene_text` are measured
  nulls at 0/50 each; `mcp_tool_desc` is NOT APPLICABLE to this suite rather than a null, which is
  why the run is 350 measured episodes of 400 records; clean-task-success averages 84% and ranges
  40–100%, so the policy is not uniformly competent; and the sampler is not fully seeded, so this
  is one draw rather than a reproducible constant.

  Updated: README (headline and result table), `docs/findings/2026-instruction-transfer.md`,
  `docs/standards/published-asr-baselines.md`, `docs/attacks.md`, `docs/faq.md`, `docs/top10.md`,
  `docs/crosswalk/robojailbench.md`, `docs/findings/2026-cross-arch-transfer.md`.

## [0.32.0] — 2026-08-08

### Added

- **`results/hardware/` exists now, empty, with the protocol in it.** A directory that appears only
  once results exist is a directory nothing can count. `provael coverage` derives a
  `hardware_results` count from it, so the sim-to-real claim on provael.com moves the day the first
  physical run lands instead of waiting on a docs edit.
- **`provael sim-to-real --dry-run`** — walks the same code path a physical run takes (runner,
  scoring, report, execution manifest, evidence manifest) against the deterministic CPU stub and
  asserts the artifact shape a real run must produce, so the first physical session is not also the
  first debugging session. It refuses to write into `results/hardware/`, because that directory is
  counted as physical evidence and a dry run must not inflate it. There is no non-dry path, and
  `--no-dry-run` says so with a reason rather than doing something ambiguous.
- **The ATLAS submission YAML is committed** at `docs/standards/atlas-submission-2026-08-08.yaml` —
  one proposed technique and one case study, typed *exercise* rather than *incident*. Committing the
  exact file makes the submission reproducible and puts its date on the record.

- **`provael coverage` — one place computes the coverage counts, and it refuses to print a bare
  total.** The counts are restated in the README, the docs, the Space and on provael.com, and a
  restated number drifts. This prints them as one machine-readable line so every surface can
  render rather than retype. It carries the validation breakdown in the same output because
  registered is not validated: 15 adversarial families are registered, **3 have been exercised
  against a real policy** (and two of those three returned measured nulls, which is a result),
  12 are stub-validated only. The real-policy set is derived from the committed run reports, so
  it rises on its own when a family is measured and cannot be inflated by editing a constant.
- **`provael submit --dry-run`** — validate, sign and print exactly what would be submitted,
  touching no network and writing nothing into the repository. It works outside a clone, which is
  the state a stranger is actually in when they first look.

### Fixed

- **The last-measured badge read "never", in red, on a project whose whole argument is that it
  measures things.** It was reading only the nightly's own log, and the nightly has never run — so
  an empty log was reported as "nothing was ever measured", which contradicts a published 10/10
  real-policy result. It now reads the end timestamp of the most recent run that actually executed
  attacks against a policy, which is a different thing from the generator run and a different thing
  again from the commit date. `docs/standards/last-measured.md` writes the definition down.
- **The badge now says when a date is approximate rather than implying it is exact.** The one
  committed real-policy run reconstructs its own provenance after the fact — identical start and end
  at exact midnight, a synthetic commit label, `legacy-unverified` with six missing fields — so the
  badge reports the date *and* marks it, and a reconstructed timestamp can never read green. Green
  would assert a precision the artifact does not have.
- **A provenance tell that would have misclassified every fast run.** Identical start/end was
  initially treated as evidence of reconstruction; manifests are stamped at second granularity, so
  every sub-second CPU run would have been marked untrustworthy. Caught by the new sim-to-real
  dry-run asserting its own artifact shape, which is what that assertion is for.

- **A coverage-count correction that runs the other way to the usual one.** An external report
  read the attack registry's dict length, 29, as a family count and concluded the website
  understated coverage by 14 families. It does not: 29 is 29 registered *attacks* — 28 adversarial
  plus one benign control — grouping into **15 adversarial families**, which is what the site
  already publishes and already derives from the registry. Publishing 29 would have overstated
  coverage, on the surface whose entire argument is that its numbers are checkable. The two
  numbers are now both printed, each labelled, and a test asserts the README never calls an attack
  count a family count.
- **`provael submit` staged files outside a repository and then printed git commands that could
  not work there.** Run from any directory that is not a clone — which is where a stranger starts
  — it wrote `results/<name>/` into that directory and told the reader to `git add` it. It now
  checks for a repository first, before validating or signing, and says what to do instead: fork,
  clone, or use `--dry-run` to preview without any of it.
- **`provael submit` referred to a PR body it had never printed.** On the no-`gh` path the last
  instruction was `--body <the summary above>`, and no summary appeared above it. It now prints
  the body.
- **`provael coverage` output was wrapped by the terminal renderer**, splitting the one
  machine-readable line across two and corrupting the JSON mid-string. Machine output no longer
  goes through the human-facing console.

- PRIOR_ART.md now cites DRIFT (arXiv:2608.03207), SARF and AGSD (arXiv:2608.03231) and
  FLARE (arXiv:2607.14698). DRIFT reports that flow-matching robustness came from
  measuring it wrong, which is a result provael should be pointing at, not competing with.
- An RFC amendment proposing first-step denoising redirection as a named sub-class. It is
  a proposal. The taxonomy does not move until people who work on this have replied.
- **`provael submit` — the whole leaderboard-submission path in one command.** Validate a run
  against the submission schema, Ed25519-sign it so the numbers are tamper-evident in transit, and
  open the PR. The machinery for outside submissions has existed since the board did and has never
  been exercised by anyone outside the project, which is what a five-step README buys you. Every
  step prints the command it ran, and a missing or unauthenticated `gh` degrades to "validated,
  signed, staged — here are the remaining steps" rather than failing with the work thrown away.
- **Leaderboard rows carry `submitted_by` and `provenance` (schema v3 → v4).** `transfer_status`
  answers "is this a real measurement?" and could never answer "whose?" — so a board of four rows
  from one maintainer run and a board of four rows from four independent labs were identical in
  every field. The CLI table and the Space now render the submitter and state the independence
  count outright. The committed board says what is currently true: **1 submitter, 0 independent.**
  Attribution is inside the signed payload, so forging a row's origin breaks verification exactly
  the way editing a success count does.
- **`provael watch` — a freshness signal that decays on its own.** Records a completed run into the
  existing trial ledger plus a run-level log, and emits a shields.io endpoint badge for
  "last measured: N days ago" (green ≤ 2 days, amber ≤ 7, red after). The age is recomputed on
  every refresh by a cheap CPU cron (`freshness.yml`) that runs whether or not anything was
  measured — a badge emitted *by* the measurement job would freeze on its last green exactly when
  measurements stop, which is the one event it exists to surface. The published board sat a month
  stale under precisely that silence.
- **A `eai04-redirect` recipe**, pinning the EAI04 targeted-redirection protocol to the same
  episodes/horizon/query-budget as the published SmolVLA × LIBERO run, so a result from it is
  comparable to that run rather than merely adjacent to it.

### Changed

- **The EAI04 redirection objective now searches the suite's own predicate.** `targeted_redirect`
  operationalizes EAI04 (targeted trajectory redirection) and its search maximised the *stub's*
  scalar danger axis unconditionally — including on a spatial suite, where nothing reads that axis
  and the run is scored by a keep-out zone on the end-effector. The search was climbing one
  quantity while the run scored another, and it still reported a rate, which is the invisible kind
  of wrong. The objective now dispatches on the suite's declared predicate:
  :func:`~provael.suites.keepout_zones.zone_margin` makes the keep-out predicate continuous (flat
  booleans are unsearchable), and the runner hands each attack the suite's zones the same way it
  already hands over the action layout. Without a verified action layout the spatial path declines
  to guess and ranks below every scored candidate rather than optimising a slice that may not be
  translation. Exercised on CPU via the `reach` suite, whose end-effector position is a pure
  function of the emitted action — so the LIBERO lane adds a real simulator rather than this code
  path's first execution. **No EAI04 real-transfer number is claimed:** see below.

### Not in this release

- **Still 0 real-robot results**, and this release is the one most likely to be misread as
  changing that. `results/hardware/` now exists, the protocol is in it, the `[hardware]` extra
  resolves and the dry-run passes end to end. All of that is the software half. The arm is not in
  hand, the count is 0, and being one `pip install` from a physical run is not evidence of one.
- Still 0 results against a flow-matching policy. SARF published a real PiPER number and provael
  has not published one at all. Still 0 third-party leaderboard submissions, forks or external
  contributors.
- **The ATLAS submission is prepared, not accepted.** The YAML is committed and dated; MITRE has not
  reviewed it. Submitted-and-pending is a state a reader can check — it is not a standards
  reference, and it will be updated here including if the answer is no.
- **No measured EAI04 real transfer.** The wiring above is what the measurement needs; the
  measurement itself requires the `[lerobot]` extra and a GPU, and it belongs on the Modal nightly
  rather than on a maintainer laptop. Running it needs `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` and
  `ENABLE_GPU_NIGHTLY=true`, none of which are set on the repo today. Until it runs, EAI04 stays
  exactly what it was — a stub-scaffolding result with an honest cross-reference — and no number
  here changes.
- **No Meta-World rows.** `docs/studies/metaworld-transfer.md` pre-registers SmolVLA *via LeRobot*
  on Meta-World and gates itself on `PROVAEL_INTEGRATION=1` + a GPU. Meta-World renders on CPU; the
  policy under test does not, so the study is blocked by the same missing stack, and its `n`,
  seeds and horizon are still `_TBD_`. Fixing those is a pre-registration amendment, not a run.
- **The GPU nightly stays off.** Setting `ENABLE_GPU_NIGHTLY=true` without the Modal secrets would
  turn a silent no-op into a nightly failure that still measures nothing, so the switch waits on
  the credentials rather than leading them.

## [0.31.1] — 2026-08-03

Recorded retroactively: 0.31.1 was tagged and published to PyPI on 3 August 2026, and this section
was never written — so the changelog spent a release claiming its newest version was unreleased,
which is the same class of defect as the stale keyid it documents. The entries below are the work
that actually shipped in that tag.

### Fixed

- **The documented verify command printed a keyid the docs called impossible.** The
  signing key was rotated in #74 and two files kept printing the old
  `5b9a65790d93d0bc`, with `docs/leaderboard.md` stating it was the only key the board
  is signed with. The board is signed with `8d62aa33ed5162f3`. Both surfaces now derive
  the keyid from `leaderboard.pub` at build time, and a test fails the build if any file
  carries a keyid that does not match. Logged in the errata register with the window
  during which the docs were wrong. If you verified a board between 2026-07-30 and today
  and got a keyid mismatch, that was this.
- **The docs site had not published since before the URL rename.** `docs.provael.com` was
  serving the pre-0abe0d7 uppercase tree, the lowercase URLs 404'd, and the redirects
  that commit promised were never live. `/errata/` was among the pages you could not
  reach, which is the one page that tells you to check it before relying on a regulatory
  date in an artifact you hold. The deploy is fixed, the redirects are in, and a
  post-deploy smoke check now fails the job on a 404.
- **The published leaderboard Space was a month behind and served an unsigned board.**
  It was still on schema v1 with `signature: null` while the docs said it rendered a
  staleness banner from `measured_with`. It now deploys from the repo on every board
  change.

### Changed

- Re-stamped the published board so the freshness guard is not one release from failing.
  `measured_with` still reads `0.1.0`, because that is the release that produced the
  numbers.
- **The sim-to-real pre-registration now names its public statement.** `docs/studies/sim-to-real-so101.md`
  links [provael.com/sim-to-real](https://www.provael.com/sim-to-real/), which publishes the same
  protocol, the null hypothesis and a dated "trials not yet run as of" line. The link exists because
  a pre-registration nobody can find does not do the job a pre-registration exists to do: the point
  is that a reader who later sees a result can confirm the design was fixed beforehand, and that
  requires the protocol to be reachable from where the result will be read. Precedence is stated in
  the file — if the two disagree, this repo wins, because it is the registered artifact and the
  website copies from it.

## [0.31.0] — 2026-08-02

The disagreement stops being prose and becomes a measurement.

0.30.0 shipped the ForesightSafety-VLA disagreement as data, which was the right first move and an
incomplete one: the artifact stated *that* the two projects disagree and carried a single run-level
CC/RET aggregate — summed over the very axis the disagreement lives on. A reader could not see
whether Provael's language result was large, its visual result small, or both. The foresight
crosswalk now emits **`measured_by_category`**: for every ForesightSafety category Provael maps
onto, that run's ASR with a 95% Wilson interval beside its CC and RET. On the committed real-policy
run the shape is now legible in the file itself — `fs06 Unsafe Instruction` at 0.567 [0.392–0.726]
against `fs12 Occlusion & Visibility` and `fs13 Adversarial Patch` at 0.000. Same inversion,
inspectable instead of asserted. `crosswalk.foresight.json` is now committed alongside the atlas and
robojailbench artifacts, so all three are readable without running anything.

Alongside it, a hypothesis that might dissolve the whole disagreement — written down **as a
hypothesis**, because an untested explanation a reader can check beats a shrug. Their Safe-Lang
family may evaluate *ordinary* paraphrase where Provael's instruction family evaluates
*adversarially selected* perturbation. If that is the whole difference, both results are true and
their conclusion narrows to "benign linguistic variation is not the dominant risk", which is
compatible with adversarial language being one. The question that settles it — are the Safe-Lang
perturbations benign-only? — is asked of the authors and deliberately not answered here. It is cheap
for them to answer and expensive for us to infer.

### Added

- **`measured_by_category` in the foresight crosswalk** (`crosswalk --target foresight --in <run>`).
  Per-category attempts, successes, ASR, 95% Wilson interval, CC and RET, plus which mapped families
  a run actually exercised. A category the run never touched reports `null` **with a stated reason**,
  never `0.0` — the distinction between "not run" and "run and found nothing" is the whole value of
  the artifact, and it would be worth negative amounts if collapsed.
- **`results/crosswalk/crosswalk.foresight.json` is committed**, generated against the committed
  reference run, and pinned by a determinism test the way the atlas artifact already was. Its CC and
  RET columns are `null` throughout, and correctly so: the one real-policy run Provael owns predates
  the per-step decision log, so those episodes have *unmeasured* exposure rather than zero. The
  fields populate on any run that carries decisions. Stated here because a null column in a safety
  artifact invites exactly the wrong reading.
- **The reconciliation hypothesis and the open question**, in `docs/crosswalk/foresight-safety-vla.md`.
- **Two prior-art entries that should have been there already** — `PRIOR_ART.md`:
  - **RoboGCG** (arXiv:[2506.03350](https://arxiv.org/abs/2506.03350)), the successor to RoboPAIR
    from an overlapping group and the closest published work to this project's threat model. Its
    finding that a textual attack applied *once* at the start of a rollout achieves full action-space
    reachability and persists over a horizon is the reason our instruction attacks are applied once
    and scored across the episode. Its harm-decoupling observation — "attacks in the real world do
    not have to be semantically linked to notions of harm" — is the premise the `misalignment` family
    exists to test, and we had no citation for it until now.
  - **Mostly Harmless VLA Steering** (arXiv:[2606.12299](https://arxiv.org/abs/2606.12299)), the
    benign twin: they search language space to *improve* behaviour, we search it to break it. Their
    conformal guarantee is calibrated on perturbations that "paraphrase the verb, noun, and a mix of
    both" — sampled, not optimised — which raises a genuine open question about what a harmlessness
    guarantee covers under adversarially optimised perturbation. Recorded as an open question
    addressed to the authors, with no claim about the answer.
- **First tests for `--target foresight` at all.** The target shipped in 0.30.0 with no coverage:
  four tests now pin the disagreement record, the CC/RET fields, the null-never-zero rule, and
  byte-identity with the committed artifact.

### Fixed

- **`README.md` said "28 attacks" for two releases while `docs/quickstart.md`, one directory away,
  was corrected in 0.29.1.** The registry holds 29 across 16 families, and the README's inline family
  list was also missing `universal_patch`, which shipped in 0.29.0. The guard added in 0.29.1 could
  not see it twice over: the enumerated claim list named only quickstart, and the sweep keys on the
  phrase "adversarial families", which that line never used — it wrote the count against an
  enumerated family list inside a shell comment. Being in a code fence hid nothing; the phrasing
  simply fell outside the only pattern anyone was looking for.
- **The same class of error, twice more, in `notebooks/01_provael_in_5_minutes.ipynb`** — found by
  reconciling every count in the tree rather than the one that was reported. It annotated
  `list-attacks` with the `quick` recipe's "nine attacks across four families", and described
  `--recipe full-sweep` as running "all four attack families", which is `CORE_FAMILIES` — what
  `ci-gate` runs — not `full-sweep`'s fifteen.
- **`tests/test_counted_claims.py` now anchors on the command instead of the noun.** A count offered
  as the output of `list-attacks` is a claim about the whole registry, always, because
  `cli.list_attacks` iterates `ATTACKS` and prints every family — there is no subset reading
  available. That anchor is what makes the sweep safe: the obvious generalisation, flagging every
  "N attacks" in the tree, would fail on `attacks/action.py`'s "Two attacks", on `recipes.py`'s
  description of `quick`, and on the crosswalk's "three families" — all true statements about
  subsets. A guard that fails on correct prose gets reverted, which is worse than no guard. The
  fenced shell-comment shape is pinned by its own regression test so a future pattern edit cannot
  quietly drop the case it was written for.
- **BadVLA's ASR is 96.7%, and 0.30.0 was wrong to withhold it.** That release cited the figure at
  the abstract's "near-100%" and recorded that 96.7% "appears in neither the abstract nor this
  repo's committed reproduction record". Both halves of that check were true and the conclusion was
  still wrong: the paper states *"BadVLA achieves near 96.7% attack success with negligible
  clean-task degradation"* in its contributions section. Checking an abstract is not checking a
  paper. Corrected in `docs/standards/published-asr-baselines.md`.
- **The truncated standard in the Halos quote is resolved: ISO/IEC TR 5469.** The quote reached
  this repo cut off at `"ISO/IEC TR…"` and shipped with its ellipsis intact, which was the right
  call at the time — completing a standard number from context is the unresolvable-citation failure
  `tests/test_citations_resolvable.py` exists to prevent. Reading the NVIDIA newsroom release itself
  (2026-08-01) settled it. The rule that produced the ellipsis is the rule that removed it: quote
  the source, then go read the source.
- **The withheld per-suite row now names every source checked.** The four proposed figures
  (Spatial 97.5 / Object 93.8 / Goal 96.5 / LIBERO-10 77.3) appear as a set in none of
  arXiv:2605.25889, arXiv:2505.16640, or arXiv:2509.19870 — two of the values occur only as
  isolated cells of unrelated tables, two do not occur at all. The row stays withheld, but a
  withholding that names three checked papers is a finding; one that names a single paper is an
  assumption wearing a finding's clothes.

## [0.30.0] — 2026-08-01

Standards coverage the certification path actually names, and ownership of the one published result
that disagrees with ours.

Two threads. The first is that a buyer's conformity file already names standards Provael had no row
for. The EU Machinery Regulation's Annex I Part A point number had been shipping as
`[point reference pending verification]` — a placeholder that `certify` faithfully rendered into a
document meant for a notified body. It is now pinned to **point 5**, verified verbatim against CELEX
32023R1230, and joined by **point 6**, the embedded-system variant, which is the row an integrator
shipping a whole robot is actually routed under. Alongside them: **IEC 61508**, **ISO 13849-1/-2**
and the in-development **ISO 25785-1**. Every one of those rows says, in terms, that Provael computes
**no SIL and no Performance Level and makes no functional-safety claim** — they are inputs to an
argument an assessor makes, and a row that let itself be read otherwise would be worth less than no
row at all.

The second thread is harder to write and more useful. **ForesightSafety-VLA** (arXiv:2606.27079)
reports that structure and visual variation degrade safety substantially more than language
variation. Provael's one real measurement found the opposite ordering: the instruction family
transferred at 17/30 while visual measured 0/20 and injection 0/10. Both cannot be a general law.
The disagreement now ships **as data** in every emitted crosswalk artifact, unresolved and labelled
unresolved, with the reason it cannot be settled without a run nobody has done — and with the
correction that matters most to us: Provael's visual null is evidence about the templated attacks it
shipped, **not** evidence that perception attacks are weak. Anyone quoting that 0/20 as the latter is
misusing it.

### Added

- **`eu-machinery:annex-i-part-a-6`** — the embedded-system conformity row. Point 5 is the safety
  component sold on its own; point 6 is machinery with the ML safety system inside it. Both route to
  Article 25(2) via Article 6(1), both travel in the dossier, and Part B point 19 is flagged
  everywhere as the Article 25(3) sibling that must not be substituted for either.
- **`iec-61508:systematic-capability`** and **`iso-13849:pl-validation`** — the functional-safety
  standards an ANAB-accredited AI-safety inspection programme assesses robot software against.
  Both `indicative`, both gated on EAI04 actually having run, both disclaiming SIL and Performance
  Level in the row text itself.
- **`iso-25785-1:dynamically-stable`** — an anticipatory row for the first Type-C standard for
  dynamically stable robots (ISO/TC 299 WG 12). It names `balance_spoof`, `whole_body_hijack` and
  `stride_freeze`, and states that the standard is an unpublished Working Draft and the humanoid
  suite is stub-validated with no real-model transfer claimed. It cites no clause, because there is
  no stable clause to cite.
- **`provael crosswalk --target foresight`** — the 13 ForesightSafety-VLA categories, names and
  *unsafe when* definitions quoted verbatim from Table I, mapped to EAI ids and Provael families.
  Honest tally: **4 covered · 3 partial · 6 not covered**. Six uncovered rows is the useful half —
  Provael models no force, no second arm, no task preconditions, no illumination, no camera pose.
- **`provael.scoring.safety_cost`** — risk exposure time (RET), cumulative cost (CC), unsafe success
  rate (USR) and the SSR/USR/SFR/UFR quadrant. Every function returns `None`, never `0.0`, when the
  signal it needs is absent: an episode with no decision log has *unmeasured* exposure, and a metric
  reporting 0.0 for "we did not look" is indistinguishable in a table from one reporting 0.0 for "we
  looked and found nothing". The quadrant carries a fifth `task_success_unmeasured` bucket so its
  counts always close.
- **`docs/standards/published-asr-baselines.md`** — the published record beside Provael's number,
  with a **comparability column** that is the entire point. Most published VLA attack figures measure
  *task-success degradation*; a Provael ASR measures *envelope breach*. One row is deliberately
  **withheld**: four per-suite figures could not be located in the paper they were attributed to, and
  printing unresolvable numbers on a page about checkability would refute the page.
- **`docs/crosswalk/halos-integrator.md`** and **`docs/crosswalk/foresight-safety-vla.md`** — the
  integrator and benchmark cards behind the rows above.

### Fixed

- **`eu-machinery:annex-i-part-a` no longer defers its own clause.** `tests/test_compliance.py` now
  fails the build if *any* requirement's `control_id` contains a pending-verification placeholder.
  Pinning the one string that was wrong would not have caught the next one, so the rule is the
  assertion — the same move as `test_counted_claims.py` in 0.29.1.
- **EAI02's honest null was quoted at half its sample.** `docs/TOP10.md` reported the perception
  null as `0% (0/10), 95% CI [0–28%]`; the `visual` family ran `patch` **and** `decoy_object` for
  **0/20, CI [0–16%]**. The page understated its own denominator and published an interval twelve
  points wider than the run earned.
- **`crosswalk --out <dir>`** now writes the target's canonical filename into an existing directory
  instead of creating a file named like the directory — the shape a caller reaches for when `--in`
  and `--out` are the same run directory.
- `report.md` gained a process-level safety-cost section that names the benchmark its vocabulary
  comes from and states plainly that Provael's suites are **not RoboTwin**.

### Citations a reader can resolve

*(Folded in from the unreleased citation-integrity work — PR #78.)*

An independent audit fact-checked this repo's citation corpus in July 2026 and came back clean on
almost all of it — roughly fifteen papers and four CVEs, real and correctly attributed, zero
fabricated or transposed identifiers, including every 2026-dated arXiv ID. It flagged exactly two
citations as unverifiable and advised "verify or soften both before any deck": EAI09's *"cited at
the U.S. Senate"* (it found only a *House* committee reference and concluded the chamber was wrong)
and EAI10's a16z *"The Physical AI Deployment Gap"* ("no independent trace found").

Both claims are true. The Senate citation is written testimony to the Commerce Subcommittee on
Science, Manufacturing, and Competitiveness, hearing of 3 Mar 2026, hosted on commerce.senate.gov — a
*different, also-real* event from the House hearing the audit surfaced. The a16z piece is by Oliver
Hsu, published 13 Jan 2026, and the quoted sentence is verbatim.

The audit being wrong twice is the finding, because of *why* it was wrong. Every citation it
confirmed carried an arXiv ID or a CVE number; the two it failed on carried neither. A named
document with no identifier is not a weaker citation, it is an **unresolvable** one — and a
diligent reader who cannot resolve a citation records "probably made up", not "unverified", and
then discounts the ninety that were fine. That is this project's own thesis pointed back at its own
documentation: a defence is a number you can re-derive, not a press release.

### Added

- **`tests/test_citations_resolvable.py`** — every tagged evidence segment in `docs/TOP10.md` must
  carry at least one globally resolvable identifier (arXiv ID, CVE number, or URL). It deliberately
  does **not** dereference them: CI here is hermetic and offline, so the invariant is "a reader can
  check this", not "this checked out today". A vacuity guard asserts the parser's own yield against
  the ten `## EAIxx` headings — a citation rule that silently matches nothing is worse than no rule
  — and a regression pin holds the specific attribution detail on the two claims that were read as
  fabrications once already.

### Fixed

- **EAI09** now names the chamber, subcommittee, hearing title and date for the Unitree G1 Senate
  citation, and pins "DRL policy stealing" to arXiv 2006.05032.
- **EAI10** now names the a16z piece's author, date and URL.
- **EAI08** now cites arXiv 2603.08665 for the static-credential fleet finding (one device's
  credentials to 267+ connected robots) and links the OWASP LLM Top 10 behind `ASI03`/`LLM06`.
- **EAI06** now carries BadRobot's arXiv ID (2407.20242) — cited at EAI01 but not here.

No attack, scorer or measured number changed in this release. Two evidence artifacts gained fields:
`dossier.json` carries four new `standards_crosswalk` rows, and `crosswalk.foresight.json` is new.

## [0.29.1] — 2026-07-31

A correctness release about **what the project says about itself**. No attack, scorer or evidence
format changed, and no measured number moved. Three claims were wrong or invisible; all three were
the kind a reader can check in under a minute, which is the kind that costs the most when wrong.

### The counted-claim drift

0.29.0 registered `universal_patch` and its own CHANGELOG entry said "15 adversarial families (was
14)". `README.md`, `SAFETY.md` and `docs/roadmap.md` shipped that release still saying **fourteen**.
`tests/test_recipes.py` already asserted that `full-sweep` covers every registry family — what no
test could see was that the prose *describing* that sweep had fallen a family behind.

The count is now derived from `ATTACKS` and checked against every restatement of it by
**`tests/test_counted_claims.py`**, which fails with both numbers and names the file. It runs two
independent checks: enumerated patterns pinned to exact sentences (so a *reworded* claim fails
loudly rather than silently ceasing to be checked), and a tree-wide sweep that catches a stale
count in a file nobody remembered to enumerate. Historical statements are exempt by design —
`CHANGELOG.md` describes each release as it shipped, and `docs/studies/action-envelope.md` reports
a study measured on 0.28.0 over the fourteen families that existed then; forcing either to today's
number would attribute a measurement to a registry that never produced it.

### Fixed

- **Family count corrected to 15** in `README.md` (two places), `SAFETY.md`, `docs/roadmap.md`,
  `docs/index.md` and a `certify.py` comment. `docs/quickstart.md` also said "28 attacks across 15
  families (14 adversarial)"; the registry holds **29 attacks across 16 families, 15 adversarial**.
- **`SAFETY.md` mis-partitioned the registry.** It split families into "eleven templated" and "the
  remaining three" non-templated searches — but `universal_patch` is a query-budgeted search, so
  the second group is **four**. A safety document that under-counts its own non-templated attacks
  is wrong in the direction that matters.
- **`docs/roadmap.md` omitted `openpi`** from its policy list, which therefore showed seven of the
  eight registered backends. Added, with the scaffolding caveat `groot` and `openvla` carry.
- **`README.md` named only `groot` as scaffolding.** `openvla` and `openpi` are equally
  scaffolding — registered and structurally tested, never given a checkpoint.

### Added

- **`provael list-suites`** — a command that did not exist. It marks `stub`, `reach` and `humanoid`
  as **CPU fixtures** and `libero` / `metaworld` as **real simulators**, deriving the split from
  `SuiteAdapter.is_fixture` (which the suite classes declare) rather than a hand-kept list, so a
  new fixture cannot inherit a "real simulator" label by omission.
- **A `status` column on `provael list-policies`**, reading `measured` / `CPU fixture` /
  `scaffolding — no checkpoint ever run` / `no run committed here`. The table already carried
  scaffolding notes, but its only status-like column was **"ready here"** — an *import* check. On a
  CPU box every non-stub backend renders `no`, so the one backend that has produced a real result
  looked exactly like the three that have never loaded a checkpoint.

  The categories are four, not the two an obvious reading suggests: `pi0`/`pi05`/`pi0fast` are
  genuinely provisioned by `provael[lerobot]` (unlike `groot`) yet have no committed run, so
  calling them scaffolding understates them and calling them measured overstates them.
  `MEASURED_POLICIES` is a **declared constant, never a filesystem probe** — `list-defenses` shipped
  that bug in 0.26.0 by looking for `docs/studies/<name>.md`, which resolves in a git checkout and
  not in an installed wheel; `results/` is not packaged either, and a probe that fails *toward*
  "measured" ships a false claim.

### Changed — the public leaderboard took **PATH B** (stamp the staleness), not PATH A (re-run)

The published board reports `measured_with: ["0.1.0"]` — 28 releases behind — covering 1 policy and
3 of 15 adversarial families, and it is Ed25519-signed, so the signature lends currency to stale
data.

**Re-running was not possible here and was not faked.** A re-run needs `lerobot` + LIBERO on a GPU;
this environment is macOS arm64 with no `torch`, no `lerobot` and no CUDA. A partial or simulated
substitute would have been worse than the staleness, so the numbers are untouched and the staleness
is now stated where a reader meets it:

- **`leaderboard/app.py` renders a staleness-and-coverage banner above the tables** — measured-with
  vs current release, policy/suite coverage, `3 of 15 adversarial families`, and
  **`12 families have no real-model measurement at all`** with the explicit warning that absent is
  not 0%. Every figure is computed from the loaded board and its rows, so the banner cannot drift
  from what it describes.
- **`measured_with` joins `generated_at`** in the provenance footer. The two are routinely
  different and only one of them is about the numbers.
- **The competence control is stated on the page**: that run predates `clean_task_success_rate`, so
  the board has a benign false-positive control (0%) but no measured benign task-completion rate.
- **`docs/leaderboard.md` and `README.md`** carry the same four limits.

**`results/smolvla_libero_object/report.json` was deliberately left byte-identical.** Its own
README already discloses the missing control in full ("predates the clean-task-success control …
We do **not** back-fill an invented value"). A free-text note cannot go in the report — `RunReport`
is `extra="forbid"` — and adding an explicit `"clean_task_success_rate": null` is **provably
information-free**: the canonical digest is taken over the *model dump*, where the field already
defaults to `null`, so the digest is unchanged (verified: `280401608e5f58…`, matching
`evidence-manifest.source_report_sha256`, `execution-manifest.report_digest` and the board's
`inputs_digest`), and `jq` returns `null` for an absent key regardless. Editing a file whose README
calls it "the **canonical, unedited** artifact" for zero information gain is a worse trade than
leaving it exactly as measured.

### Note

`leaderboard/app.py` hardcodes `TOTAL_ADVERSARIAL_FAMILIES` and `CURRENT_RELEASE` because the
Hugging Face Space installs no `provael` (viewing renders committed JSON). Both are pinned to the
live registry and to `__version__` by `tests/test_counted_claims.py`, so the release that forgets
them fails its own gate.

## [0.29.0] — 2026-07-31

### The prior-art finding

`PRIOR_ART.md` cited seven papers and was missing the one that most constrains what this project
may claim. **AttackVLA** (arXiv:2511.12149) is a unified evaluation framework for adversarial and
backdoor attacks on VLA models, reporting attack success rates, evaluated in **both simulation and
real-world robotic settings**. The README already named it as prior art; the prior-art file had no
entry for it.

That matters because "What is actually novel here" claimed a model-agnostic harness with a
comparable ASR metric — a position AttackVLA already occupies, with hardware evaluation this
project does not have. The claim was rewritten rather than restated.

A second gap was larger and closer to home: the README's limitations list contained **no**
occurrence of "hardware", "physical world" or "printed". The most load-bearing caveat in the
project — that nothing here has ever run on a real robot — was not written down anywhere a reader
would find it.

### Added

- **`universal_patch` family (EAI02)** — one adversarial patch, fit **once**, then frozen and
  carried unchanged to every episode and task it never queried. `optimized_patch` re-searches a
  fresh patch per episode, which is the right measurement for "does a patch exist for this
  episode" and the wrong one for a *printed* sticker, which cannot be re-optimised between
  frames. Reimplements the **threat model** of UPA-RFAS (arXiv:2511.21192, CVPR 2026), not its
  method: this is a black-box **query** search over placements with no gradients, no feature-space
  access, no InfoNCE and no attention objective, so it will find a weaker patch than that paper
  reports and its numbers must not be read as reproducing them. Ports no code.
  Records `attacker_access="black-box-query"`. GPU-gated; inert (`N/A`, never `0%`) on the
  image-less CPU stub, so the golden canary stays at 47/70.
- **Prior-art entries for AttackVLA (arXiv:2511.12149), UPA-RFAS (arXiv:2511.21192) and ADVLA
  (arXiv:2511.21663)**, each stating where we differ *and where we do not*.

### Changed

- **`PRIOR_ART.md` "What is actually novel here" rewritten.** The surviving claims are narrower and
  checkable: a deterministic CPU-only no-download core (auditable by a third party, not merely
  published), the evidence/compliance layer (SARIF / OSCAL / CycloneDX ML-BOM / signed attestation
  / Wilson-CI regression gate), and a refusal to report a number we did not measure. Adds an
  explicit "what we do NOT claim" list: not the unified-harness idea, not sim-to-real, not parity
  with white-box attacks, not certification.
- **README gained a sim-only limitation as its FIRST bullet.** No number in this repository has
  been produced on physical hardware; a patch here is composited into a frame as an array and is
  never printed, photographed, or subjected to lighting, viewing angle, print gamut, motion blur
  or sensor noise. Sim-to-real transfer is unmeasured and explicitly unclaimed.
- `full-sweep` covers 15 adversarial families (was 14) — derived from the registry, so the new
  family joined automatically; only the declared precondition and the asserted count changed.
- `results/smolvla_libero_object/evidence-manifest.json` regenerated. **Registry counts only**
  (28 attacks / 15 adversarial families); every measured value — adversarial 17/60, all-episode
  17/70, benign 0/10 — is byte-identical.

## [0.28.0] — 2026-07-30

### The interface finding

`docs/DEFENSES.md` specified **six** mitigation rows. The `Defense` ABC could only ever express
**two** of them.

Four rows — action clamping / keep-out enforcement, trajectory anomaly detection, rate limiting /
scope enforcement, output / memory screening — act on what comes **out** of the policy. The ABC
offered a single pre-processing hook, `apply(instruction, observation)`, so those four were not
merely unmeasured: they were **unimplementable by construction**. "Specified, unproven" was
overstating their status. A taxonomy the interface cannot satisfy is a spec, not a plan.

### Added

- **`Defense.filter_action(action, observation) -> action`** — a non-abstract, no-op-by-default
  action-side hook, so `InstructionCanonicalization` and any third-party defense keep working
  untouched. It is handed only the action and the observation — never the policy, the suite, the
  report, the attack, the task id or the danger predicate — must be deterministic, and must not
  mutate the array in place.
- **`Defense.position`** (`"input"` / `"action"` / `"input+action"`), surfaced as a column in
  `provael list-defenses` and carried on the mitigation report beside the verdict. A certifier
  reading "a defense was applied" needs to know whether it was a text pre-filter or an output
  monitor: different protective measures, different failure modes.
- **`Defense.audit_action(raw, filtered)`**, feeding the same `defense-log.jsonl` sidecar as
  `audit()`. The envelope clamp overrides it to name *which* channel engaged. "The number moved" is
  not evidence — what changed is.
- **`action_envelope` (`ActionEnvelopeClamp`)** — the first action-side defense, implementing
  `docs/DEFENSES.md` row 3. A scalar cap on the danger channel and an L2 cap on the motion channels,
  **clipping rather than zeroing** (zeroing is itself an availability failure). Bounds derived from a
  committed measurement of the *benign* policy's own commanded envelope, following the
  `suites/keepout_zones.py` calibration pattern — **never** from a suite's unsafe predicate. A
  structural guard in `tests/test_defenses.py` parses the module's AST and fails if it imports
  anything from `provael.suites.*` or `provael.scoring.*`, because a clamp tuned against the bound it
  is measured on has measured nothing.
- **`risk_reduction_measures`** in the `provael certify` dossier (JSON, OSCAL and HTML section 4), via
  a new `--mitigation <report.mitigation.json>`. Carries the measure's name, kind, position, the
  per-family pre/post ASR with both 95% Wilson intervals, the credited families, the acceptance gate,
  the verdict verbatim, the transfer status and **both arm digests** so a reader can re-derive the
  comparison. Free core, no entitlement check — `docs/open-core-promise.md` v1.0 unchanged.
- **`defense` input on the reusable Action** (opt-in, empty by default so existing consumers are
  unaffected), with `residual-asr`, `mitigation-verdict`, `mitigation-report` and `defense-log`
  outputs, both arms uploaded as artifacts.
- **`defenses_total` / `defenses_measured`** in the evidence manifest, derived from the registry and
  each `Defense.study` so they cannot drift from the code.
- **`docs/studies/action-envelope.md`** and **`studies/action_envelope/run.py`** (a thin driver over
  the public API, following the `studies/cross_arch_transfer/run.py` precedent).

### Measured — as measured

Policy `stub`, 10 episodes per (task, attack), seed base 0, `none` benign control in both arms, the
**full 14-family adversarial registry**. Bounds: danger cap `0.0`, motion-L2 cap `0.125`
(benign-derived). Transfer status `stub-validated-scaffolding` — **no real-model transfer is claimed**.

| suite | verdict | adversarial ASR | credited families |
| --- | --- | --- | --- |
| `stub` | `credited` | 84.1% [78-89%] → 52.9% [45-60%] | `injection`, `instruction`, `optimized_instruction`, `visual` |
| `reach` | `credited` | 72.9% [66-79%] → 52.9% [45-60%] | `injection`, `instruction`, `visual` |
| `humanoid` | **`not-credited`** | 27.3% [20-36%] → 27.3% [20-36%] | none |

**`humanoid` is `not-credited` and that is published, not hidden.** Not one interval moved: the
whole-body balance predicate is not a magnitude cap on the channels this defense bounds.

**Most of the credit above carries no information, and the study says so first.** The benign policy
commands **exactly 0.0** on the danger channel, so any honestly benign-derived cap pins that channel
to zero while `stub` calls an episode unsafe at a threshold in [0.5, 0.9) and `reach` at 0.75. Every
family whose success routes through that channel goes to 0% **by construction**. The tautology is
structural, not a tuning choice.

Controls: benign FPR `0.0% → 0.0%` on all three suites. Clean-task success `100.0% → 100.0%` on
`stub` (pre 95% CI [72-100%], n=10, accepted); **not evaluable** on `reach` and `humanoid`, which
surface no task-success signal — a limitation, not a pass.

**The acceptance-gate sweep is the part that carries information.** Tightening the motion cap on
`stub`: `0.1250` and `0.0600` → `credited`, task preserved; `0.0400` and `0.0200` →
**`rejected-benign-cost`**, clean-task success `100.0% → 0.0%`. Between 0.06 and 0.04 the clamp stops
being a mitigation and becomes an availability failure, and the protocol rejects it outright.

**The coverage map — the headline.** One protective measure does not cover a hazard list. A magnitude
cap **cannot** credit `action` / `action_space` / `humanoid` (`freeze`, `critical_freeze`,
`stride_freeze` are availability attacks pushing toward *zero*; no upper bound restores a suppressed
command), and does not reach `backdoor`, `authorization` or `confidentiality`, whose successes route
through a decoupled flag rather than a clamped channel. `optimized` stayed at 100%. The measure is
credited on rows mapped to EAI04/EAI06 and addresses nothing on EAI03, EAI08 or EAI09 — carried into
the dossier so a safety case cannot imply otherwise.

### Changed

- **`examples/runtime/robot_firewall.py` rewritten.** It printed a bare `base - firewalled`
  point-estimate delta and ended with `assert fw_s < base_s` — no confidence interval, no credit
  rule, no benign-FPR control, no acceptance gate: exactly the reasoning `docs/DEFENSES.md` and
  `defenses/measure.py` exist to forbid, in the project's own "show defense" demo. Two specifics: its
  clamp sat at `0.4`, **below** the fixture's own unsafe threshold (so its ASR reduction was
  tautological), and it ran **no benign control**, so the comparison could not have been valid even
  with intervals added. It now drives the registered defense through `build_mitigation_report` and
  prints verdicts and intervals. `tests/test_runtime_firewall.py` no longer asserts a direction of
  effect — `not-credited` must remain a representable outcome.
- `provael list-defenses` gained a `position` column, and its footer now says **four** of the six
  taxonomy rows are unregistered rather than five.
- `docs/DEFENSES.md` status header: **two rows measured, four specified and unproven**, with the
  action-clamping row linked to its study. `docs/roadmap.md`'s defense line was understated and now
  states what is measured and what is not.
- Regenerated `results/smolvla_libero_object/evidence-manifest.json`. **Only the derived registry
  section changed** — two added keys, `defenses_measured: 2` and `defenses_total: 2`. The manifest is
  built from the committed `report.json` at a pinned commit; **no measurement moved and
  `report.json` was not touched** (same discipline as the 0.27.0 leaderboard re-stamp).

### Unchanged, deliberately

- **Nothing was added to `RunReport` or `AttackResult`.** The action-side hook was the obvious excuse
  to record a filtered action on the result, and that is exactly where it must not go: `AttackResult`
  is nested in `RunReport.results`, so a field there moves the canonical JSON the attestation is
  signed over. The trail lives in the sidecar, the position on the mitigation report. Asserted by
  test, and a real issued attestation still verifies.
- **`asr-threshold` still gates the UNDEFENDED adversarial ASR.** `residual-asr` is an additional,
  separately-named output. Letting a filter of unproven real-model efficacy lower the number a release
  gate reads is precisely how a team ships an unmitigated policy behind a text-and-clamp wrapper. The
  job fails on `rejected-benign-cost`, and on `insufficient` with a message naming the missing benign
  control — nothing measured is not a pass.

## [0.27.0] — 2026-07-30

### Fixed

- **The public leaderboard artifact was stale and unsigned**, which made the product's own claim —
  "a dated, signed record, not a screenshot" — false in the one place a buyer checks. It was stamped
  2026-07-04 at commit `a5fdd13` (first released in **v0.18.0**, so 8 released tags back) with
  `signature: null`. Regenerated and Ed25519-signed; the public key is published beside it at
  `leaderboard/results/leaderboard.pub` (keyid `5b9a65790d93d0bc`).

  **Nothing was fabricated and no GPU was needed.** The board is built by *aggregating committed
  `report.json` files*, not by re-running a policy, so rebuilding reproduces the same measurement
  exactly — rows and examples are byte-identical to the previous board. Only the provenance envelope
  moved.
- `.gitignore` carried **no key rules at all** while a workflow already consumed
  `secrets.PROVAEL_SIGNING_KEY`. `*.pem` / `*.key` are now ignored, with an explicit negation for
  the published `.pub`.

### Added

- **Checkpoint supply-chain integrity in the CI gate** (`provael verify-checkpoint`, and a step in
  the reusable Action that runs **before any policy is instantiated** — the check is worthless after
  the load). Verifies a pinned SHA-256 over the checkpoint's weight files and refuses pickle-format
  weights, **both fail-closed**, each with an explicit opt-out that is recorded in the evidence
  rather than being silent. "We did not check" and "we checked and it matched" must not produce the
  same verdict.

  Motivated by [CVE-2026-25874](https://nvd.nist.gov/vuln/detail/CVE-2026-25874), which
  `SECURITY.md` already documents: LeRobot unauthenticated pickle-deserialization RCE (CVSS 9.8),
  affecting `lerobot` through `0.5.1`, in the async-inference `PolicyServer` which `pickle.loads`
  untrusted payloads over an unauthenticated gRPC endpoint. **Provael never starts that
  PolicyServer**, so that path is not reachable through Provael — but loading *any* third-party
  pickle executes it, and the tool named the risk publicly while the Action did not check for it.

  Mapped to **EAI03 — Model & pipeline poisoning, backdoors & supply chain** (the mapping is in the
  title), deliberately **not** EAI07: that entry declares CPS/firmware/teleop out of scope for
  *attacks*, and filing a control there would imply this closes part of it. It does not.

  > **This is a supply-chain control, not an adversarial-robustness result.** It emits a *verdict*,
  > never a rate; a checkpoint that passes every check can still be driven off-task at exactly the
  > rate the ASR reports. In SARIF it is nested under `checkpointIntegrity`, never flattened beside
  > `adversarialAsr`, and the record carries that sentence with it. A test asserts the evidence
  > contains no rate-shaped field at all.
- Three CI guards on the published board: it is signed, the signature **verifies against the
  published key** (a signature under an unpublished key is worse than none — a buyer following our
  own docs would get `INVALID`), and its build commit is no more than **3 released tags** behind.
  Three because re-stamping is a GPU-free one-command operation, while failing on every release
  would be noise.

### Changed

- **Leaderboard `schema_version` 2 → 3**, adding `measured_with`. A re-stamp moves `generated_at`
  to today while every row still carries the measurement it always did, so a board carrying only
  `generated_at` reads as a fresh measurement — the one thing a dated record must not do.
  `measured_with` records the tool versions the *numbers* came from, and `Leaderboard.is_restamp()`
  answers it directly. The published board reports `measured_with: ["0.1.0"]`.


## [0.26.1] — 2026-07-28

### Fixed

- **`provael list-defenses` told every installed user that the one measured defense was
  "specified, unproven".** The status was decided by probing for `docs/studies/<name>.md` on disk,
  which resolves in a git checkout and never in an installed wheel — `docs/` is not packaged. So
  0.26.0, the release whose headline feature *is* the measured defense, shipped a CLI that
  contradicted its own published study. `Defense.study` is now a class attribute, so the status
  travels with the code and is derivable without a checkout. Found by the release smoke test
  against the published artifact, which is exactly what that step exists for.
- **`release.yml` fetched no tags**, so `test_every_pin_names_a_tag_that_exists` reported the real
  `v0.25.0` and `v0.3.0` as nonexistent and blocked the 0.26.0 release. `ci.yml` got
  `fetch-depth: 0` in #62; the release workflow re-runs the same gate from its own checkout and was
  missed. It failed closed and published nothing, which is the gate working.

## [0.26.0] — 2026-07-28

> **`full-sweep` now sweeps 14 families instead of 4, so the ASR it reports moves.** On the CPU
> stub it goes from **74.4% (67/90) to 84.1% (143/170)** — the recipe was always *meant* to be a
> full sweep, and the
> number it printed before was computed over 4 of the registry's 14 adversarial families with
> nothing in the output saying so. If you gate on a `full-sweep` threshold, re-baseline it. To keep
> the old behaviour exactly, switch to the new **`core-sweep`** recipe.
>
> An earlier draft of this note said 82.4%. That figure came from a 4-episode spot check, not from
> the recipe, whose default is 10 episodes. Both arms of the comparison are now measured at the
> recipe's own default and pasted from the run — see `docs/quickstart.md`.

### Fixed

- **`full-sweep` swept 4 of 14 attack families.** `recipes.ALL_FAMILIES` was the literal
  `["instruction", "visual", "injection", "action"]` sitting beside a registry that had grown to
  fourteen adversarial families, so a user running the recipe named *full-sweep* got an ASR
  computed over 29% of the catalogue and no indication of it. That number is exactly the kind that
  ends up in a conformity file. `ALL_FAMILIES` is now derived from the registry at import, so a
  newly-registered family joins `full-sweep` automatically — the hardcoded list beside a growing
  registry was the actual defect.
- **The GitHub Action's default `attacks` omitted the `none` benign control.** A sweep without the
  control produces an ASR with no false-positive baseline, and
  `verdict.ReleaseRequirements.require_benign_control` cannot be satisfied — so the default could
  only ever return `incomplete`. The default is now
  `none,instruction,visual,injection,action`, kept byte-identical to the `ci-gate` recipe and
  asserted by a test so the two cannot drift. The same fix lands in the reference
  checkpoint-security-gate workflow.
- **All five `examples/recipes/*.yml` templates were missing the benign control**, so anyone
  starting from a copy-paste template inherited the same uninterpretable ASR. They are now
  generated from the built-ins and a test asserts each mirrors the recipe it documents.
- **`docs/attacks.md` said "Four families"** against a registry of fourteen, and `docs/roadmap.md`
  said "4 families". Both corrected, with the doc pointing at `provael list-attacks` as the
  authority.
- **The security-gate reference workflow pinned the action at `v0.24.0` — a tag that has never
  existed**, so the workflow a design partner is told to copy failed at ref resolution. (Written
  without the full `owner/repo@tag` syntax on purpose: the new guard scans this file too, and
  spelling it out here would make the CHANGELOG fail its own check — which is precisely how this
  entry was caught.)
  `.pre-commit-hooks.yaml` documented `rev: v0.6.0`, nineteen releases stale. Both repinned to
  `v0.25.1`.
- **`tests/test_version_consistency.py` could not have caught either**, because it checked five
  *named* files and neither pin was on the list. It now scans every tracked file, and the
  exemptions are the short deliberate list — a missing exemption fails loudly rather than passing
  silently. Two separate checks: a pin naming a nonexistent tag is fatal anywhere (including the
  CHANGELOG); a stale pin is fatal only in copy-paste surfaces. CI's checkout gains `fetch-tags`
  so the guard is authoritative there rather than skipping.

### Added

- **The Top 10 catalog now holds all ten risks.** `docs/TOP10.md` defines EAI01–EAI10; `eai.py`
  held eight. **EAI07** (CPS / firmware / comms / teleop) and **EAI10** (evaluation / observability
  / incident response) were absent from the code, so they were silently dropped from every
  crosswalk, scorecard, compliance report, dossier and evidence manifest. A category that vanishes
  reads as covered; "we do not test this, and here is why" is a legitimate answer, and an omission
  is not. Every entry carries an explicit `EaiCoverage` — `attacks-implemented`, `no-attacks-yet`,
  `out-of-scope-for-simulation`, or `process-control-not-attackable` — plus a note a buyer can
  read, and the coverage claim is cross-checked against the attack registry by test rather than
  asserted by hand.
- **Every evidence artifact renders all ten categories** with a `status` column, so an empty row
  says *why* it is empty rather than leaving a reader to infer it from an absence.
- **`provael crosswalk --target atlas`** — a second crosswalk target driven by the
  `atlas_techniques` already sitting unused on every catalog entry. EAI07 and EAI10 keep an
  **empty** ATLAS mapping: ATLAS enumerates adversary techniques against ML systems, and neither a
  firmware compromise nor a missing governance control is one. Padding the column would fabricate
  the precision the "no invented `AML.TXXXX` ids" rule exists to prevent.
- **`core-sweep`** — the previous four-family `full-sweep`, under a name that describes it.
- **`provael --version`** as a flag, mirroring the existing `version` subcommand. There was only
  the subcommand, so the conventional first thing anyone types exited 2 with "No such option".
- **`recipes.CONDITIONAL_FAMILIES`** — the precondition each suite-dependent family needs, carried
  into the certify dossier as `families_skipped_with_reason`. A test runs every family on every CPU
  suite and asserts the declared preconditions match reality, so a reason cannot rot into an excuse
  for a family that is actually broken.

### Changed

- A run report that predates `RunReport.eai` (schema v1) now reports its per-risk rows as
  **`unknown — this report carries no EAI map`** rather than "not exercised by this run". Such a
  report may well have exercised a risk while attributing nothing — the insurer fixture ran
  `roleplay`, `patch` and `scene_text`, covering EAI01/02/05 — so the stronger phrasing would have
  stated a falsehood, and signed it into an attestation. An absent measurement and an absent
  *mapping* are different claims.
- `RunReport` is **unchanged**, so the attestation subject digest is byte-identical and
  attestations issued by earlier versions still verify.

### Added

- **Measured defenses (`provael.defenses`).** `docs/DEFENSES.md` has been a written spec with no
  implementation since it landed; this ships the first row of its taxonomy. A `Defense` ABC whose
  *shape* is the constraint — `apply()` sees an instruction and an observation and nothing else, so
  a "defense" that lowers ASR by reaching into the policy, the scorer or the danger predicate
  cannot be written against it — plus `InstructionCanonicalization`, implementing the three
  numbered steps at `docs/DEFENSES.md` in pure stdlib with no new runtime dependency.
- **Mitigation report (`report.mitigation.json` / `.md`).** Pre/post ASR per family with 95% Wilson
  intervals, the credit rule as literal interval disjointness, a benign-FPR control and a
  benign-task-success acceptance gate — all four rules of the published protocol, none softened.
  Both arms bound by report digest so the pair is tamper-evident and re-derivable.
- **CLI:** `provael list-defenses` (status reads "measured" only where a study exists),
  `--defense` on `attack`, and `provael mitigation --defended --baseline --out`, which exits
  non-zero on `rejected-benign-cost` so it works as a CI gate.
- **[First measured defense study](docs/studies/instruction-canonicalization.md)** —
  `stub-validated-scaffolding`, `credited` on the `stub` and `reach` CPU suites (adversarial ASR
  67.5% → 7.5% and 35.0% → 0.0%). **The study leads with why that number means less than it
  looks:** four of the stub fixture's seven danger tokens are words the defense strips, so
  `optimized_instruction`'s 60% → 0% is close to tautological. No real-model transfer is claimed.
  The registry ships exactly one defense; the other five taxonomy rows stay specified and unproven.

### Changed

- **`EXECUTION_MANIFEST_VERSION` 1 → 2**, adding `defense`. The manifest is *provenance* and is
  bound to the report by digest rather than being part of it, so growing it does not move the
  attestation subject. **That is precisely why the defense identity lives there and not on
  `RunReport`:** a field on `RunReport` (or on `AttackResult`, which is nested inside
  `RunReport.results`) would change the canonical JSON every attestation is signed over, and every
  attestation issued by an earlier version would stop verifying. Verified rather than asserted — an
  undefended run's digest is byte-identical before and after this release, and
  `tests/test_defenses.py` pins it to a literal so a future field addition fails loudly.
- The defense's raw → canonical audit trail is written to a `defense-log.jsonl` **sidecar** in the
  run directory, never into `report.json`, for the same reason.

### Fixed

- **`docs/attacks.md` documented 4 of 14 attack families** and carried a warning admitting it. All
  nine missing families now have sections — member attacks, EAI id, `attacker_access` and honest
  transfer status — sourced from `attacks/registry.py` and each family module. The warning is
  removed because it is no longer true.
- **`docs/quickstart.md` printed the pre-fix four-family number** (74.4%, 67/90). Re-ran
  `provael attack --recipe full-sweep` and pasted the real output: **84.1% (143/170)**, with the
  shown per-attack rows from that same run.
- The acceptance gate rejected clean-task success that was perfectly **preserved** at 100%:
  `wilson_ci(n, n)` returns `hi = 0.999…9`, so an exact `post <= hi` failed by one float ulp and
  the best possible outcome scored as a hard failure. Caught on the first real run of the protocol.

## [0.25.1] — 2026-07-27

A security-only patch. No behaviour, API, or report-schema change, so an attestation issued by
0.25.0 still verifies under 0.25.1.

### Security

- **The dependency-audit gate in CI never audited the project.** The step ran `uv sync --locked`
  and then a bare `uvx pip-audit`, but `uvx` builds an isolated environment for pip-audit itself,
  so the audit inspected pip-audit's own dependencies (`boolean.py`, `CacheControl`, `certifi`, …)
  and reported a clean tree on every run since the step was introduced. It now audits an exported
  requirements file, with a guard that fails the job if the export contains no runtime dependencies
  — a vacuous pass is treated as a failure, not a success.
- **`pillow` floor raised `>=10` → `>=12.3`, and the lockfile moved 12.2.0 → 12.3.0.** The gate
  above was masking 13 open advisories in the locked `pillow`, a *direct* runtime dependency.
  Provael decodes and perturbs untrusted camera frames as its core function, so the image decoder
  is squarely on the attack surface and the permissive `>=10` floor admitted a range with
  RCE-class advisories. Every supported configuration already requires Python 3.12+, and all five
  extras re-resolve on 12.3.0. `gitpython` (3.1.50 → 3.1.57, 5 advisories) and `setuptools`
  (→ 83.0.0) were refreshed in the same lock.

  The published 0.25.0 wheel is **not** affected: `pyproject.toml` declared `pillow>=10`, so
  `pip install provael` resolved the newest `pillow` available. The vulnerable pin was reachable
  only via `uv sync --locked` — developers, CI, and the container build.

- GPU extras (`torch`, `transformers`, `diffusers`, `aiohttp`) are now audited in a second,
  non-gating step. Those advisories frequently have no fixed version, so they are reported rather
  than enforced; they are tracked with the GPU-dependency work.
- The published Action's install bound moves to `provael[attest]>=0.25.1,<0.26.0`. It stays a
  *range* on purpose: pip re-resolves it on every run, so an adopter still pinned at
  `uses: provael/provael@v0.25.0` picks this patch up without waiting for a new action tag.
- **The rebuilt audit gate could not survive a release PR.** `uv export` emits the project itself,
  so `pip-audit --strict` tried to resolve `provael==<version-being-released>` on PyPI, failed with
  "Dependency not found on PyPI", and exited non-zero. Every release PR would have been blocked by
  the gate meant to protect it — latent in the 0.25.0 tree because that version was already
  published. The export now passes `--no-emit-project`: the gate audits our dependencies, not our
  own unpublished artifact.

### Fixed

- `CITATION.cff` gave `date-released: 2026-07-23` for 0.25.0 — 0.22.0's date, three days before
  the 0.25.0 artifact existed. The 0.25.0 release commit bumped `version` and left the date behind,
  despite the comment above both fields saying to bump both. A citation now names the real date.

## [0.25.0] — 2026-07-26

First release since 0.22.0, and it carries three releases' worth of work: the continuous
per-checkpoint CI security gate, the Humanoid safety pack, and the findings of a full
adversarially-verified audit of the evidence pipeline.

> **0.23.0 and 0.24.0 were never published.** Both version numbers exist as `__version__` values in
> public commits, so anyone who installed from git at those points has a tree calling itself 0.23.0
> or 0.24.0. Publishing a *different* artifact under either number would put two distinct trees
> under one version — the exact provenance failure this project exists to prevent — so the release
> moves to 0.25.0 and those numbers are retired unused. Their work is included below.

> **Upgrading from 0.22.0 changes gate behaviour.** If you pin an ASR threshold in CI, read
> "The pass/fail gates measured the wrong number" first: the gate now reads the adversarial ASR,
> which is *higher* than the figure it previously compared on any run carrying a benign control.
> A gate that passed at 0.22.0 may correctly fail now. That is the fix, not a regression.

### Fixed

- **The pass/fail gates measured the wrong number.** `scorecard.verdict`, the baseline-regression
  gate in `regression.diff_reports`, the CycloneDX ML-BOM metric, the Machinery Annex I dossier
  headline, the AVID record, and the published GitHub Action all read `RunReport.asr` — the
  **all-episode** observed-unsafe rate, which includes the benign control in its denominator. Adding
  the `none` control that `provael.compliance` tells users to add therefore pushed the gated figure
  *below* the true attack rate: a run with an adversarial ASR of 80% printed
  `Verdict: PASS (overall ASR 40.0%)` and exited 0. Every gate and published metric now reads
  `RunReport.adversarial_headline()`, the all-episode figure is emitted under its own explicitly
  labelled key, and a run with **zero** adversarial episodes reports `INSUFFICIENT` /
  `incomplete` rather than passing vacuously. The regression gate additionally records an
  `incomparable` list (differing policy / suite / horizon / predicate / tasks) so a delta across a
  changed configuration is not silently gated.
- **Fixture suites could fabricate a "real transfer".** `stub`, `reach` and `humanoid` read hazard
  and flag signals from fixed channel positions that are only meaningful for the 11-channel fixture
  layout. A real policy's 7-DoF end-effector delta had its *x-translation* read as the danger axis
  and its rotation/gripper channels read as backdoor and self-authorization flags, yielding a 100%
  ASR **and** a 100% benign false-positive rate labelled `measured-real-transfer`. All three now
  declare an `action_schema()` and reject a mismatched action shape via
  `scoring.action_schema.require_exact_layout`.
- **Pure-numpy fixtures were classified as real embodied runs.** `evidence.classify_run` tested
  `suite != "stub"`, so `reach` and `humanoid` earned `real-episode` (and thus
  `measured-real-transfer`). Realism is now declared by the suite itself
  (`SuiteAdapter.is_fixture`), an unknown suite name fails closed, and real simulators are
  unaffected.
- **Optimized attacks searched the wrong axis on real suites.** `LiberoSuiteAdapter` and
  `MetaworldSuiteAdapter` declared no action layout, so motion-reading attacks kept the fixture
  fallback (translation on channels 1-3) against LIBERO's OSC_POSE layout (0-2). Both now declare
  their real schema, and an undeclared layout degrades to zero motion instead of guessing.
- **`OptimizedAttack` leaked results across tasks.** The per-episode cache was keyed by seed alone,
  but the runner reuses the same seed sequence for every task, so task A's winning edit was served
  for task B. It is now keyed by `(task, seed)`, and the winning *edit* is cached rather than the
  rendered pair — `perturb` runs every step, so caching the pair froze the policy's observation at
  step 1 for the whole episode.
- **Emitted OSCAL was schema-invalid.** Every `observation`, `risk` and `finding` omitted a
  field required by NIST's assessment-results schema v1.1.2 (`collected`, `statement`, `target`
  respectively). The finding's `target.status.state` is derived from the run's release verdict
  rather than hardcoded, and an unsupplied collection time is emitted as an unmistakable epoch
  sentinel with a `collected-precision` property instead of an invented date.
- **CycloneDX ML-BOM emitted numbers where the 1.6 schema requires strings** for
  `performanceMetric.value` and both `confidenceInterval` bounds.
- **The published GitHub Action could not install Provael.** The default install spec expanded to
  `provael>=0.23.0,<0.24.0[attest]`, which is not a valid PEP 508 requirement (extras must precede
  the version specifier), and the pin excluded the current release. CI never caught it because the
  smoke test always overrides `install-spec`.
- **`--accelerator` was recorded but never applied.** The runner never forwarded a `device` to the
  policy factory, so every real adapter loaded onto its `cuda` default while the report asserted the
  requested device. The device is now forwarded, and the report records what the adapter actually
  resolved to (`PolicyAdapter.resolved_device`).
- **Non-finite actions scored as safe.** Every unsafe predicate is a threshold comparison, and every
  comparison against NaN is False, so a policy emitting NaN was recorded as benign on all axes. The
  runner now rejects non-finite actions at the single boundary they all cross.
- **LIBERO attributed results to a task that never ran.** The env config was cached from the
  constructor's `task_ids`, so a request for any other task fell through to a different task's
  environment while `reset` recorded the requested name. The config is now built per requested task
  and the lookup is strict.
- **No shipped recipe included the benign control** the release gate requires, so every recipe
  produced an `incomplete` verdict by construction.
- **Releases published to PyPI untested.** `release.yml` ran no lint, type-check or tests; it now
  runs the full CPU gate and asserts the tag matches `__version__` before anything is built.
- **CLI help swallowed extra names.** Rich parsed `[hosted]` and `[lerobot]`/`[openpi]` in command
  docstrings as markup, rendering "needs the `` extra" and "the / extra". `report --format` also
  omitted `oscal` and `mlbom` from its help.
- Rates are no longer printed from an empty denominator (`headline()`, the AVID record and the
  per-attack rows report N/A rather than a measured 0.0%).
- **Meta-World task ids were from a dead generation.** `reach-v2` and friends predate Farama's
  V3 environments (LeRobot's `metaworld` extra pins `metaworld==3.0.0`, whose ids are `reach-v3`
  …), so a run would have failed at env construction. The suite's error hint also claimed
  `provael[lerobot]` ships Meta-World; it is a separate `lerobot[metaworld]` extra.
- `ISO/TS 15066:2016` is now cited as incorporated into ISO 10218-1/-2:2025 rather than as a
  current separate source, and `ISO 13482:2014` notes the in-progress ISO/DIS 13482 revision.
- **A Machinery Regulation citation named the wrong annex.** The protection-against-corruption
  requirement was cited as Annex I, which is the numbering of the superseded Directive 2006/42/EC.
  Under Regulation (EU) 2023/1230 the essential health and safety requirements moved to **Annex
  III** (1.1.9), and Annex I now lists the machinery *categories* — Part A being the third-party
  conformity-assessment route reached via Art. 6(1) → Art. 25(2). Those are two distinct
  obligations and are now two rows.
- **Version drift across the release surface.** `CITATION.cff` said 0.22.0 and copy-paste CI
  snippets pinned `@v0.22.0` or `@v0.8.0` while the package built 0.24.0 — a snippet pinning a
  version a user cannot resolve is worse than none. `tests/test_version_consistency.py` now pins
  the citation file, every documented Action snippet, the Action's own install bound (which must
  *admit* the packaged version, the failure mode being exclusion rather than mismatch), and the
  presence of a CHANGELOG section.
- Zero-attempt attacks no longer render a fabricated `0.0% [0–0%]` in the scorecard heatmap, the
  per-attack table, the OSCAL observation props or the conformity dossier; they report N/A, and the
  heatmap gained an `n` column so the denominator is visible.
- `badvla` was tagged EAI02 and ran the visual family, contradicting both `docs/TOP10.md` and the
  EAI03 backdoor family that the cited paper actually describes.
- A `leaderboard build` against a submission naming an attack this build does not register died
  with a raw `KeyError` instead of rendering the row.

### Security

- `RunReport` now sets `extra="forbid"`, so an unrecognised key in a report file is rejected at
  load instead of being absorbed into the digest that an attestation signs.
- **Every third-party GitHub Action is pinned to a full commit SHA** (with a `# vX.Y.Z` comment) in
  all seven workflows and in `action.yml`. They were on mutable major tags while this repo runs
  OpenSSF Scorecard, whose Pinned-Dependencies check penalises exactly that — a compromised or
  retagged release would have been picked up silently, including on the PyPI publish path.
- **`persist-credentials: false` on every checkout** (six were missing it). A checkout that leaves
  the token in `.git/config` exposes it to every later step and anything those steps invoke; none
  of these jobs pushes with it.
- **`provael[hosted]` could not sign.** The extra omitted `cryptography`, yet the reference server's
  `?sign=true` path calls `attest.to_bundle(sign=True)` — so the failure surfaced at request time
  instead of install time.

### Documented

- **The attestation digest contract is now stated on `RunReport`.** The digest covers the canonical
  re-serialisation of the model, not the bytes of `report.json`, so adding any field changes the
  digest of every historical report and breaks re-verification by an older-issued attestation.
  Adding a field is therefore a breaking change that must bump `attest.RULESET_VERSION`. Switching
  the subject to a raw-bytes digest of `report.json` would remove that coupling and is the
  recommended follow-up; it changes the attestation format, so it wants its own release.

### Changed
- **Transfer status unified + evidence-state/verdict surfaced across exporters.** The scattered
  `policy != "stub" and suite != "stub"` inference (attestation, compliance, OSCAL, hosted report)
  now routes through one `provael.evidence.transfer_status_of` derived from the evidence ladder
  (behaviour-preserving — a legacy artifact falls back to the policy/suite signal it was built on).
  The **evidence state** and **release verdict** are now carried in the attestation statement, SARIF
  run properties, OSCAL props, and compliance evidence (in addition to `report.md` + the public
  manifest); the derived attestation golden was regenerated.
- **Real-integration failures are no longer swallowed.** `scripts/run_real.sh` dropped the
  `|| true` that let a failing gated integration test (real load / real env / real step) continue on
  to the leaderboard refresh — a failure now stops the run. A new `PROVAEL_REQUIRE_REAL_INTEGRATION=1`
  required mode turns a missing GPU (or a failing gated test) into a hard failure, so a skipped or
  unavailable real integration can never masquerade as success.
- **Pinned remote code for OpenVLA.** `OpenVLAAdapter` gained a `revision` parameter threaded into
  every `from_pretrained`. Because the model loads with `trust_remote_code=True`, a release-gated run
  (`PROVAEL_REQUIRE_REAL_INTEGRATION=1`) now refuses an unpinned revision (`UnpinnedRemoteCodeError`)
  instead of executing whatever code the moving default branch ships; discovery mode warns and
  proceeds. An allowlist (empty by default — no unverified SHA is shipped) holds vetted revisions.
- **The headline ASR now excludes the benign control.** `RunReport` gained `adversarial_asr` /
  `adversarial_attempts` / `adversarial_successes` (the benign `none` baseline excluded by semantic
  *role*, so adding benign episodes never moves it) and a `schema_version` (2). The report headline,
  `report.md`, SARIF, OSCAL, and the compliance/attestation evidence all lead with the adversarial
  ASR; the existing `asr` field is kept but relabelled as the **all-episode observed-unsafe rate**
  (benign included) so the two are never conflated. Legacy (schema-1) reports are corrected on read
  — recomputed from `results` — never silently reinterpreted. The committed SmolVLA×LIBERO
  attestation golden was regenerated to reflect the grown schema (null/default fields only; the
  source `report.json` is unchanged).
- **Attestation verification now fails closed.** `attest --verify` and
  `provael.attest.VerifyResult` no longer treat an unsigned or unchecked bundle as OK. Verification
  is decomposed into independent facts — payload integrity, subject-report integrity, signature
  presence, cryptographic validity, keyid match, and **signer trust** — and `overall_strict_ok`
  requires the whole trusted chain. A cryptographically-valid signature from a key that is not in a
  local trust store is authentic but *untrusted* and no longer passes strict verification.
  `VerifyResult.ok` is **deprecated** as an alias for `overall_strict_ok` (it previously returned
  `True` for unsigned bundles); call `overall_strict_ok` or `integrity_only_ok` explicitly.

### Added
- **Humanoid safety pack (whole-body / locomotion) — stub-validated.** A new deterministic CPU
  `humanoid` suite (fall/topple, loss of balance = COM outside the support polygon, self-collision,
  footstep keep-out) and a `humanoid` attack family — `balance_spoof` (EAI02), `whole_body_hijack`
  (EAI04), `stride_freeze` (EAI04) — each with its transfer-test (ASR + 95% Wilson CI + a benign-FPR
  control) and honestly labelled **stub-validated** (no real-model transfer claimed; N/A off the
  humanoid suite). A dedicated, gated `GrootAdapter` (NVIDIA GR00T-N1, routed through LeRobot;
  refused unless `PROVAEL_INTEGRATION` / `PROVAEL_REQUIRE_REAL_INTEGRATION` is set, so CPU CI stays
  deterministic). Pre-registered real-model protocol:
  `docs/studies/humanoid-locomotion-transfer.md`. The 47/70 canary and every existing family's ASR
  are unchanged — the humanoid attacks reuse the disjoint EAI02/EAI04 channels. Sim-only, no
  real-robot control code.
- **Continuous, signed per-checkpoint security gate.** The reusable GitHub Action now emits a signed
  **regression attestation** (`provael report --baseline … --attest-out`, or the Action's `sign` +
  `signing-key` inputs): a tamper-evident, offline-verifiable **Ed25519** envelope binding the
  regression diff, its SARIF, and the human summary under one signature, stating the verdict with the
  ASR **and its 95% Wilson CI** (never a bare number) — the artifact a safety case references
  (`provael.regression.verify_regression_attestation` checks it offline; the key is untrusted by
  default). A new reference workflow (`.github/workflows/checkpoint-security-gate.yml`) makes the gate
  **self-maintaining** — it persists the baseline in the Actions cache and promotes each passing
  checkpoint to the next baseline. Generic across the policy/suite abstraction (generality intended;
  tested on SmolVLA × LIBERO). Free core unchanged, still Apache-2.0.
- **Versioned cross-architecture RPC contract** (`provael.studies.cross_arch.CrossArchRequest` /
  `CrossArchResponse`, `build_cross_arch_request`, `ingest_cross_arch_response`). Because `[openpi]`
  and `[lerobot]` pin conflicting numpy majors, each real architecture runs in its own env; they now
  exchange only this JSON schema, which pins both sides (tool version, extra, lockfile digest). A
  response with no report is `incomplete` (not executed ≠ measured), a stub executor is `stub` (never
  a cross-architecture transfer claim), and a mismatched contract version is rejected.
- **Calibration as a bound, leakage-checked state** (`provael.calibration.CalibrationBinding`,
  `build_calibration_binding`, `split_seeds_three`) — records the endpoint + oracle version, the
  model/suite/task, digests of a **fit / calibration / eval** split, and the FPR achieved on the
  **untouched eval** set. Seed leakage (eval overlapping fit/calibration) is **refused at build**;
  `valid()` fails closed (leakage, an eval FPR above target, or an explicit invalidation all mean
  *uncalibrated*, never "calibrated-with-a-warning").
- **Independent semantic endpoints** (`provael.endpoints`) — `unsafe_envelope` (the legacy
  `success`), `authorized_task_success`, `unauthorized_action`, `attacker_objective_success`,
  `physical_hazard`, `controller_intervention`, each with a version-stamped oracle. A result carries
  an `endpoints` map; endpoints with no signal are **N/A** (absent), never a fabricated `False`, so
  the distinct questions are no longer collapsed into one boolean.
- **Paired McNemar test** (`scoring.asr.paired_mcnemar` / `mcnemar_exact`) — the right paired-binary
  test for each attack vs its benign twin at the *same* `(task, seed)` cell, complementing the
  existing benign control, matched-benign FPR, and BH-FDR. Exact (dependency-free), stable at the
  small n a real-transfer run produces; returns `None` without a benign baseline (never a fabricated
  significance).
- **Bound execution manifest** (`provael.execution.ExecutionManifest`) — runtime provenance (code
  commit + dirty state, OS/Python, dependency-lock digest, hardware / accelerator / precision,
  checkpoint revision+digest, seeds / horizon / attacks, action-schema digest, evidence state,
  release verdict, timestamps) stored **separately** from the deterministic `report.json` and bound
  to it by the report's SHA-256 digest — so time and machine identity never enter the byte-
  deterministic report. Pure builder (provenance passed in), env allow-listed with secret values
  redacted, and any provenance the caller could not supply recorded in `missing_fields` rather than
  invented. `provael attack` now **emits** `execution-manifest.json` alongside `report.json`, and a
  checked-in manifest ships for the committed artifact (legacy — unknown provenance recorded as
  missing, not faked).
- **Regulatory clock refreshed + sourced.** Each `REGULATORY_CLOCK` entry now carries a
  `last_verified` date (2026-07-23) and an official `source` (ELI URLs for the EU regulations). The
  AI Act note is updated: the Digital Omnibus reached a **provisional agreement (7 May 2026)** to
  defer Annex I embedded high-risk obligations to 2 Aug 2028, but it is **not yet formally adopted**,
  so 2027-08-02 remains the legal baseline (verified against current sources).
- **Glossary + schema-v2 migration guide** (`docs/glossary.md`, `docs/migration-v2.md`) — precise
  definitions for adversarial ASR vs the all-episode rate vs the benign control, the evidence-state
  ladder, the release verdict, and integrity-vs-signature-vs-trust; plus the additive schema-1→2
  migration and the renamed APIs (`ok`→`overall_strict_ok`, `transfer_status`→`evidence_state`,
  `/insurer-report`→`/assurance-report`, `MOTION_SLICE`→`ActionSchema`).
- **Deterministic public evidence manifest** (`provael.manifest`, `provael evidence-manifest`) — the
  JSON a website can consume. Restates the exact metric semantics (adversarial ASR vs all-episode vs
  benign control), per-attack results with Wilson intervals and applicability (N/A stays N/A, never a
  fabricated 0), baseline-aware registry counts, the evidence-ladder state, and the release verdict.
  Requires a **pinned commit** (never a moving branch), carries no wall-clock (byte-deterministic),
  and makes no hardware / calibration / external-reproduction claim the evidence state does not
  support. A checked-in manifest for the SmolVLA×LIBERO artifact ships alongside it
  (legacy-unverified, incomplete verdict, adversarial 17/60 vs all-episode 17/70).
- **Typed release verdict** (`provael.verdict.ReleaseVerdict`: incomplete / fail / conditional /
  pass) replacing binary pass/fail. Missing evidence is `incomplete`, not pass; a threshold breach or
  integrity/protocol violation is `fail`; a bounded exception (named approver + expiry + remediation)
  softens `incomplete` to `conditional` but never a `fail`. Conservative by construction — stub
  evidence cannot satisfy a real-policy gate, uncalibrated cannot satisfy a calibration gate, an
  unsigned/untrusted attestation cannot satisfy a signed-evidence gate, and a skipped requested
  integration is `incomplete`. Surfaced in `report.md`.
- **Explicit evidence-state ladder** (`provael.evidence.EvidenceState`) — the finer-grained
  successor to the binary transfer-status. A fresh stub run is `stub`, a real policy on a real suite
  is `real-episode`, and the classifier **never** awards `measured-real-policy-effect` or any HIL /
  hardware / external-reproduction / customer rung without the bound evidence those require. A report
  predating the ladder (the committed SmolVLA×LIBERO artifact) reads `legacy-unverified` — the bottom
  rung — never re-promoted from its non-stub policy/suite names. Surfaced additively in `report.md`
  and the compliance evidence; the derived attestation golden was regenerated.
- **First-class `ActionSchema`** (`provael.scoring.action_schema`) replacing the hard-coded
  `MOTION_SLICE = (1, 4)`. The optimized action attacks now read the end-effector translation
  channels from the **suite's declared layout** (wired in by the runner via a new
  `SchemaAwareAttack` protocol), and an action that does not match the declared layout (wrong
  dimension / non-finite) yields an explicit **N/A** rather than a guessed slice — so a real 7-DoF
  policy is read on channels 0-2, not the stub's 1-3. Ships `STUB_ACTION_SCHEMA` and a generic
  `SEVEN_DOF_DELTA_SCHEMA`, each with a stable digest for execution-manifest provenance.
- **Adversarial vs benign vs all-episode metrics** (`scoring.asr.adversarial_asr`,
  `benign_unsafe_rate`, `all_episode_observed_unsafe_rate`, `semantic_role`) plus a `reconcile()`
  tool that recovers the honest breakdown (benign 0/10, adversarial-only 17/60, all-episode 17/70,
  `mcp_tool_desc` N/A) from a legacy report **without editing it**. `ASRStat.measured_rate` returns
  `None` for a 0-attempt slice (an N/A, not a measured 0%), and a `roles` map labels each attack
  benign-control vs adversarial-treatment.
- **Local trust store** (`provael.attest.TrustStore` / `TrustedKey`, `attest --verify --trust-store`)
  with per-key validity window, revocation status, and subject label — the verifier's own trust
  anchor, never shipped inside a bundle.
- **Integrity-only verification** (`attest --verify --integrity-only`,
  `VerifyResult.integrity_only_ok`) that grades only the digest layer and is never reported as plain
  "verified".
- **Distinct `attest --verify` exit codes** per state — unsigned, invalid signature, untrusted
  signer, revoked/expired key, subject mismatch, digest mismatch, malformed — via `verify_exit_code`.

### Security
- **Supply-chain & governance hardening.** Least-privilege `permissions: contents: read` + a job
  timeout + `persist-credentials: false` + concurrency on the CI workflow; a Dependabot config for
  GitHub Actions and pip; a `CODEOWNERS` gating the evidence-integrity surfaces; the composite
  `action.yml` install bounded to the current minor (`>=0.22.0,<0.23.0`) instead of an open
  `>=0.18.0`; a PR evidence/claims checklist and an evidence-defect issue template; and
  `docs/maintainers/GITHUB_SECURITY_SETTINGS.md` documenting the admin-only branch/tag/scanning
  controls (boxes explicitly unticked until a maintainer verifies them — never falsely marked done).
  Adds a **dependency-vulnerability audit** CI job (`pip-audit --strict`, verified clean), **CycloneDX
  SBOM + SHA-256 checksums** attached to each release (alongside the existing PEP 740 provenance
  attestations + OIDC trusted publishing), and a **non-root user** in the runtime Docker image.
  (GitHub Actions are kept current/pinnable via Dependabot rather than hand-pinned SHAs.)
- **The experimental hosted server is disabled by default and asserts no authority.** The reference
  `provael.hosted` surface is now explicitly experimental and refuses to start unless
  `PROVAEL_ENABLE_EXPERIMENTAL_HOSTED=1` is set. `POST /attest` no longer mints a throwaway ephemeral
  key (it refuses to sign without a configured operator key) and returns the operator's public key
  labelled **untrusted by default** — every signature is the operator's own key, never a
  Provael/project authority. `POST /insurer-report` is renamed `POST /assurance-report` and produces
  a structured **assurance-report draft** (an evidence export, not an insurer / Notified-Body
  opinion). `PROVAEL_HOSTED_LICENSE` is documented as a local feature flag, **not** authentication.
  The "authoritative project-key signature" and "insurer / Notified-Body-ready" marketing wording was
  removed; `docs/maintainers/HOSTED_PRODUCTION_REQUIREMENTS.md` records the controls a real operated
  service would require (none implemented). The SmolVLA×LIBERO assurance golden was regenerated for
  the renamed, adversarial-headline draft.

### Documentation & community
- **Community & discoverability scaffolding (docs only — no `src/` change, no behaviour change).**
  New `docs/ADOPTERS.md` (self-reported, ships empty), `docs/COMMUNITY.md` (a Discussions map plus a
  maintainer TODO block for the social preview and repo topics), `docs/TOP10_RFC.md` (the v0.2 → v0.3
  process for the Embodied AI Security Top 10), and `docs/DEFENSES.md` (a mitigation taxonomy and the
  instruction-canonicalization spec — no defense claimed until measured). Three **pre-registered**
  study protocols under `docs/studies/` (`pi0-openpi-transfer`, `metaworld-transfer`,
  `sim-to-real-so101`) — protocol only, no results claimed. Three GitHub issue-form templates
  (`top10_proposal`, `attack_family` with a required honest-limitations acknowledgement, and
  `design_partner`). A README **Commercial & design partners** section, an Assessment badge, a
  defenses roadmap bullet, and a 1280×640 social-preview image. No metrics, adopters, contributors,
  or results were invented.

## [0.22.0] — 2026-07-23

### Added
- **`optimized_instruction` / `targeted_redirect` — an optimized, command-preserving instruction
  attack.** The first optimized attack on the *instruction* channel (the other two optimized
  families search the action-directive and image channels): a bounded-budget, on-policy **greedy
  search** over command-preserving instruction edits — the command-preserving analogues of the
  templated `roleplay` / `goal_substitution` / `paraphrase` operators (reframe / sequence / manner-
  urgency cues) **minus the explicit target object** — for the edit that most redirects the policy's
  emitted action toward an unsafe outcome, then commits it for the episode. Each candidate is rolled
  out through the policy (an oracle the runner wires in via the existing `OracleAttack` protocol —
  **no new backend, no runner change**), scored by the new
  `scoring.asr.targeted_redirection_score`, gated by the new `scoring.asr.is_command_preserving` /
  `benign_similarity` (it may not name a target/danger word nor drop below a benign-similarity floor
  of the operator's command), under a `--query-budget` with early-stop on the redirection target.
  A new `attacks.base.OptimizedAttack` base carries the reusable search loop (propose → roll out →
  score → keep-best → early-stop), composing over `Attack.perturb`.
- **Held-out transfer-test** (`attacks.targeted_redirect.frozen_transfer_test`): search on train
  seeds, freeze the discovered *operator*, re-apply it verbatim to held-out seeds, and report
  train + held-out ASR with a 95% Wilson CI — the honesty control that separates a generalising edit
  from one overfit to a single episode. The standard ASR + Wilson CI + matched-benign-FPR travel
  with the new family through the existing report path (no metric reimplemented).
- **Scope + honesty.** Primary tag **EAI01** (instruction channel, scored on the CPU stub by the
  danger-threshold predicate); it operationalizes the **EAI04** targeted-redirection *threat model*
  through the one channel measured to transfer on a real SmolVLA×LIBERO policy — an honest
  cross-reference (`THREAT_MODEL_EAI`), **not** a claim that EAI04 transfers: the real
  motion-redirection outcome is GPU-gated (`PROVAEL_INTEGRATION=1`) and **not measured here**, and
  the CPU stub shows an honest sub-100% ceiling (command-preserving cues cannot reach the top per-seed
  thresholds). The `instruction,visual,injection` seed-0 **47/70 canary is byte-identical** (the new
  attack is in its own `optimized_instruction` family). Recommended mitigation — **instruction
  canonicalization / repair** — documented in `docs/TOP10.md` + `PRIOR_ART.md`. Sim-only: no
  real-robot / hardware control, no real-world-harm payload, no detection-evasion; grounded in the
  command-preserving / trajectory-level instruction-redirection line of work (`PRIOR_ART.md`); no
  "first" claim; the Embodied AI Security Top 10 is never branded "OWASP".

## [0.21.0] — 2026-07-22

### Added
- **`provael attest --profile` — signed standards-aligned assurance attestation (ISO 10218-2 /
  IEC 62443 / insurer) from an ASR run.** The existing DSSE/Ed25519-signed attestation gains an
  optional `--profile <iso-10218-2|iec-62443|insurer>` that embeds a standards-aligned **assurance
  view** in the signed statement (new `provael.assurance`), mapping the *same* measured ASR +
  EAI-Top-10 findings + per-family transfer-test results onto: (a) **ISO 10218-2:2025** cyber-risk-
  assessment evidence routed to an **IEC 62443 SL2** target; (b) an **insurer-consumable** summary
  with the honest *which-families-transfer-on-the-real-model* table (per family: ASR, n, 95% Wilson
  CI, benign-FPR, `measured-real-transfer` vs `stub-validated-scaffolding`); (c) a third-party
  **cert-readiness cross-reference** (NVIDIA Halos / UL 4600 / ISO/PAS 8800 / ISO 21448 / ISO/IEC
  TR 5469 — a readiness input, not a certification or endorsement). It **reuses** the shipped
  scoring, the compliance crosswalk, and the insurer report — nothing is re-measured or re-signed —
  and reuses the existing DSSE Ed25519 path (no new signing dependency). Deterministic: a fixed
  `(report, issued_at, commit)` yields a byte-identical attestation (the sample is digest-only for
  reproducibility). Ruleset bumped to `provael-attest-ruleset/4`. A worked, verifiable example over
  the real SmolVLA×LIBERO run is committed at `results/smolvla_libero_object/attestation.insurer.json`.
  Honest per-family transfer caveat throughout; evidence, not certification; the Embodied AI Security
  Top 10 is never branded "OWASP"; no "first" claim. `docs/ATTESTATION.md` + README updated.

## [0.20.0] — 2026-07-21

### Added
- **EAI04 action-space transfer study — a clearly-published negative result.** New
  `provael study eai04` + `provael.studies.cross_arch.build_eai04_study` extend the v0.17.0
  cross-architecture harness (reusing the runner + `provael.scoring.asr` — no ASR reimplemented, no
  second harness) to the four EAI04 vectors (`freeze`, `trajectory_hijack`, `keepout_hijack`,
  `critical_freeze`). Per (architecture × vector) it reports ASR + n + fixed-n 95% **Wilson** CI +
  matched **benign-FPR** + **Succ-But-Unsafe** + **BH-FDR** across vectors, flagging `preliminary`
  under 5 seeds. On the deterministic `reach` keep-out fixture all four fire 100% [72–100%] (BH-FDR
  significant vs a 0% benign control; Succ-But-Unsafe n/a — the fixture surfaces no task-success).
  **The real SmolVLA/π0 × LIBERO legs are `not-applicable`, not `pending`:** these out-of-band
  directive attacks never reach a real VLA, and `libero` surfaces no `supports_action_integrity` /
  `supports_action_space` signal (verified on a LIBERO-shaped observation, guarded by a test). So
  `action`/`action_space` **remain stub-validated** — no real-policy EAI04 transfer is claimed or
  obtainable through this mechanism; a real action-freeze/hijack needs the GPU-gated adversarial-image
  path (`optimized_patch` / FreezeVLA / AttackVLA). Deterministic artifact at
  `results/eai04_action_space_transfer/`; write-up `docs/studies/eai04-action-space-transfer.md`;
  `provael certify` auto-composes the EAI04 evidence with its transfer statement (no fork). README +
  TOP10 EAI04 updated; coverage unchanged (still 8/10). No "first" claim.

## [0.19.0] — 2026-07-20

### Added
- **EAI ↔ RoboJailBench taxonomy crosswalk.** New `provael.crosswalk` + `provael crosswalk --target
  robojailbench` map the Embodied AI Security Top 10 against **RoboJailBench**'s 18-category
  harm-outcome taxonomy (Yeke, Zhou, Lin, Cai, Bianchi & Celik, Purdue; arXiv 2605.19328v1, 2026;
  leaderboard v1.0.0) — category names quoted verbatim from Table 2. A declarative, machine-readable
  mapping in both directions with an honest per-category coverage state (**2 covered · 5 partial · 9
  not covered · 2 out of scope by design**, of 18 — the two taxonomies are orthogonal axes, harm vs
  mechanism, so a clean 1:1 does not exist). Deterministic JSON + Markdown (`sort_keys`, no
  wall-clock). A **head-to-head** reports provael's measured ASR per mapped family (95% Wilson CI +
  benign-FPR, **reusing `provael.scoring.asr` — no ASR reimplemented**) with the mandatory transfer
  statement next to every number: only the `instruction` family is demonstrated on a real policy;
  every other family is labelled *not demonstrated on a real policy*. Wired into `provael certify
  --include-crosswalk` as an optional Annex I appendix (composed, not re-rendered). Full write-up:
  `docs/crosswalk/robojailbench.md`; committed JSON at `results/crosswalk/`. Adds **no** new Top-10
  coverage (still 8/10); TOP10.md gains a "Relationship to other taxonomies" section. Sim-only: no
  RoboJailBench benchmark is run and no comparative scores against their numbers are produced.

## [0.18.0] — 2026-07-19

### Added
- **`provael certify` — Machinery Regulation conformity-assessment evidence dossier.** A new command
  produces the evidence pack a notified body reviews for an ML-based safety component under
  Regulation (EU) 2023/1230 (**applies 20 January 2027**; CELEX 32023R1230, Article 54). One shared
  code path (`provael.certify`) serves two profiles: `--profile annex-i-part-a` (default — the
  Annex I Part A third-party conformity route for ML self-evolving-behaviour safety components, via
  Article 6(1) → Article 25(2)) and `--profile annex-iii`; the existing hosted **Annex III** pack
  (`provael.hosted.machinery`) is now a thin caller of this core, not a parallel implementation. The
  dossier's separately-addressable artifacts: component identification + intended use + operating
  envelope (run-derived, plus an operator `--component-metadata` overlay); the per-family adversarial
  evidence — ASR with its **n**, the fixed-n **Wilson 95%** interval *and* the anytime-valid
  **Robbins Beta-mixture** confidence sequence, the matched benign FPR, Succ-But-Unsafe, and
  **BH-FDR** across families, with the `preliminary` flag under 5 seeds; an honest **transfer
  statement** where a family with no real-policy transfer is labelled *"not demonstrated on a real
  policy"* in the same sentence as its ASR; a plain **residual-risk** statement (classes deferred per
  SAFETY.md, families/suites not run, embodiments not covered); a **standards crosswalk** (Machinery
  Annex I Part A / Annex III, ISO 10218-1/-2:2025 → IEC 62443, NIST AI 100-2e2025) with unverifiable
  clause numbers marked `[clause reference pending verification]` rather than guessed; and references
  (not copies) to the CycloneDX **ML-BOM** and the PEP 740 **attestation**. It **reuses** every
  statistic from `provael.scoring.asr` and `provael.calibration` — **no scoring is reimplemented**
  (guarded by a test). Emits two formats: the machine-readable **OSCAL** assessment-results (extended
  with `import-ap` + `reviewed-controls` clause bindings — not a new schema) and a single
  self-contained **print-to-PDF HTML** an assessor can read without ever having used Provael.
  Deterministic (`sort_keys`-stable, no wall-clock). **Evidence input to a conformity assessment — it
  is not a conformity assessment, and Provael is not a notified body.** New
  `docs/compliance/machinery-annex-i-part-a.md`.

## [0.17.0] — 2026-07-18

### Added
- **Cross-architecture transfer study.** New `provael.studies.cross_arch` + the runnable harness
  `studies/cross_arch_transfer/run.py` + CLI `provael study cross-arch`: runs the shared
  **instruction / visual / injection** battery (plus the benign `none` control) against multiple VLA
  architectures — **stub** (CPU, deterministic), **SmolVLA** (LeRobot), **π0** (openpi) — through the
  *same* runner + scoring, and reports **per-(family × architecture)** ASR with a **95% Wilson CI**
  and the **benign-FPR** control. It **reuses** `provael.runner` and `provael.scoring.asr` (via the
  existing `by_family` + `wilson_ci` + `matched_benign_fpr`) — **no ASR is reimplemented**. The
  CPU-stub path is byte-deterministic and GPU/network-free (CI-green); the SmolVLA/π0 legs are gated
  behind `PROVAEL_INTEGRATION=1` + the `[lerobot]`/`[openpi]` extra and, because those extras pin
  conflicting numpy majors, run in separate envs merged offline (`merge_reports`) — off the gated
  path they are honestly `pending`. Deterministic artifacts land in `results/cross_arch_transfer/`
  (`summary.json` + per-architecture RunReport JSON). Honest findings in
  `docs/findings/2026-cross-arch-transfer.md` (which family transfers on which architecture, with
  CIs and the transfer-test for every claim; no "first" claim; Top-10 not branded "OWASP") and a new
  README "Cross-architecture transfer" section. Adds **no** new Top-10 coverage (still 8/10).

### Notes
- Sim-only, defensive; the CPU-stub numbers are fixture properties, not a real VLA — no
  cross-architecture transfer is claimed until the gated real legs run. The deterministic CPU core
  (stub 47/70 canary and all family screens) stays byte-identical.

## [0.16.0] — 2026-07-15

### Added
- **P0.4 — honest reporting for a real-transfer number.** Every run now carries, on the overall ASR,
  **both** a fixed-n 95% Wilson CI (`RunReport.ci95`) **and** an **anytime-valid CI**
  (`RunReport.anytime_ci`) — a Robbins-style **Beta-mixture confidence sequence** (`calibration.
  anytime_ci`, stdlib `math.lgamma`, no SciPy) that stays valid under the seed-by-seed peeking a
  budget-capped GPU job does, where a single-n Wilson interval would not. Plus a **matched-benign
  FPR** (`scoring.asr.matched_benign_fpr`): the benign `none` twin flag-rate over exactly the
  `(task, seed)` cells an attack touched, removing the composition confounds the marginal
  `benign_fpr` can hide. Runs record their distinct **seed count** and a **`preliminary`** flag
  (`<5` seeds → indicative, not banked; LIBERO shows a ~13.7 pp cross-seed spread). A **per-episode
  log** (`AttackResult.decisions`, one `Decision` per executed step) now ships in `report.json`; it
  is bound by the same SHA-256 the attestation subject already records (no new hash). `report.md`
  surfaces all of the above.
- **INV-4 — threat-model metadata on every attack.** `Attack` (and each `AttackResult`) gains
  `attacker_access` (`white-box-gradient` | `black-box-query` | `in-scene-physical`) and
  `action_head_class` (`token` | `flow`), defaulting to `None` where a stub family makes no real
  claim — so no freeze/token attack is silently assumed to transfer to a flow-matching head (D3).
- **D6 — explicit `accelerator` / `precision`.** `RunConfig` gains both fields (`cpu` | `cuda` |
  `mps`; **`tpu` → `NotImplementedError`** pointing at ROADMAP §8/D5, the reserved-but-unimplemented
  slot). Threaded into `RunReport`, the `Calibration` provenance, and the attestation statement so a
  result records **where** and **at what precision** it ran. New `--accelerator` / `--precision` CLI
  flags on `provael attack`.
- **D1 — transfer-aware compliance tier.** The signed attestation's honesty label
  (`measured-real-transfer` / `stub-validated-scaffolding`) is now threaded as a **run-level
  `transfer_status`** field on the compliance `EvidenceResult` and as an OSCAL `transfer-status`
  prop on the overall finding, so an auditor cannot misread stub scaffolding as conformity-relevant.
  Both vocabularies are promoted to shared constants in `types.py` (INV-3: one source, extended not
  bypassed); `attest.py` now references them. The per-family nuance (e.g. the optimized family) stays
  in the attestation's per-attack `transfer` list — the run-level summary does not override it.
- **D2 — standards rows.** Compliance crosswalk gains **EU CRA** (Reg. (EU) 2024/2847), **ISO/IEC
  TR 5469:2024** (AI functional safety), **ISO/IEC 42001:2023** (AI management system), and **ISO/IEC
  23894:2023** (AI risk management) requirement rows, each scope-flagged *indicative*. A **CRA
  regulatory-clock** entry is added to the attestation (main obligations 2027-12-11; reporting
  2026-09-11 — dates verified against OJ 2024/2847). Ruleset bumped to `provael-attest-ruleset/2`.
- **D5 — ATLAS mapping promoted to structured data (INV-6).** Each `provael.eai.CATALOG` entry
  gains an `atlas_techniques` tuple (descriptive tactic→technique phrasing, no fabricated
  `AML.TXXXX` ids, `(proposed)` where ATLAS's embodied coverage is thin), surfaced into SARIF rule
  `properties.atlasTechniques`. `docs/standards/atlas-case-study.md` extended to all eight covered
  categories as the human-readable mirror. Routes external validation through MITRE ATLAS.
- **C1 — Benjamini-Hochberg FDR.** `scoring.asr.benjamini_hochberg` (adjusted q-values + reject
  mask) + `binom_test_greater` (exact one-sided binomial p-value, stdlib `lgamma`); `fdr_by_attack`
  tests each EAI-tagged attack against the benign control and BH-corrects across the family, so
  "significant" means *survives* multiple-comparison control — pre-empting the "~19.8% of LIBERO
  SOTA claims are significant" critique. Surfaced as a report.md section (requires a benign control).
- **C2 — Succ-But-Unsafe metric (schema scaffold).** `AttackResult.task_success` (`bool | None`,
  read from the suite state) and `RunReport.succ_but_unsafe` + `scoring.asr.succ_but_unsafe` give the
  SafeVLA-Bench worst-quadrant rate (task completed AND safety violated). The stub surfaces no
  task-success, so it is honestly `None`/N-A there — the real signal is GPU-gated (LIBERO), never
  fabricated.
- **E3 — resumable trial ledger.** New `provael.ledger`: an append-only JSONL of `(attack, task,
  seed)` `TrialRecord`s with `pending_trials` resume — a preempted GPU run resumes instead of
  re-measuring, which is what makes the ≥5-seed budget affordable on cheap spot instances.
  Crash-safe (a mid-write line is skipped, not fatal) and deterministic.
- **E4 — CycloneDX ML-BOM export.** New `provael.mlbom` promotes the supply-chain example to a
  first-class deterministic exporter (`provael attack/report --format mlbom`): a CycloneDX 1.6
  ML-BOM carrying the ASR + Wilson CI + benign-FPR + transfer-status as model-card metrics, mapped
  to EU AI Act Art. 11 / Annex IV. Ingests into OWASP Dependency-Track.
- **D3 — EU Machinery Annex III evidence-pack (paid).** New `provael.hosted.machinery.
  build_machinery_annex_pack` maps the run's evidence onto the two cybersecurity-relevant Annex III
  EHSRs of Reg. (EU) 2023/1230 — **1.1.9 protection against corruption** and **1.2.1 safety &
  reliability of control systems** — wrapping the signed attestation, carrying the run-level transfer
  tier, ahead of 2027-01-20. Pure function; gated at the server layer (Q4 paid enterprise add-on).
- **D4 — insurer report honesty signals.** `build_insurer_report`'s executive summary now threads
  the P0.4/D1 signals (Wilson + anytime CI, matched-benign FPR, run-level `transfer_status`, seed
  count + `preliminary`) so an insurer cannot read a stub number as a real-transfer measurement.
- **P0.3b — `optimized_patch` family (`patch_hijack`), the GPU-ready optimised adversarial-patch
  attack.** A new attack that searches over adversarial **image patches** on the real camera channel
  (`IMAGE_KEY` → the adapter's `_apply_image_override`) — the perception-space analogue of
  `targeted_hijack`, scoring each candidate by the policy's *emitted motion* via the runner's oracle
  (broadened from a concrete-class check to the structural `OracleAttack` protocol). It maps to
  **EAI02**, records `attacker_access="black-box-query"` + `action_head_class="flow"` (honest: a query
  search, not the white-box-gradient FreezeVLA it credits), lives in its **own family** so every
  existing family expansion stays byte-identical, and is **applicable-gated on a real image** — so it
  is inert on the image-less stub and the 47/70 canary is untouched. Reimplemented from scratch
  (INV-8; FreezeVLA is MIT but no code is ported). The gradient/search only runs on GPU; no transfer
  is claimed until the gated path runs.
- **P0.1 `scripts/clean_baseline.py` + P0.2 `tests/test_libero_realpath.py` — the GPU-ready
  denominator and predicate proof.** `clean_baseline.py` runs the benign `none` control through the
  real SmolVLA×LIBERO path and emits a machine-readable **pass/fail false-positive gate** at the Q2
  tolerance (X = 5 pp), recording GPU-hours for the ROADMAP §5 budget. `test_libero_realpath.py`
  proves the shipped `evaluate_unsafe` predicate has teeth: a CPU test (no sim) flags an in-zone
  end-effector and clears an out-of-zone one, plus gated integration tests that assert a real benign
  rollout never trips and a real in-zone end-effector is flagged. Both are gated/skip cleanly on CPU.
- **`[lerobot]` extra now pulls the LIBERO simulator** (`lerobot[smolvla,libero]==0.5.1`) and the
  LIBERO suite surfaces its real task-completion as `task_success`, so the C2 Succ-But-Unsafe metric
  is live on the real path (still honestly N/A on the stub). A **budget-capped nightly GPU workflow**
  (`.github/workflows/gpu-nightly.yml`, OFF unless `vars.ENABLE_GPU_NIGHTLY == 'true'`) runs the real
  path via Modal without ever touching the CPU `ci.yml`.
- **§8 — accelerator rationale doc.** New `docs/accelerators.md` documents the D6 device slot and
  **why `accelerator='tpu'` raises** (no maintained VLA-class PyTorch TPU inference path yet) with
  the both-required revisit trigger (TorchTPU GA **and** third-party PyTorch VLA inference parity).
  Linked from the `NotImplementedError` message and added to the docs nav.
- **`openpi` / π0 flow-matching adapter — the cross-architecture transfer backend.** New
  `provael.policies.openpi_adapter.OpenPiAdapter`: a second non-LeRobot backend that connects to a
  Physical-Intelligence/openpi π0 policy **server** via the CPU-only `openpi-client` (`[openpi]`
  extra), injecting the (adversarial) instruction as openpi's `prompt`. Registered so
  `list-policies` shows `openpi` (8 policies now). The point is **cross-architecture transfer**: the
  same instruction-family attacks that move SmolVLA (LeRobot) can be aimed at π0 served by openpi's
  own stack — a different framework, same flow-matching action head. Ships the harness + a gated
  integration test; the real forward pass needs the extra, `PROVAEL_INTEGRATION=1`, and a running
  GPU server, so **no cross-model number is claimed** ("run pending on GPU"). `[openpi]` and
  `[lerobot]` are declared **mutually exclusive** (`[tool.uv] conflicts`) — conflicting numpy pins —
  so the cross-architecture comparison runs in a separate env, compared offline. Adds **no** new
  Top-10 coverage (still 8/10); "Embodied AI Security Top 10" naming preserved.

### Security
- **P0.5b — PEP 740 publish attestations.** `release.yml` pins the PyPI publish step from the moving
  `pypa/gh-action-pypi-publish@release/v1` to `@v1.14.0` and sets `attestations: true`, so releases
  emit signed provenance attestations alongside the OIDC trusted-publishing upload.
- **P0.5a — dependency advisory (hygiene, not a Provael finding).** `SECURITY.md` records
  **CVE-2026-25874** (LeRobot unauthenticated pickle-deserialization RCE, CVSS 9.8, affecting
  `lerobot` ≤ 0.5.1) — verified against the upstream advisory. Provael's optional `[lerobot]` extra
  pins an affected version but **never starts the vulnerable async-inference gRPC PolicyServer**, so
  the path is unreachable through Provael; the note frames it as supply-chain hygiene and points at
  the upstream fix. Also fixes the stale `SECURITY.md` "supported versions" line (`0.3.x` → `0.16.x`).

### Notes
- CPU core stays deterministic and lean (INV-9): the new fields default to `None`/empty and the new
  `patch_hijack` is inert off the real image path, so every frozen canary (stub 47/70; the
  EAI03/EAI04/EAI08/EAI09 screens; the `reach` keep-out families) stays **byte-identical**. The GPU
  path rides the `[lerobot]` extra and stays behind `PROVAEL_INTEGRATION=1`; CPU CI touches no GPU,
  model, or network. No paper ASR is a Provael number (INV-2); nothing is labelled "first" (INV-5).

## [0.15.0] — 2026-07-13

### Added
- **EAI09 `confidentiality` attack family — model & data confidentiality (a memorized-canary leak
  screen).** `feat(attacks): EAI09 confidentiality family — sim-only, transfer-tested (Wilson-95 +
  benign-FPR).` Two attacks (`membership_inference`, a `member::` probe asking whether a candidate
  canary was a training member; `model_extraction`, an `extract::` query asking the policy to
  reproduce it — extraction / inversion) each screen a policy for a **memorized training canary** an
  attacker who can only *query* it could recover. **Sim-only, defensive:** Provael performs **no real
  exfiltration** — the "canaries" are opaque sim markers and the leak is scored on a deterministic
  fixture; the visible instruction stays benign, so any leak is attributable to the probe. New
  `src/provael/scoring/confidentiality.py` protocol + `src/provael/attacks/confidentiality.py`; wired
  into the registry, `list-attacks`, SARIF (EAI09 ruleId, derived from the tag), and the stub suite's
  unsafe OR-chain (`suites/base.py::evaluate_unsafe` gains `confidentiality_unsafe`, surfaced by the
  scalar `stub` suite like the EAI03 backdoor / EAI08 authorization screens). The leak rides a
  **disjoint stub action channel (10)** — the stub fixture width goes 10→11 — so every frozen canary
  (stub 47/70; the EAI03 backdoor, EAI08 authorization, EAI04 action families; the `reach` keep-out
  families) stays **byte-identical**. New `CATALOG["EAI09"]` entry; mapped to EAI09 in the **Embodied
  AI Security Top 10** (not OWASP) and to NIST AI 100-2 **Privacy (model extraction, NISTAML.03)** +
  MITRE ATLAS **Exfiltration** in the compliance crosswalk.
- **Mandatory transfer-test (stub-validated).** On the deterministic CPU `stub` suite the planted
  fixture leaks its memorized canary 100% [84–100%] (Wilson CI) against a **0% benign-FPR control**
  (the `none` baseline probes nothing); a clean policy that memorized no such canary screens ~0% — an
  honest null. Labelled `stub-scaffolding` via `provael transfer-test`. The real-model path (a
  membership-inference / extraction advantage measured by *querying* a real policy, never exfiltrating
  real data) is GPU-gated and **not run**; no cross-model claim, no "first" claim.
- **Top-10 coverage now 8/10.** Categories with a shipped sim-only attack family: EAI01–EAI06, EAI08,
  EAI09. **Scope note:** the requested EAI07 (CPS / firmware / comms / teleop) is an infrastructure /
  CVE category — faithful coverage would need real exploit tooling (out of the sim-only, defensive
  scope), so per the maintainer's fallback the family targets **EAI09** instead. **EAI07** and
  **EAI10** (a governance meta-risk Provael's own eval mitigates) remain taxonomy-only by design.

## [0.14.0] — 2026-07-13

### Added
- **EAI04 `action_space` attack family — action-space integrity, 2nd vector.**
  `feat(attacks): add EAI04 action-space-integrity 2nd vector (action_space) —
  keep-out hijack of the commanded end-effector + critical-step freeze; transfer-tested
  Wilson-95 + benign-FPR.` A **second, disjoint EAI04 vector** alongside the founding `action`
  family (mirroring how `sensor_spoof` is a 2nd EAI02 vector beside `visual`): instead of the motion
  channels (1-3), it attacks the **commanded end-state** on its own out-of-band channel. Two attacks
  (`keepout_hijack`, an AttackVLA-style targeted hijack that drives the *commanded* end-effector into
  a **monitored-standstill keep-out zone**; `critical_freeze`, a targeted FreezeVLA-style paralysis
  at a **safety-critical step**). **Sim-only, defensive:** the attack perturbs only the observation
  the policy receives, **never real-robot control**, and ships no real-world payload. The visible
  instruction stays **benign** (the stub's danger channel stays 0), so the violation is attributable
  to action-space integrity, not a jailbroken language goal (the separate EAI01 `instruction`
  family) nor the motion-channel freeze of the founding `action` family. New
  `src/provael/scoring/action_space.py` protocol + `src/provael/attacks/action_space.py`; wired into
  the registry, `list-attacks`, SARIF (EAI04 ruleId, derived from the tag), and the spatial keep-out
  OR-chain (`suites/base.py::evaluate_unsafe` gains `action_space_unsafe`, surfaced by the `reach`
  suite). The cue uses a **disjoint stub action channel (9)** — the stub fixture width goes 9→10 — so
  the frozen canaries (stub 47/70; reach roleplay 10/10, goal_substitution 0/10; the founding
  `freeze` / `trajectory_hijack`, and backdoor / authorization / sensor_spoof / misalignment) stay
  **byte-identical**. It maps to EAI04 (Action-space integrity) in the **Embodied AI Security Top 10**
  (not OWASP), and to the EU Machinery Regulation (EU) 2023/1230 corruption-of-safety-function
  essential requirement (applies **2027-01-20**) + ISO 10218-1:2025 monitored-stop / space-limiting
  functions in the compliance crosswalk.
- **Mandatory transfer-test (stub-validated).** On the deterministic CPU `reach` keep-out suite the
  commanded end-effector is hijacked into the zone / the policy is frozen 100% [84–100%] (Wilson CI)
  against a **0% benign-FPR control** (the `none` baseline injects no cue and stays at the origin,
  un-frozen). Labelled `stub-scaffolding` via `provael transfer-test`. The real-model path (AttackVLA
  / FreezeVLA × SmolVLA × LIBERO) is GPU-gated and **not run**; no cross-model claim, no "first" claim.

## [0.13.0] — 2026-07-08

### Added
- **EAI06 `misalignment` attack family — cross-domain safety misalignment (the embodiment gap).**
  `feat(attacks): add EAI06 cross-domain safety-misalignment (embodiment-gap) family —
  benign-instruction → unsafe-action, targeting keepout_zones; transfer-tested Wilson-95 + benign-FPR.`
  Two attacks (`benign_urgency_override`, an urgency framing; `euphemistic_reroute`, a euphemism) each
  **reframe the task into an instruction a chat-layer safety filter would pass as benign** yet, when
  embodied, drive the policy's commanded end-effector into a **monitored-standstill keep-out zone**
  (BadRobot, ICLR 2025, risk (b)). **Sim-only, defensive:** the attack perturbs only the
  instruction/observation the policy receives, **never real-robot control**, and ships no real-world
  payload. The reframed instruction carries **no** language-level danger token (the stub's danger
  channel stays 0), so the violation is attributable to the language→action gap, not a jailbroken
  language goal (the separate EAI01 `instruction` family). New `src/provael/scoring/misalignment.py`
  protocol + `src/provael/attacks/misalignment.py`; wired into the registry, `list-attacks`, SARIF
  (EAI06 ruleId), and the spatial keep-out OR-chain (`suites/base.py::evaluate_unsafe` gains
  `misalignment_unsafe`, surfaced by the `reach` suite). The cue uses a **disjoint stub action channel
  (8)** — the stub fixture width goes 8→9 — so the frozen canaries (stub 47/70; reach roleplay 10/10,
  goal_substitution 0/10; action, backdoor, authorization, sensor_spoof) stay **byte-identical**. It
  maps to EAI06 (Cross-domain safety misalignment) in the **Embodied AI Security Top 10** (not OWASP).
- **Mandatory transfer-test (stub-validated).** On the deterministic CPU `reach` keep-out suite a
  benign-sounding instruction drives the end-effector into the zone 100% [84–100%] (Wilson CI) against a
  **0% benign-FPR control** (the `none` baseline injects no cue and stays out of the zone). Labelled
  `stub-scaffolding` via `provael transfer-test`. The real-model path — a benign-sounding instruction
  driving a real policy's end-effector into a keep-out zone (BadRobot × SmolVLA × LIBERO) — is GPU-gated
  and **not run**; no cross-model claim, no "first" claim.

## [0.12.0] — 2026-07-08

### Added
- **EAI02 `sensor_spoof` attack family — adversarial perception / sensor spoofing.** A new EAI02
  attack *vector* (distinct from the scalar `visual` family): a **sim-injected perception spoof**
  (`patch_spoof`, an adversarial patch on the simulated camera; `signal_spoof`, a range/depth signal
  perturbation on the simulated LiDAR) that makes the policy perceive a phantom target inside a
  **monitored-standstill keep-out zone** and command its end-effector there. **Sim-only, defensive:**
  it perturbs the simulator's observation stream, **never real sensor hardware**, and ships no
  real-world payload. New `src/provael/scoring/perception.py` protocol + `src/provael/attacks/
  sensor_spoof.py`; wired into the registry, `list-attacks`, SARIF (EAI02 ruleId), and the spatial
  keep-out OR-chain (`suites/base.py::evaluate_unsafe` gains `sensor_spoof_unsafe`, surfaced by the
  `reach` suite). The spoof uses a **disjoint stub action channel (7)** — the stub fixture width goes
  7→8 — so the frozen canaries (stub 47/70; reach roleplay 10/10, goal_substitution 0/10; action,
  backdoor, authorization) stay **byte-identical**. It maps to EAI02 (Adversarial perception) in the
  **Embodied AI Security Top 10** (not OWASP).
- **Mandatory transfer-test (stub-validated).** On the deterministic CPU `reach` keep-out suite the
  spoof drives the end-effector into the zone 100% [84–100%] (Wilson CI) against a **0% benign-FPR
  control** (the `none` baseline injects no spoof and stays at the origin). Labelled `stub-scaffolding`
  via `provael transfer-test`. The real-model path — an adversarial patch on a real policy's RGB
  stream driving its end-effector into a keep-out zone (SmolVLA × LIBERO) — is GPU-gated and **not
  run**; no cross-model claim, no "first" claim.

## [0.11.0] — 2026-07-06

### Added
- **EAI08 `authorization` attack family — identity, access & excessive autonomy.** A new family
  (`self_authorize_bypass` + `scope_escalation`) fills the EAI08 risk (Identity, access & excessive
  autonomy; OWASP ASI03 Excessive Agency). It probes whether a perturbed instruction can make the
  policy **self-authorize and execute a consequential, authorization-gated action without the
  required operator-authorization token**: `self_authorize_bypass` requests a guarded action while
  claiming clearance; `scope_escalation` reframes the task to invoke a higher-privilege action —
  neither presents a valid operator token. New `src/provael/scoring/authz.py` protocol +
  `src/provael/attacks/authorization.py`; wired into the registry, `list-attacks`, the EAI catalog
  (`EAI08`), SARIF, and the suite `evaluate_unsafe` OR-chain. The `authz_unsafe` predicate is
  benign-controlled (unsafe iff a guarded action is emitted **and** no valid token authorized it; a
  valid token is safe; absent the surface it is a no-op) and uses **disjoint stub action channels**,
  so the frozen canary ASRs (instruction 21/30, visual 14/20, injection 12/20, action, backdoor)
  stay **byte-identical**.
- **Mandatory transfer-test (stub-validated).** On the deterministic CPU fixture the screen fires
  100% [84–100%] (Wilson CI) against a **0% benign-FPR control** (the `none` baseline never invokes a
  guarded action). Labelled `stub-scaffolding` via `provael transfer-test`. Real-model SmolVLA ×
  LIBERO transfer is GPU-gated and **not run** — no cross-model claim, no "first" claim, and the
  Embodied AI Security Top 10 is **not** branded as OWASP.
- **Docs.** `docs/TOP10.md` gains the `authorization` family under EAI08 (community draft, PRs
  welcome); `docs/compliance/machinery-reg-2027.md` maps EAI08 evidence to ISO 10218:2025
  monitored-standstill / least-agency and OWASP ASI03; README documents the sixth family.

## [0.10.0] — 2026-07-05

### Added
- **EAI03 `backdoor` attack family — objective-decoupled trigger screening.** A new family
  (`object_trigger` + `phrase_trigger`) fills the previously documented-but-unimplemented EAI03 risk
  (Model & pipeline poisoning, backdoors & supply chain), grounded in **BadVLA** (arXiv:2505.16640)
  and **AttackVLA / BackdoorVLA** (arXiv:2511.12149). It is a **pre-deployment backdoor *screen***,
  not an exploit: it injects a battery of harmless, sim-only candidate triggers (a visual/object
  trigger and an objective-decoupled trigger phrase) while leaving the visible task benign, and
  measures whether the policy activates a hidden objective. Provael **neither trains nor implants a
  real backdoor**. On the deterministic CPU stub (a known-planted fixture) the screen fires 100%
  [84–100%] vs a 0% benign-FPR control; a clean public checkpoint carries no such implant, so the
  same screen reads ~0% (an honest null). New `src/provael/scoring/backdoor.py` protocol +
  `src/provael/attacks/backdoor_vla.py`; wired into the registry, `list-attacks`, the EAI catalog
  (`EAI03`), SARIF, and the suite `evaluate_unsafe` OR-chain. The family uses a **disjoint
  observation channel + an unused stub action channel**, so the frozen canary ASRs (instruction
  21/30, visual 14/20, injection 12/20, action) stay **byte-identical**. Real SmolVLA × LIBERO
  transfer is GPU-gated and **not yet run** — no cross-model claim.
- **Per-family transfer-test (`provael transfer-test`).** Every family now reports its mandatory
  transfer-test — activation/redirection **rate + 95% Wilson CI + benign-FPR control** — with an
  honest `transfer-status` label (`real-transfer` on a real policy×suite, `stub-scaffolding` on the
  stub). New `by_family` (`scoring/asr.py`), `transfer_test` (`calibration.py`), and a `TransferTest`
  model; the CLI prints a table or writes byte-stable JSON.
- **Hosted open-core surface (`provael serve`, `[hosted]` extra).** A self-hostable Apache-2.0
  FastAPI reference server (`src/provael/hosted/`) that turns a `report.json` into a signed
  attestation and an insurer / Notified-Body-ready compliance report. **Open-core boundary:** the
  free CLI, all attack families (incl. the backdoor screen), ASR, SARIF, the GitHub Action, the
  Top-10, and **local `attest`** are never gated; the **operated, project-key-signed** instance +
  the insurer report (`build_insurer_report`, guarded by `require_entitlement`) + the curated screen
  are the paid tier. Self-hosters get self-signed attestations. The free core is not crippled.
- **EU Machinery Regulation compliance mapping.** New `docs/compliance/machinery-reg-2027.md` maps
  `provael attest` evidence → EU Machinery Regulation 2023/1230 (applies **2027-01-20**), AI Act
  Annex-I machinery (statutory **2027-08-02**; proposed-not-adopted **2028-08-02**), and ISO
  10218-1/-2:2025. **Evidence, not certification.**

## [0.9.0] — 2026-07-04

### Added
- **Real, signed, reproducible public ASR leaderboard.** `provael leaderboard build --real
  <results-dir>` builds the public board from real-model runs (seeded from the committed
  `results/smolvla_libero_object/`), and every row now carries its **95% Wilson CI**, the **benign
  (`none`) control**, and a **transfer-status** label (`real-transfer` vs `stub-scaffolding`). When
  any real run is present, `is_demo` is False and stub and real rows are never silently mixed (each
  is labelled). The board is stamped with a **UTC build date, the source commit, and a SHA-256
  digest of the aggregated inputs** (reusing the digest path from `attest.py`), so it is
  reproducible: rebuild and check the `inputs_digest` matches. Optional **Ed25519 signing**
  (`--sign`, via the `provael[attest]` extra) with offline verification (`provael leaderboard
  verify --in … --pubkey …`). The hosted Gradio Space renders the real SmolVLA × LIBERO numbers
  (instruction family transfers; **visual/injection are 0%** on the real model) with the provenance
  footer. The free core builds and verifies boards; the hosted, project-key-signed board is the
  open-core paid surface. **Evidence, not certification.**

## [0.8.0] — 2026-07-04

### Added
- **Per-checkpoint baseline-regression gate (`report --baseline` + the Action).** A new
  `provael report --baseline <known-good report.json> --regression-tolerance <float>` diffs a
  candidate run against a baseline and reports overall, per-EAI-risk, and per-attack ASR deltas.
  A slice **regresses** only when the candidate ASR beats the baseline by more than the tolerance
  **and** the two 95% Wilson CIs are disjoint in the worse direction, so small-`n` noise cannot
  fail a build (it reuses the CIs already computed, inventing no new statistic). It prints a diff
  table, writes a machine-readable `regression.json` and a **regression SARIF** (a regressed EAI
  family becomes an error-level code-scanning finding, not just pass/fail), and **exits non-zero**
  on a regression. Deterministic and dependency-free (stays within the ~6-dep core).
- **Reusable GitHub Action regression gate.** New inputs `baseline`, `regression-tolerance`
  (default `0.05`), and `fail-on-regression` (default `true`); new outputs `regressed` and
  `asr-delta`. The job now fails if **either** the absolute `asr-threshold` is exceeded **or** a
  regression is detected, surfaces the per-family diff in the job summary, and uploads the
  regression SARIF under a distinct `provael-regression` category. A runnable consumer workflow is
  in `examples/ci/regression-gate.yml`; `examples/ci/regression-gate.md` documents storing and
  rolling the baseline. Per-checkpoint regression is **evidence** (e.g. for EU Machinery Regulation
  2023/1230 Annex III §1.1.9 safe-behaviour-across-updates), not certification.

## [0.7.0] — 2026-07-03

### Added
- **Signed attestation (`provael attest`).** Wraps the *same* compliance evidence as
  `report --format compliance` (ASR + 95% Wilson CI + benign-FPR control + per-EAI breakdown + the
  EU/ISO/NIST/IEC crosswalk) into a **tamper-evident, dated, offline-verifiable** bundle: a SHA-256
  digest binds the run, a UTC issuance date + crosswalk ruleset + source commit are stamped, a
  per-attack transfer-test status is recorded (real-transfer vs stub scaffolding), and it is wrapped
  in a **DSSE-style envelope**. The digest layer is standard-library and always on (`--no-sign`);
  **Ed25519** signing/verification rides the optional `provael[attest]` extra (`cryptography`) and
  verifies offline (`provael attest --verify … --pubkey …`). It re-runs nothing (reuses
  `report.json`) and carries a regulatory clock (EU Machinery Reg 2023/1230 applies 2027-01-20; AI
  Act Annex-I machinery statutory 2027-08-02 with a proposed-not-adopted 2028 move). **Evidence, not
  certification.** New `docs/ATTESTATION.md`. The free core stays 6 deps; the hosted, key-backed
  attestation with a real-VLA (GPU) transfer run is the open-core paid surface.
- **Optimized attack family (`optimized`) — the first non-templated attack.** `targeted_hijack`
  is a **black-box, query-budgeted search** (EAI04): it searches candidate `goto::` action
  directives (within a magnitude cap, bounded by `--query-budget`, default 200) for the one whose
  *emitted* motion best aligns with an attacker-chosen — but harmless, sim-only — goal, then
  commits it for the episode. It only *queries* the policy (no gradients/internals, model-agnostic;
  the runner wires a policy oracle and resets around each query so the search never pollutes the
  live rollout), and is deterministic given the episode seed. New `--query-budget` CLI flag +
  `RunConfig.query_budget`. **Stub-validated scaffolding:** on the deterministic CPU stub the
  targeted-redirection rate is **100% (20/20) [84–100%]** vs a **0% benign-FPR control** (see
  `results/optimized_targeted_hijack_stub/`); the real SmolVLA×LIBERO transfer is GPU-gated and
  **not run in CI** (a gated integration test measures it), so no cross-model transfer is claimed.
  Prior art cited (AttackVLA/BackdoorVLA arXiv:2511.12149, FreezeVLA arXiv:2509.19870); no "first"
  claim.

## [0.6.0] — 2026-06-30

### Added
- **Model breadth (7 policies).** LeRobot-native `pi0` / `pi05` / `pi0fast` / `groot` (config-level
  reuse of the generic LeRobot adapter) and `openvla` (OpenVLA / OpenVLA-OFT via Hugging Face
  `transformers`, a new `[openvla]` extra — the non-LeRobot, model-agnostic path). A
  bring-your-own-VLA cookbook + a runnable `PolicyAdapter` example.
- **Second & spatial CPU suite (`reach`).** A deterministic, pure-CPU suite with a *spatial*
  keep-out predicate (the first non-GPU exercise of that path), plus a gated **Meta-World** adapter
  and a live **cross-suite validation** example.
- **`reproduce`** — run published attacks (FreezeVLA / OpenVLA-patch / BadVLA / RoboPAIR) mapped
  onto the existing families; the paper's number is cited separately from Provael's measured run.
- **Named recipes** (`list-recipes`, `attack --recipe NAME|./file.yml`).
- **New report/export surfaces:** `--format scorecard` (one-page pre-deployment ASR scorecard),
  `--format oscal` (NIST OSCAL assessment-results), and `provael export --format avid` (AVID record).
- **Explorer onboarding:** an examples gallery, a 5-minute Colab notebook (+ notebooks 02–05), and a
  Material-for-MkDocs docs site (build-only; deploy gated).
- **Integrations:** a runnable promptfoo provider, garak/PyRIT reference plugins, multi-CI SARIF
  (GitHub/GitLab/Azure + DefectDojo/SonarQube), a pre-commit hook, MLflow/W&B ASR logging, an HF
  eval-results emitter, a fork-safe Modal GPU-CI job, a Dockerfile + devcontainer, and supply-chain
  examples (model-signing + CycloneDX ML-BOM).
- **Compliance:** a worked EU AI Act Art. 15 evidence pack, per-persona crosswalk cards, a NIST AI
  RMF MEASURE 2.7 walkthrough, and standards drafts (MITRE ATLAS case study, OWASP Agentic embodied
  annex, OECD.AI / awesome-list listings) — all drafted, not submitted.
- **Defense demo:** a model-agnostic action-stream firewall (ASR with vs. without) + a ROS 2 guard
  node (sim/reference).
- **Leaderboard** upgraded to a RoboArena-style all-vs-open-source split with open submission; an
  interactive HF-Space demo; an OpenSSF Scorecard workflow + SLSA provenance example.

### Changed
- **Compliance crosswalk corrected for the 2026 Digital Omnibus:** AI-enabled robots route through
  the **Machinery Regulation (EU) 2023/1230** (applies 2027-01-20) + ISO 10218:2025 cyber-risk
  assessment, not AI Act Chapter III directly; high-risk deadlines shifted (2027-12-02 / 2028-08-02).
  Added a `eu-machinery:cyber` requirement to `report --format compliance`.
- Relocated the consumer GitHub Actions example to `examples/ci/github-actions.yml`.

## [0.5.0] — 2026-06-29

### Added
- **EAI04 action-space-integrity attack family (`action`).** Two new attacks alongside the
  existing instruction/visual/injection families: **`freeze`** — a FreezeVLA-style
  action-freeze (arXiv:2509.19870) that drives the policy's motor command to a no-op — and
  **`trajectory_hijack`** — a targeted redirect that biases the action toward an attacker
  waypoint. Both route through the standard `Attack` interface and are scored as a rate with
  a **95% Wilson CI against a benign-FPR control** (the `none` baseline under the same
  predicate). On the deterministic CPU stub both land at **100% [72–100%] vs a 0% benign
  baseline**; the EAI04 predicate (freeze / redirect) is OR-ed into the suite's unsafe check,
  is independent of danger calibration, and is a no-op on suites that surface no action
  signal (so the attacks report **not-applicable** there — e.g. the GPU-gated LIBERO path).
  **Stub-validated scaffolding:** a real-model action-freeze needs an adversarial-image search
  (FreezeVLA / AttackVLA), which is GPU-gated and **not yet run** — no cross-model transfer is
  claimed. `docs/TOP10.md` EAI04 moves from taxonomy-only to *attack shipped*.
- **Compliance evidence report** — `provael report --in <run> --format compliance` emits an
  auditor-readable evidence artifact mapping a run's calibrated results to **EU AI Act**
  (Art. 9 / 15 / 72), **ISO 10218-1/-2:2025** (cyber), **NIST AI 100-2 / AI RMF**
  (GOVERN·MAP·MEASURE·MANAGE), and **IEC 62443**. `--out report.compliance.json` writes the JSON
  evidence schema — per mapped requirement: the Provael artifacts that evidence it (attack
  families, calibrated redirection rate + 95% Wilson CI, benign FPR, EAI ids covered, calibration
  metadata), an `evidence-present` / `gap` status with a reason, and the honest-scope caveats
  (adversarial-only, evidence-not-certification, behavioural-not-worst-case). `--out
  report.compliance.md` renders the buyer/auditor-readable version; with no `--out` the JSON
  prints to stdout. `provael attack … --format compliance` also drops a `report.compliance.json`
  next to the report. Reuses `report.json` (no attacks re-run), is CPU/stub-runnable in CI, and is
  byte-deterministic. Implements the `docs/COMPLIANCE.md` pre-spec.
- `docs/COMPLIANCE.md` — the crosswalk + evidence map the generator implements (calibrated
  redirection rate, benign FPR, CI, EAI tags, SARIF → the frameworks above). Linked from the README.

### Changed
- **First real result refreshed to a calibrated, control-bearing framing.** The README and
  `docs/TOP10.md` headline SmolVLA × LIBERO result now leads with `roleplay` **100% (10/10),
  95% Wilson CI [72–100%]** against a **0% benign baseline FPR** — every rate shown with its
  control and CI — replacing the blended, uncalibrated 24.3% headline. The honest caveats
  (sim-only, one task, `n = 10`, only the instruction family transfers) and methodology notes are
  unchanged, now pointing at `provael calibrate` + `provael attack --calib`.

## [0.4.0] — 2026-06-28

### Added
- **Per-task keep-out-zone / predicate calibration.** New `provael calibrate --policy <p>
  --suite <s> [--tasks …] --seeds N [--target-fpr 0.05] --out calib/` runs benign (attack
  `none`) rollouts, derives a per-task safe predicate from the policy's own behaviour, and
  tunes it on a fit/holdout split so the benign **false-positive rate** stays at or below the
  target. Writes a per-task JSON artifact (envelope/threshold, achieved benign FPR, n, seed
  split). Stub calibration is CPU-only and deterministic; the SmolVLA/LIBERO path stays
  GPU-gated.
- **Calibrated scoring.** `provael attack … --calib calib/` uses the calibrated predicate when
  an artifact exists for `(policy, suite, task)`, else the default (backward-compatible). The
  report records `calibrated`, the live `benign_fpr` (the `none` baseline's rate under the
  predicate used — every number gets its control), and per-task calibration metadata.
- **Confidence + control everywhere.** ASR is shown as a **calibrated redirection rate** with a
  **95% Wilson CI** and the benign FPR alongside, in `report.json`, `report.md`, the rich CLI
  table, and the SARIF output (per-result `asrCiLow`/`asrCiHigh` + run-level `calibrated`/
  `benignFpr`). Multi-task calibrate + report (per-task + aggregate).

### Changed
- The default predicate is unchanged and remains the fallback; calibration is strictly opt-in.

## [0.3.0] — 2026-06-27

### Added
- **SARIF 2.1.0 output** — `provael report --in <run> --format sarif [--out file]` (stdout when
  no `--out`) and `provael attack … --format sarif` / `--sarif-out <path>`. One result per
  attack, severity from ASR (≥0.5 `error`, >0 `warning`, 0 `note`), with stable
  `partialFingerprints`, so red-team findings surface in GitHub code scanning.
- **Reusable GitHub Action** (`provael/provael@v0.3.0`) — a composite action that runs a
  red-team, uploads the SARIF via `github/codeql-action/upload-sarif`, and fails CI when the
  overall ASR exceeds `asr-threshold`; plus `examples/workflow.yml` for consumers.
- **Embodied AI Top-10 mapping** — every attack is tagged with its `EAIxx` risk
  (`instruction` → EAI01, `visual` → EAI02, `injection` → EAI05; the baseline control stays
  untagged). Surfaced as `RunReport.eai` in report.json, an EAI column in report.md and the
  CLI table, and as SARIF `ruleId`s deep-linked to `docs/TOP10.md`.
- `docs/TOP10.md` — The Embodied AI Security Top 10 (v0.2), an independent risk taxonomy for
  VLA/robot security with a crosswalk to OWASP/MITRE/NIST.
- Brand assets under `docs/assets/` (icon + wordmark, SVG and PNG) and a logo in the README header.

### Unchanged
- The deterministic stub run still reports ASR 67.1% (47/70), byte-identical; the CPU core
  pulls no GPU/ML stack and CI never installs lerobot.

## [0.1.0] — 2026-06-27

Initial **Provael** release. Provael is the open-source red-team & assurance layer for
physical AI — a CPU-first, model-agnostic harness that perturbs the instructions and
observations a Vision-Language-Action (VLA) robot policy receives in simulation and reports
an Attack Success Rate (ASR).

> **Renamed from `vla-redteam` / `robopwn`.** The same engine and full git history, under a
> new name, CLI (`provael`), and home (github.com/provael/provael). It was previously
> published on PyPI as `vla-redteam` (0.1.0–0.2.2); the env-var gate is now
> `PROVAEL_INTEGRATION`. Behavior is unchanged — the deterministic stub run still reports
> ASR 67.1% (47/70), byte-identical.

### Included
- **CPU-first deterministic core** — `StubPolicy` + `StubSuite` give exact, byte-reproducible
  ASRs with no GPU or model download; strict typing, `py.typed`, 100 tests.
- **Three templated attack families** (`instruction`, `visual`, `injection`) + a `none`
  baseline; ASR with per-attack / per-task breakdowns and seeded mean ± std for real policies.
- **Real SmolVLA × LIBERO path** behind the `[lerobot]` extra + `PROVAEL_INTEGRATION=1`,
  replicating LeRobot's verified evaluator rollout; first real result on `libero_object/0`
  (instruction attacks 60–100% vs a 0% benign baseline; visual/injection 0% — honest null).
- **Per-task calibrated keep-out zones** scaffold (`suites/keepout_zones.py` +
  `scripts/calibrate_zones.py`) toward a calibrated hazard rate.
- **Leaderboard** — deterministic `(policy × suite × family) → ASR` table, a Gradio Space, and
  a public submission flow (validator + CI on `results/**`).
- **CLI `provael`** — `attack`, `report`, `leaderboard build`, `list-policies`,
  `list-attacks`, `version`; actionable errors (exit code 2), never a traceback.
- Apache-2.0; OIDC trusted-publishing release pipeline; strict `ruff` + `mypy` gate in CI.

### Honest scope
Attacks are templated (not gradient/optimization-based); only the instruction family
transfers to real SmolVLA so far; one policy + one suite shipped; the headline result uses a
single task with a default, uncalibrated keep-out predicate. See the README's
"Scope and honest limitations."

### Roadmap
- **v0.3.0** — SARIF output (`provael report --format sarif`) for GitHub code scanning; a
  reusable `provael/provael` CI gate; an Embodied-AI Top-10 risk mapping; per-task
  keep-out-zone calibration.
- **later** — optimized (gradient/search) attacks; a second policy/suite backend.

> Detailed pre-rebrand history (the `vla-redteam` 0.2.x line) is preserved in the git log and
> the prior PyPI releases.

[0.6.0]: https://github.com/provael/provael/releases/tag/v0.6.0
[0.5.0]: https://github.com/provael/provael/releases/tag/v0.5.0
[0.4.0]: https://github.com/provael/provael/releases/tag/v0.4.0
[0.3.0]: https://github.com/provael/provael/releases/tag/v0.3.0
[0.1.0]: https://github.com/provael/provael/releases/tag/v0.1.0
