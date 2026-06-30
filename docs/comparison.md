# Provael vs. the LLM red-team tools (for embodied AI)

The mature AI red-team tools — **garak**, **PyRIT**, **promptfoo**, **Giskard** — are excellent,
and Provael does not replace them. They score an LLM/agent's **text I/O**. Provael scores a robot
policy's **action-space**. They answer *"what does the model say?"*; Provael answers *"what does
the robot do?"*

## Where each fits

| | garak / PyRIT / promptfoo / Giskard | **Provael** |
| --- | --- | --- |
| Target | LLM / agent text I/O | VLA **action policy** in a simulator |
| Success signal | toxic/jailbroken/leaked **text** | policy driven to an **unsafe action** (ASR) |
| Environment | prompt → completion | reset/step rollout with an unsafe predicate |
| Risk taxonomy | OWASP LLM / Agentic Top-10 | **Embodied AI Security Top-10** (EAI01–10) |
| Output | findings / scores | ASR + 95% CI + benign-FPR control, SARIF, OSCAL, AVID |

## Use them together

Provael ships [integrations](https://github.com/provael/provael/tree/main/examples/integrations)
so it runs *inside* those tools, not against them:

- **promptfoo** — a custom provider runs Provael's embodied scan as a promptfoo eval row.
- **garak** — a reference probe brings the action-space dimension into a garak run.
- **PyRIT** — a reference PromptTarget surfaces a Provael scan.

A complete program red-teams the **LLM brain** with garak/PyRIT/promptfoo **and** the **embodied
body** with Provael. The action-space is the part the text-only tools structurally cannot reach —
which is the whole reason Provael exists.

> Honest framing: Provael's attacks are templated/auditable screens, not gradient-optimised
> worst-case attacks; it's sim-only and evidence-not-certification. See the
> [FAQ](faq.md) and [scope](SIM_PREDICTS_REAL.md).
