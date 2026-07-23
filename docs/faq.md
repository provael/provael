# FAQ

**UniPwn is a firmware bug — why do I need a VLA red-teamer?**
Because they are **different layers**, and both have to hold. The fielded robot-security incidents
so far — **UniPwn** (CVE-2025-60250 / CVE-2025-60251), the **Unitree Go1** backdoor
(CVE-2025-2894), **G1** telemetry exfiltration — are **firmware / supply-chain / comms** bugs: an
attacker who already has a foothold in the device or its update channel. Provael maps those to
**EAI07** (CPS / firmware / comms) and deliberately leaves them to the tools built for that layer —
CVE scanners, SBOM/supply-chain, pentest. What Provael red-teams is the layer *above*: the **VLA
policy** (EAI01–EAI06), the language-conditioned control policy that turns an instruction into a
trajectory. That layer **becomes** the fielded attack surface as robots gain language-driven
autonomy, and a text-only jailbreak tool structurally can't reach it — a prompt that a language
filter passes as "safe" can still drive the *arm* into an unsafe trajectory (the embodiment gap).
Our real-model finding is exactly this: a single benign-looking `roleplay` instruction drove a real
SmolVLA policy out of its safe envelope 100% of the time (10/10, 95% CI [72–100%]) against a 0%
benign control — a policy-layer failure no firmware patch addresses. Full write-up:
[The instruction-transfer finding](findings/2026-instruction-transfer.md); the layer split is the
[Embodied AI Security Top 10](TOP10.md).

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
