# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
