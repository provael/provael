# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
