# Provael™

**Prove it. Prevail.** Red-team open **Vision-Language-Action (VLA)** robot policies in
simulation and report an **Attack Success Rate (ASR)**.

Every "proven" red-team tool scores LLM/agent *text I/O*. Provael measures the **action-space** —
*garak scans what the model says; Provael scans what the robot does.*

```bash
pip install provael
provael attack --recipe full-sweep        # all 16 adversarial families (suite-inapplicable ones are skipped)
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
- **Sixteen adversarial families** mapped to the [Embodied AI Security Top 10](top10.md) — 8 of the 10
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
