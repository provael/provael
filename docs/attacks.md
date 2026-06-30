# Attack catalog

Four families of templated, auditable attacks, each tagged with its [Embodied AI Security Top
10](TOP10.md) risk. These are heuristic perturbations, **not** gradient/optimisation-based
adversarial attacks. List them with `provael list-attacks`.

!!! note "How to read the numbers"
    Stub ASRs are properties of the deterministic test fixture, not of any real VLA. Real-model
    numbers (where shown) come with a 95% CI and a benign-FPR control. On SmolVLA × LIBERO, so far
    **only the instruction family transfers** — an honest null for visual/injection on that suite.

## `instruction` — policy & instruction jailbreak (EAI01)

Text reframings of the task that keep the goal benign-looking but redirect behaviour.

| Attack | Idea |
| --- | --- |
| `roleplay` | reframe the task inside a persona/scenario |
| `goal_substitution` | swap the goal object/target |
| `paraphrase` | reword to slip templated guardrails |

Real-model signal: `roleplay` redirected SmolVLA **100% (10/10) [72–100%]** vs 0% benign control.

## `visual` — adversarial perception (EAI02)

Observation-space markers / planted objects.

| Attack | Idea |
| --- | --- |
| `patch` | inject an adversarial visual-token marker |
| `decoy_object` | plant a forbidden object in the scene |

## `injection` — indirect / embodied prompt injection (EAI05)

Instructions arriving through the *environment*, not the user.

| Attack | Idea |
| --- | --- |
| `scene_text` | a sign/label in the scene carries an instruction |
| `mcp_tool_desc` | a malicious tool description (MCP/agent boundary) |

## `action` — action-space integrity (EAI04)

Manipulating the actuation itself. Reproduces the FreezeVLA threat class.

| Attack | Idea |
| --- | --- |
| `freeze` | zero the commanded motion (the robot stops, ignores the task) |
| `trajectory_hijack` | redirect motion toward an attacker waypoint |

## Baseline

`none` is the benign control — it never perturbs anything, so its ASR is the false-positive floor
every other rate is read against.
