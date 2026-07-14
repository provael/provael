# MITRE ATLAS case-study draft — embodied VLA red-team

> **Draft for review — not submitted.** MITRE ATLAS accepts community case studies via GitHub PR
> to `atlas-data` (STIX 2.1). This is the draft we'd propose; opening the PR is gated on sign-off.

ATLAS (https://atlas.mitre.org) is the adversarial-ML ATT&CK analog and is actively soliciting
agent/embodied techniques — its embodied coverage is thin, which is the opening.

## Case study: instruction-jailbreak of a VLA policy in simulation

- **Summary.** A templated instruction reframe (RoboPAIR-style) redirects a Vision-Language-Action
  policy's end-effector out of its benign envelope in simulation, measured by Provael as an Attack
  Success Rate with a benign-FPR control.
- **Target.** Open VLA policy (e.g. SmolVLA) on the LIBERO benchmark.
- **Procedure.** `provael reproduce robopair --policy smolvla --suite libero` (gated, GPU).

## ATLAS technique mapping (proposed)

**Now structured (D5).** This mapping is promoted from prose to the `atlas_techniques` field on each
`provael.eai.CATALOG` entry and surfaced into SARIF rule `properties.atlasTechniques`, so external
validation routes through MITRE ATLAS with zero Top-10 branding conflict (INV-6). The table below is
the human-readable mirror; phrasings are descriptive tactic→technique (not invented `AML.TXXXX` ids)
and flagged *(proposed)* where ATLAS's thin embodied coverage has no on-point technique.

| Provael attack family | EAI | ATLAS tactic → technique (proposed) |
| --- | --- | --- |
| instruction (jailbreak) | EAI01 | ML Attack Staging → prompt-injection / jailbreak of an ML-driven agent |
| visual (patch / decoy / sensor-spoof) | EAI02 | Evasion → adversarial example in the perception channel (craft adversarial data) |
| backdoor (object / phrase trigger) | EAI03 | Persistence → backdoor the ML model; ML Supply Chain Compromise → poison an open-weights checkpoint |
| action / action_space (freeze / hijack) | EAI04 | Impact → manipulate / deny the agent's actuation *(proposed — ATLAS embodied coverage is thin)* |
| injection (scene-text / tool-desc) | EAI05 | Execution → indirect prompt injection via the environment |
| misalignment (embodiment gap) | EAI06 | Impact → unsafe embodied action under a language-benign instruction *(proposed — no on-point ATLAS technique)* |
| authorization (excessive autonomy) | EAI08 | Privilege Escalation → excessive agency / self-authorized guarded action *(proposed)* |
| confidentiality (extraction / membership) | EAI09 | Exfiltration → model extraction / membership inference via the inference interface |

## Evidence

The Provael run emits an AVID record (`provael export --format avid`) and OSCAL
assessment-results; ATLAS case-study fields (summary, target, procedure, references) are drawn from
those plus [docs/TOP10.md](../TOP10.md). RoboPAIR (arXiv:2410.13691) and BadRobot
(arXiv:2407.20242) are the canonical robot-jailbreak references to align to.
