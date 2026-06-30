# FAQ

**Is it only simulation?**
Yes — Provael is a pre-deployment scanner. The literature says sim/edited-image red-teaming
predicts real-robot brittleness well enough to be useful (Predictive Red Teaming, MAE < 0.19) —
see [Sim predicts real](SIM_PREDICTS_REAL.md). Treat ASR as a floor on susceptibility, not a
guarantee.

**Do the stub numbers mean anything about real VLAs?**
No. The stub is a deterministic *test fixture* so the whole engine is testable on a CPU. Its ASRs
are properties of the fixture. Real-model runs (GPU + `[lerobot]`) produce real numbers with CIs
and a benign-FPR control.

**Which models can I red-team?**
`stub` (CPU) plus `smolvla`, `pi0`, `pi05`, `pi0fast`, `groot` (via `[lerobot]`) and `openvla`
(via `[openvla]`). Any policy implementing the `PolicyAdapter` ABC works — see
[Python API](python-api.md).

**Which simulators?**
`stub` (scalar, CPU) and `reach` (spatial, CPU) ship pure-CPU; `libero` and `metaworld` wrap real
simulators behind `[lerobot]`. More are on the [roadmap](roadmap.md).

**Are these real adversarial attacks?**
They're templated, auditable perturbations — a screen, not gradient/search-optimised worst-case
attacks. That's deliberate (reproducible, inspectable). `provael reproduce` maps published attacks
(FreezeVLA, RoboPAIR…) onto these families and cites each paper's number separately from ours.

**Does running Provael make my system compliant?**
No. It produces *engineering evidence* (SARIF / OSCAL / AVID / a compliance crosswalk) you can put
into a conformity or assurance file. It is not certification and not legal advice. See
[Compliance](COMPLIANCE.md).

**Is it a runtime safety controller?**
No. The runtime firewall example is a *sim/reference* monitor for demonstrating a red-team → harden
loop, not a certified safety controller (that's NVIDIA Halos / ISO 26262 territory).
