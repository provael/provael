# OWASP Agentic Top-10 — embodied annex (draft)

> **Draft for review — not submitted.** OWASP's GenAI Security Project / Agentic Security
> Initiative takes contributions via Slack + GitHub (permissive licence, no CLA). The 2026 "Top 10
> for Agentic Applications" has **no embodied/physical/robot coverage** — an open white-space this
> annex fills. Engaging the initiative is gated on sign-off.

This annex cross-walks Provael's **Embodied AI Security Top 10 (EAI01–10)** to the OWASP Agentic
Top-10 (ASI01–10), so an agentic-security reader can see where physical-action risk maps and where
it has no text-world analog.

## EAI ↔ ASI crosswalk (proposed)

| EAI (embodied) | Closest ASI (agentic) | Note |
| --- | --- | --- |
| EAI01 policy/instruction jailbreak | ASI: goal manipulation / hijacking | direct analog — but the output is a physical action |
| EAI02 adversarial perception | (weak analog) | physical/sensor channel; no clean text-world equivalent |
| EAI04 action-space integrity (freeze/hijack) | ASI: tool misuse / unexpected execution | the *actuation* is the tool; freeze = denial of action |
| EAI05 indirect/embodied injection | ASI: memory poisoning / insecure inter-agent comms | injection arrives via the *environment* (scene text, objects) |
| EAI10 eval/observability gaps | ASI: human-agent trust / cascading failures | physical incidents are hard to observe/roll back |

## Why an annex (not just a mapping)

Physical action introduces risks the text-world Top-10 doesn't model: irreversibility (you can't
un-grasp), sensor-channel attacks (adversarial patches), and action-space integrity (freeze /
trajectory hijack). The annex proposes these as embodied extensions, with Provael as the
open measurement methodology and EAI01–10 as the reference taxonomy
([docs/TOP10.md](../TOP10.md)).
