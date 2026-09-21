# Provael™

**Prove it. Prevail.** Red-team open **Vision-Language-Action (VLA)** robot policies in
simulation and report an **Attack Success Rate (ASR)**.

Every "proven" red-team tool scores LLM/agent *text I/O*. Provael measures the **action-space** —
*garak scans what the model says; Provael scans what the robot does.*

```bash
pip install provael
provael attack --recipe full-sweep        # all 17 adversarial families (suite-inapplicable ones are skipped)
```

[Quickstart](quickstart.md){ .md-button .md-button--primary }
[Examples gallery](examples.md){ .md-button }
[Open in Colab](https://colab.research.google.com/github/provael/provael/blob/main/notebooks/01_provael_in_5_minutes.ipynb){ .md-button }

## What it is

A small, **model-agnostic** harness that perturbs the instructions and observations a VLA policy
receives inside a simulator and measures how often those perturbations drive it into an *unsafe*
state. The headline number is the ASR, reported with a 95% Wilson CI and a benign-FPR control.

- **CPU-first.** The whole engine (attacks, scoring, runner, report, CLI) runs and is tested on a
  plain CPU with a deterministic stub. Real policies (SmolVLA, π0, GR00T, OpenVLA…) and real
  simulators (LIBERO, Meta-World) live behind optional extras + a `PROVAEL_INTEGRATION` gate.
- **Seventeen adversarial families** mapped to the [Embodied AI Security Top 10](top10.md) — 8 of the 10
  categories (EAI01–06, EAI08, EAI09): `instruction`, `visual`, `sensor_spoof`, `injection`, `action`,
  `action_space`, `backdoor`, `authorization`, `confidentiality`, `misalignment`, `humanoid`, plus the
  black-box, query-budgeted searches `optimized`, `optimized_patch`, `universal_patch` and
  `optimized_instruction`.
- **Evidence, not certification.** SARIF, an OSCAL assessment-results export, an AVID record, and a
  compliance crosswalk — see [Compliance](compliance/index.md).

!!! warning "Defensive, sim-only"
    Provael is a defensive tool for hardening policies via responsible disclosure. It drives no
    physical robots and ships no real-world-harm payloads. Stub numbers are properties of the test
    fixture, not of any real VLA — see [Sim predicts real](sim-predicts-real.md).

## If you would rather not run it yourself

The CLI, every attack family, the ASR with its benign control, SARIF, the GitHub Action and local
attestation are free and always will be. Nothing below is required to use any of it.

These docs had no route to the operated work at all — a reader who got here, decided the tooling was
right and wanted someone to run it had nowhere to go but the back button.

- **[Read the deliverable first](https://www.provael.com/sample-evidence-pack)** — the evidence pack
  an assessment produces, in full, before any conversation.
- **[Assessment and pricing](https://www.provael.com/pricing)** — what the operated work costs and
  what it includes.
- **[Design partners](https://www.provael.com/design-partners)** — a founding rate in exchange for
  the right to publish the result.

## Why the policy layer

> *Moved here from the repository README on 20 September 2026, when the README was cut to what a new reader needs. The text is as it stood there; links were re-pointed.*


The fielded robot-security incidents so far — **UniPwn** (CVE-2025-60250 / CVE-2025-60251), the
**Unitree Go1** backdoor (CVE-2025-2894), and **G1** telemetry exfiltration — are **firmware /
supply-chain** bugs. Real, serious, and a **different layer**. Provael™ red-teams the **VLA policy
itself** (EAI01–EAI06): the language-conditioned control policy that *becomes* the fielded attack
surface as robots gain language-driven autonomy — and the layer a text-only jailbreak tool
structurally can't reach, because a prompt that stays "safe" in text can still drive an **unsafe
trajectory**. That gap is what the measured result above is about. See the
[Embodied AI Security Top 10](top10.md).

Everything in the core — abstractions, attacks, scoring, runner, report, CLI, leaderboard — runs
and is tested on a **plain CPU with no GPU and no model/dataset download**, using the
deterministic `StubPolicy` + `StubSuite`; real policies (SmolVLA via LeRobot) and the LIBERO
simulator live behind an optional extra and a `PROVAEL_INTEGRATION=1` gate. New here? The
[Colab notebook](https://colab.research.google.com/github/provael/provael/blob/main/notebooks/01_provael_in_5_minutes.ipynb)
runs it in a browser; the [examples gallery](https://github.com/provael/provael/blob/main/examples/) and `provael list-recipes` are the next
two stops.

## Scope and honest limitations

> *Moved here from the repository README on 20 September 2026, when the README was cut to what a new reader needs. The text is as it stood there; links were re-pointed.*


This is an **early, research-grade** harness, built to be reproducible and honest rather than
to oversell. Before you trust a number, know:

- **Everything here is simulation. No number in this repository has ever been produced on
  physical hardware.** Provael has never been run against a real robot, a real controller or a
  real safety PLC, and it is not built to be. Every ASR is a claim about the simulator that
  produced it — **not** evidence that the same policy fails the same way on a bench. That gap is
  not a formality: an adversarial patch here is composited into a frame as an array, and is never
  printed, photographed, or subjected to lighting, viewing angle, print gamut, motion blur or
  sensor noise — the factors that decide whether a simulated patch survives contact with a camera.
  A patch that works at 100% in this harness may do nothing on a bench, and a policy that looks
  clean here may still fail physically for reasons the harness cannot see.
  **We have not measured sim-to-real transfer, and we do not claim it.** Establishing it needs a
  hardware lab and a published study; until one exists, read every number as simulator-scoped.
  (Independent groups such as [Robocurve](https://www.ycombinator.com/companies/robocurve) make the
  same point from the performance side — models strong in simulation show large real-world gaps.)
- **Mostly templated attacks, plus four optimized search families.** Most attacks are auditable
  string/observation templates (instruction reframings, image markers, scene text) — behavioral
  probes, not gradient-based worst-case robustness. Four **optimized** families now also ship as
  bounded-budget *searches*: `optimized` (`targeted_hijack`, action-directive), `optimized_patch`
  (`patch_hijack`, adversarial patch — GPU-gated), `universal_patch` (one patch fit **once** then
  frozen and carried to episodes and tasks it never queried — the constraint a *printed* sticker
  actually faces, where `patch_hijack` re-optimises per episode; GPU-gated, and its transfer rate
  is **unclaimed** until that run happens), and `optimized_instruction` (`targeted_redirect`)
  — an optimized, **command-preserving** instruction search that redirects the policy through subtle
  manner/urgency cues while keeping the operator's command and never naming the target object. Its
  recommended mitigation is **instruction canonicalization / repair** (normalise phrasing, strip
  redundant manner/urgency adverbials, re-derive the canonical command), which collapses the search's
  edit space — see [PRIOR_ART.md](https://github.com/provael/provael/blob/main/PRIOR_ART.md). Gradient-based (GCG/PGD-style) VLA attacks remain an
  open roadmap item (cf. prior art **BadVLA**, **AttackVLA**).
- **Only the instruction family clears the floor on the measured policy, and it is fragility,
  not control.** On SmolVLA × LIBERO-Object (ten tasks, 42/50 `roleplay` against a 1/50 benign
  floor on 0.41.2), the visual and injection arms sit at the floor — measured, published nulls.
  The 14 September controls ([E-2026-12](errata.md)) show the same frame with no target
  named and with its tokens scrambled leaving the envelope too: the policy is fragile under a
  long, imperative, out-of-distribution string, and the attacker is not choosing where it goes.
- **EAI04 (`action` + `action_space`) is stub-validated — and its transfer study confirms it does
  not reach a real policy through this mechanism.** On the deterministic `reach` keep-out fixture all
  four vectors (`freeze`, `trajectory_hijack`, `keepout_hijack`, `critical_freeze`) fire 100%
  [72–100%] vs a 0% benign-FPR control (BH-FDR significant). But they inject an *out-of-band directive
  channel a real VLA ignores*, and LIBERO surfaces no action-integrity signal — so on the real
  SmolVLA/π0 path they are **not-applicable** (verified), not merely pending. A real
  action-freeze/hijack needs the GPU-gated adversarial-image search (FreezeVLA / AttackVLA; see the
  `optimized_patch` family). Full write-up:
  [docs/studies/eai04-action-space-transfer.md](studies/eai04-action-space-transfer.md)
  (`provael study eai04`).
- **The envelope-exit effect is shown on one policy, and its transfer is not.** Two real
  architectures have a committed arm: SmolVLA (the body above) and π0.5, whose preliminary
  18 September 2026 leg (three seeds, two of eight arms) put `roleplay` at the benign floor,
  1/30 against 0/30 — no transfer is claimed. The **π0-via-openpi** leg, which tests the
  framework rather than the architecture, is GPU-gated and not yet run. Generality is an adapter
  interface; it is shown only where a run exists, and the count of policies with a committed arm
  is derived, never typed (`realPoliciesTested` in [`watch/registry.json`](https://github.com/provael/provael/blob/main/watch/registry.json)).
- **Every rate ships with its control, and the decision is separate from the measurement.** A
  rate is published with its 95% interval and the benign floor it is read against; a release
  verdict is made only under a named acceptance protocol, and without one every artifact says
  `incomplete — not assessed`. `provael calibrate` fits the unsafe predicate per task from the
  policy's own benign rollouts to a benign-FPR target on a tuning split, then measures the FPR
  again on an eval split of a three-way fit and binds it to the checkpoint, task and oracle; apply
  it with `provael attack --calib`. See [Calibration](quickstart.md#calibration).

Honesty and reproducibility are the point — see
[PRIOR_ART.md](https://github.com/provael/provael/blob/main/PRIOR_ART.md) for how this sits
next to the academic state of the art.
