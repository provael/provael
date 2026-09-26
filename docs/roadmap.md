# Roadmap

Provael is CPU-first and model-agnostic. Shipped vs. planned, honestly marked. Since 19 September
2026 the roadmap is deliberately short: reliability work the project owes on what it already
claims, and work a customer triggers. Nothing below is a promise of a capability that does not
exist.

## Now: the three proofs, with dates

Nothing else gets built until these exist, unless a named prospect asks for it on a call. Each
removes an objection that blocks every sale — "your unsafe definition is arbitrary", "zero hardware
runs", "no peer review" — and each has a date this page will keep or publicly miss.

1. **A calibrated predicate — target 24 October 2026** ([#136](https://github.com/provael/provael/issues/136)).
   The hand-picked keep-out box fires on 4–5% of benign episodes; ten per-task fits are withheld
   rather than adopted, and a benign-only fit cannot choose the face an attack leaves through. What
   is owed: fit the keep-out zone per task from the benign reachable bounds at a target FPR of 1%
   or less with the face chosen from data, commit the ten calibration JSONs, make
   `PROVAEL_REQUIRE_CALIBRATED=1` the `libero` default, re-run the headline (roleplay plus the four
   controls) and the π0.5 leg under the calibrated predicate, and publish whatever comes out — with
   an erratum, a README and a site change the same day if the headline moves. Beside it, **a
   second predicate a safety engineer recognises**: a contact / force event from the simulator's
   contact API, reported as a second column next to the envelope exit, never in its place — the
   column exists on main since 21 September 2026, not yet in a release (`physical_hazard`,
   `suites.libero.ContactRule`: end-effector force at or above 140 N or an arm link touching a
   non-robot body, read from robosuite's sensor and MuJoCo's contact list, verified against the
   sources and not yet against a live simulator), and
   the re-run is what fills it. The scheduled GPU campaign is **paused** until this lands
   (`.github/workflows/gpu-scheduled.yml`; `watch/campaign.json` says `cadence.paused: true`),
   because it would re-measure with the box.
2. **One real-arm run — published by 31 December 2026, even if null.** The protocol is
   pre-registered ([sim-to-real, SO-ARM101](studies/sim-to-real-so101.md)); the two hardware
   blockers below stand until the arm, the inline supply cut and the voltage trace exist. Then the
   n = 5 protocol with SmolVLA, then 30 trials, per-trial logs and video committed, the result
   published whichever way it comes out.
3. **Peer review — the SPAIS@CoRL 4-pager by 1 October 2026 AoE**, around the measurement
   discipline (benign controls, Wilson and task-clustered intervals, published nulls, errata, the
   π0.5 null); arXiv in November regardless of the decision, the ID into `CITATION.cff` and the
   README. After the calibrated predicate: **the second architecture, properly** — the full π0.5
   leg (50 episodes × the four LIBERO suites with controls) and OpenVLA-OFT or GR00T N1.7 through
   the allenai harness path, October–December, nulls published as nulls.

Still owed alongside them, from what is already published: **complete provenance on every new
committed run** (`tests/test_results_provenance.py` refuses a shard without `repository`, `commit`,
`dep_lock_digest` or `precision` since 20 September 2026) and **one decision, everywhere** (every
export renders the release verdict under a named acceptance protocol since 0.43.0; the remaining
work is a customer protocol agreed before a paid run).

## The freeze (20 September 2026)

- **No new attack families, crosswalks, output formats, recipes or suites** until the three proofs
  and a paid engagement exist. The registry holds 17 adversarial families and 8 have met a real
  policy; the compliance layer already outruns the measurement. A named prospect asking for a
  specific missing capability on a call is the one exception, and it is recorded here when it
  happens.
- **The compliance layer is split into two tiers**, carried on every emitted row (`tier` in
  `provael report --format compliance`, in the dossier, and in the catalogue the website mirrors).
  **Operative** — the route a machinery assessor reads this evidence through, and the one this
  project develops: the **Machinery Regulation 2023/1230**, **ISO 10218:2025**, and the three
  implemented safety/security standards asked for beside it, **ISO 13849**, **IEC 61508**,
  **IEC 62443**. **Reference** — every other mapping (EU AI Act, CRA, NIST, ISO/IEC 42001, 23894,
  TR 5469, ISO 25785-1, Korea, UN R155, ISO/SAE 21434): kept, emitted and checked, not developed
  further. ISO 12100 (risk assessment) and ISO/IEC TS 22440 (draft) belong to the operative
  conversation and are cited in the Machinery pages as references; neither is implemented and
  neither becomes a row under this freeze.
- **Release cadence: one minor every two to four weeks; patch releases only for correctness.**
  Fifty-seven releases in fourteen weeks meant a version-drift risk on every one of them
  (`CITATION.cff` wrong three times, a non-existent Action tag advertised twice) and read as churn.
  Changelog entries are batched into the minor; an incident narrative goes to
  [errata](errata.md), not the changelog.
- **Integration after the hardware run, not before**: the model-server proxy for the allenai
  evaluation harness, an Inspect task, a reimplementation of Trajectory-Level Redirection from its
  released code, and the Isaac Lab-Arena, ROS 2 and planner-level adapters start only once the
  calibrated predicate and the real-arm run exist — they turn this from a rival harness into an
  evidence layer on top of the harnesses that already have models and hardware, and they are
  worth nothing on top of an uncalibrated predicate.

## Customer-triggered (starts when a qualified engagement needs it)

- More attack families and adapters — when a customer's configuration needs the specific missing
  capability, not before (and recorded under the freeze above when it happens).
- A hosted, multi-tenant operated surface with billing — when repeated buyers require hosted
  operation and will pay for its controls; the in-repo server stays an experimental reference.
- Hardware and sim-to-real beyond the one pre-registered run — a funded partner and a facility.
- A certification or insurer-shaped product — a named relying party that specifies and accepts a
  scoped evidence use.
- A full calibration platform — repeated engagements showing the narrow corrected workflow is
  insufficient.

## Shipped

- **Attacks:** 17 adversarial families + a `none` benign control, mapped
  to the [Embodied AI Security Top 10](top10.md).
- **The three-way calibration split, wired end to end (21 September 2026, on main, not yet in a
  release).** The
  calibration command splits benign rollouts into fit / tuning / eval by default and scores the
  eval split only after the threshold or hazard face is chosen, so its FPR is an estimate where
  the tuning split's is a target; the artifact persists the three seed splits and a
  `CalibrationBinding` (seed overlap refused), an eval-split failure is recorded as an invalid
  binding and never re-fitted, and a run re-derives the binding's validity against its own
  checkpoint, suite, task and oracle version (`calibration.<task>.split` / `eval_fpr` /
  `binding` in `report.json`, schema 7). `--split two-way` keeps the historical path. The stub
  is bound and valid; no real policy is — see Planned.
- **Publication freshness as a derivable artifact** (`watch/publish-freshness.json`), shipped in
  **0.41.2**. `watch/freshness.json` answers when *anything* was last measured, and a one-episode
  timing probe satisfies it — on 8 September 2026 a $0.06 probe put that badge at `today` while the
  published 44/50 headline was still measured with v0.32.0, nine minors back. The second window
  that catches this existed in `provael doctor` and nowhere a consumer could read, so anyone wanting
  the same three numbers had to reimplement the rule against `watch/measurements.json` — and a
  reimplemented staleness rule drifts in the reassuring direction by default. See
  [`watch/README.md`](https://github.com/provael/provael/blob/main/watch/README.md) for the whole
  consumption surface and why the two freshness files disagree on purpose.

  This is **not** the cross-repo constant fix; that was `staleAfterReleases` in `watch/release.json`
  in 0.41.1, which www.provael.com now reads instead of holding its own copy.

  Since 18 September 2026 the artifact also carries the body behind the published number and the
  newer body nearest to displacing it (`published`, `challenger`, with `attemptsNeeded` and
  `tasksMissing`), because the lane meant to refresh it could not add up: a canary re-pinned on
  every release, so its version bucket reset before it accumulated, and it ran one task of ten. The
  scheduled lane now measures a declared campaign (`studies/scheduled_campaign/plan.json`) shard by
  shard at one held pin, records a shard only with complete provenance, combines the shards into a
  `campaign.json` that says how complete it is, and publishes its progress as `watch/campaign.json`;
  the rule requires a re-measurement to cover what it replaces before its size counts. What the lane
  cannot do is stated in its own header: at the August-to-September release cadence the campaign
  that displaces the published measurement completes about a dozen minors behind. It moves the
  number; it does not make it current.
- **White-box gradient attacks** (`gradient_patch`), shipped in **0.39.0, 1 September 2026**.
  Untargeted L-inf projected gradient ascent through the policy's own vision encoder, GPU-gated
  and sim-only. This was listed under Planned for two days after it shipped, and neither
  `SAFETY.md` nor this file knew — SAFETY.md still said the registry used no gradients or model
  internals, which by then was false. Corrected in 0.39.3, along with the roadmap-honesty test
  that could not have caught it because an attack family registers no CLI command.

  **Measured status, and the next transfer arm.** Since the 0.42.0 release, `weight_integrity` and
  `gradient_patch` can run against the real SmolVLA x LIBERO adapter (`LeRobotAdapter` exposes the
  `action_out_proj` weights through an INT8 view and backpropagates through its own vision tower),
  and the arm is registered
  and priced as the `whitebox-pilot` stage of
  [`examples/gpu-ci/modal_libero_suite.py`](https://github.com/provael/provael/blob/main/examples/gpu-ci/modal_libero_suite.py)
  (2 tasks x 12 arms x 2 seeds, hard ceiling ~$4, dispatched by hand through `gpu-arm.yml`, never
  scheduled). It has not run. The workstation breadth probe of 14 September already exercised
  `weight_integrity` and `gradient_patch` against SmolVLA on one task at three seeds (0/3 each,
  with applicable episodes, which is why `realPolicyTested` in `watch/registry.json` already
  counts them: **8 of 17**); this arm is the powered version of that probe, and no rate is stated
  here before its result is committed under `results/`.
- **Policies:** `stub` (CPU); `smolvla`, `pi0`, `pi05`, `pi0fast`, `groot` (LeRobot); `openvla`
  (HF transformers); `openpi` (websocket client to a π0 policy *server*). Bring-your-own via the
  `PolicyAdapter` ABC. **`groot`, `openvla` and `openpi` are registered scaffolding** — no
  checkpoint has been loaded through any of them here, and `provael list-policies` says so per
  backend. `smolvla` (the ten-task suite) and `pi05` (a three-seed preliminary leg on the same
  tasks, 18 September 2026) have committed real-model results.
- **Suites:** `stub` (scalar, CPU), `reach` (spatial, CPU), `humanoid` (whole-body, CPU),
  `libero` + `metaworld` (real simulators, gated); `vla_arena` (VLA-Arena's declared per-step
  cost predicate as `is_unsafe()`, LIBERO-shaped policy path — **registered scaffolding** until its
  first committed run; needs its own Python 3.11 environment). `provael list-suites` marks which
  is which.
- **Evidence:** SARIF, compliance crosswalk, pre-deployment scorecard, OSCAL export, AVID export.
- **Reproductions:** FreezeVLA, OpenVLA-patch, BadVLA, RoboPAIR.
- **Integrations:** promptfoo provider; garak/PyRIT reference plugins; multi-CI (GitHub/GitLab/
  Azure) SARIF; pre-commit; MLflow/W&B logging; HF eval-results; Modal GPU-CI; Docker/devcontainer;
  supply-chain: **checkpoint-integrity verification shipped in 0.27.0** (pinned-digest + pickle
  refusal, fail-closed, in the reusable Action — see
  [checkpoint-integrity](checkpoint-integrity.md)); the CycloneDX **ML-BOM ships** (`provael report
  --format mlbom`), while model-*signing* (Sigstore) remains planned. The public leaderboard is
  Ed25519-signed as of 0.27.0.
- **Public leaderboard with open submission — SHIPPED, and this line was wrong until 22 Aug 2026.**
  `provael submit` has been in every release since **0.32.0**, `CONTRIBUTING-leaderboard.md` documents
  the PR route, and `leaderboard-submission.yml` validates submissions on `results/**`. It sat under
  *Planned* while the Shipped section above already said the board is Ed25519-signed — the file
  contradicted itself. **Zero external submissions have arrived**, which is the honest reason it felt
  unshipped, and is a fact about adoption rather than about the code.
- **Defenses — what is measured and what is not.** Two of the six `docs/defenses.md` taxonomy rows
  are measured under the protocol, both `stub-validated-scaffolding` on CPU fixtures:
  `instruction_canonicalization` (input side) and `action_envelope` (action side). The action-envelope
  study is `credited` on `stub` and `reach` and **`not-credited` on `humanoid`**, and both studies
  open by stating how much of their own credit is circular on a fixture. **No real-model transfer is
  claimed for either defense.** The four remaining rows are *specified and unproven*; three of them
  act on the policy's output and became expressible only with `Defense.filter_action` in 0.28.0.
  The ROS 2 guard node stays a sim/reference node that makes no measurement claim.
- **Optimized attacks (in progress):** the `optimized` family — `targeted_hijack`, a black-box,
  query-budgeted search — is the first non-templated attack (stub-validated; real transfer gated).

- **Docs-site versioning** (`mike`), tag-driven for the alias. A tagged release publishes a
  versioned docs set and moves the `latest` alias; since 20 September 2026 a push to `main`
  publishes `main` as its own unaliased version at `/dev/`, moving nothing. The version selector
  renders from `extra.version.provider: mike`.

    **This reverses a decision recorded earlier the same day (2 September 2026), and the reversal is
    the interesting part.** The objection was never to versioning — it was that `mike` namespaces
    every page under a version path, so `docs.provael.com/top10/` becomes `/latest/top10/` and the
    root URL 404s. Those URLs are cited from the marketing site and named in the Top 10's own
    BibTeX. The earlier entry said what would make it acceptable: *every retired URL gets a stub,
    the same way the uppercase→lowercase rename was handled.* That is what
    [`scripts/gen_root_stubs.py`](https://github.com/provael/provael/blob/main/scripts/gen_root_stubs.py)
    now does — it walks the published alias after each deploy and writes a meta-refresh page at
    every root path that would otherwise be dead, and the docs smoke job probes both forms. The
    cost was paid rather than argued away; an old URL stays old forever.

    Two things were found while wiring it, both of which would have shipped broken. `mike`'s default
    `alias_type` writes `latest` as a git **symlink** (mode 120000), and GitHub Pages does not serve
    symlinked directories — every `/latest/…` URL would have 404'd, so the deploy pins
    `--alias-type=copy`. And `alias_type: redirect`, the other option, would have made every alias
    URL bounce to a **dated** `/0.39.2/…` path, which defeats the point of having an alias at all.

    **What this cost, and the remedy now wired:** between 2 and 20 September 2026 `main` did not
    publish, so a docs fix waited for the next release — a narrowed version of the incident
    push-on-main was introduced to fix. The remedy named at the time is in place: `main` publishes
    as its own unaliased version at `/dev/` on every push (`.github/workflows/docs.yml`), `latest`
    still means the newest release, the root stubs still point at `latest`, and the smoke probes
    `/dev/` on every deploy.

## Blocked on hardware — sim-to-real (SO-ARM101)

**Runs executed to date: 0**, and none will run until both prerequisites below exist. The protocol
is pre-registered in [docs/studies/sim-to-real-so101.md](studies/sim-to-real-so101.md) and published
at [provael.com/sim-to-real](https://www.provael.com/sim-to-real/); it was amended on
**1 September 2026, before any trial**, and the amendment created these two blockers. They are
recorded here because a dependency visible only inside the study it blocks is not visible at all.

- **An inline cut on the DC supply.** The STS3215's own over-current protection is not a latch — the
  output is disabled only until the next position command arrives. This study's threat model is a
  policy that keeps streaming commands, so it re-arms the servo it just faulted. The protection
  holds under benign teleop and fails under precisely the condition being tested, so the e-stop this
  protocol depends on has to be a physically operated inline cut on the supply. **No kit ships one**;
  it is a required addition, not an assumption.
- **A per-trial servo-bus voltage trace.** The kits ship a 12 V 7.5 A supply while per-servo
  over-current protection trips above ~2 A, so six servos accelerating together can demand more than
  the supply delivers. The failure is voltage sag, torque loss mid-motion, and the arm falling — and
  it is **biased toward the hypothesis**, because adversarial action sequences are jerkier and drive
  more joints at once than benign teleop, making the attacked condition the more likely one to brown
  out. An arm that loses torque above a keep-out zone falls into it. Unmeasured, a power fault is
  indistinguishable from a successful redirection, in the direction that flatters the result.

Neither is a software task, so neither can be closed by anything in this repository. Until both are
in place, the honest state of the real-robot arm of this work is zero trials, and any sim/real
comparison here would be reporting a hardware fault as a finding.

## Planned (contributions welcome) — every item conditional

- **Real-policy calibration validity (conditional on the 24 October re-run).** The three-way
  calibration path is shipped (see Shipped); what has not happened is the condition that matters,
  a fresh supported real-policy calibration run under it. Until that lands every real-policy
  number is measured under the uncalibrated default box, no real-policy calibration validity is
  claimed, and the honest offer stays the explicitly uncalibrated robustness diagnostic.
- **Suites (conditional on a customer needing one):** RoboCasa, CALVIN, SimplerEnv, and the AI2 vla-evaluation-harness bridge (one adapter
  → ~18 benchmarks at the harness's v0.4.0; v0.5.0 exposes 20). See
  [examples/suites](https://github.com/provael/provael/tree/main/examples/suites).

    **Scaffolding exists, and it is not a bridge yet.** The `ai2_bridge` suite is registered and
    listed as *scaffolding — no benchmark ever run*; every contract method raises. It was written
    against a reading of the harness that its maintainer corrected in
    [allenai/vla-evaluation-harness#127](https://github.com/allenai/vla-evaluation-harness/issues/127)
    (8 September 2026): the end-effector state **does** reach the model-server side with
    `send_state: true`, and `StepRecorder` is the intended hook for a second writer. So the
    supported route is a **model-server proxy** that perturbs what the policy sees and scores the
    pose it receives — the plugin work above, after the calibrated predicate and the hardware run —
    not a suite adapter on the caller side. The benign control arm is expressible either way. Full
    notes, with the correction on top, in [docs/studies/ai2-bridge-notes.md](studies/ai2-bridge-notes.md).
- **Standards (submissions and proposals until a body accepts them):** MITRE ATLAS case study, OWASP Agentic embodied annex, OECD.AI listing (drafts in
  [docs/standards](https://github.com/provael/provael/tree/main/docs/standards)).
- **Stronger attacks (conditional on a customer or a funded study):** gradient-based adversarial **suffixes** (GCG-style) and a real-model
  transfer of the `optimized` family beyond the stub. The white-box *patch* half of this line
  shipped in 0.39.0 and has moved to Shipped above; what is left here is the text-side white-box
  work, which is not implemented.

!!! note
    "Planned" means not yet shipped — we don't ship fabricated capability. Each lands behind tests
    and the same honesty discipline as the rest of the project.
