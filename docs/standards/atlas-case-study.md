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

| Provael attack family | EAI | ATLAS tactic / technique (proposed) |
| --- | --- | --- |
| instruction (jailbreak) | EAI01 | *ML Attack Staging* → prompt-injection / jailbreak of an ML-driven agent |
| visual (patch/decoy) | EAI02 | *Initial Access / Evasion* → adversarial example in the perception channel |
| injection (scene-text / tool-desc) | EAI05 | *Execution* → indirect prompt injection via the environment |
| action (freeze / hijack) | EAI04 | *Impact* → manipulate the agent's actuation / denial of robot action |

## Evidence

The Provael run emits an AVID record (`provael export --format avid`) and OSCAL
assessment-results; ATLAS case-study fields (summary, target, procedure, references) are drawn from
those plus [docs/TOP10.md](../TOP10.md). RoboPAIR (arXiv:2410.13691) and BadRobot
(arXiv:2407.20242) are the canonical robot-jailbreak references to align to.
