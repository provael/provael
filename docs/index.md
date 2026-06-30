# Provael

**Prove it. Prevail.** Red-team open **Vision-Language-Action (VLA)** robot policies in
simulation and report an **Attack Success Rate (ASR)**.

Every "proven" red-team tool scores LLM/agent *text I/O*. Provael measures the **action-space** —
*garak scans what the model says; Provael scans what the robot does.*

```bash
pip install provael
provael attack --recipe full-sweep        # all four attack families on the CPU stub
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
- **Four attack families** mapped to the [Embodied AI Security Top 10](TOP10.md): `instruction`,
  `visual`, `injection`, `action`.
- **Evidence, not certification.** SARIF, an OSCAL assessment-results export, an AVID record, and a
  compliance crosswalk — see [Compliance](COMPLIANCE.md).

!!! warning "Defensive, sim-only"
    Provael is a defensive tool for hardening policies via responsible disclosure. It drives no
    physical robots and ships no real-world-harm payloads. Stub numbers are properties of the test
    fixture, not of any real VLA — see [Sim predicts real](SIM_PREDICTS_REAL.md).
