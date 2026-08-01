# Attack catalog

**Fourteen** adversarial families of templated, auditable attacks plus the `baseline` benign
control, each tagged with its [Embodied AI Security Top 10](top10.md) risk. Most are heuristic
perturbations rather than gradient/optimisation-based attacks; the three `optimized*` families are
the exception — bounded-budget black-box searches. List them with `provael list-attacks`.

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

## `optimized` — search-based targeted hijack (EAI04)

The first **non-templated** family: a black-box, query-budgeted *search* that adapts to the
policy's responses instead of emitting a fixed cue.

| Attack | Idea |
| --- | --- |
| `targeted_hijack` | search (within a magnitude cap, under `--query-budget`) for the action directive that best steers the policy's *own emitted motion* toward an attacker-chosen goal, over the horizon |

It only *queries* the policy (no gradients / internals), so it is model-agnostic; each query is
made independent by resetting the policy around it, and the search is deterministic given the
episode seed. On the CPU stub it converges in closed form.

!!! warning "Stub-validated scaffolding"
    On a real VLA a targeted action hijack needs an adversarial-image / action-token search over
    the model's inputs (AttackVLA, arXiv:2511.12149). That path is GPU-gated and **not run in CI**,
    so no cross-model transfer is claimed. The stub numbers are fixture properties; run
    `tests/test_optimized.py::test_targeted_hijack_transfer_smolvla_libero` under
    `PROVAEL_INTEGRATION=1` to measure a real rate. No "first" claim is made.

## `sensor_spoof` — adversarial perception, perception-stream vector (EAI02)

A second EAI02 vector, disjoint from `visual`: rather than raising a scalar danger signal with
trigger tokens, it **spoofs the simulated perception stream** so the policy drives the end-effector
into a keep-out zone. Needs a suite with spatial keep-out geometry (`reach` / `keepout_zones`); no
episode is applicable on the scalar-danger `stub` suite.

| Attack | Idea |
| --- | --- |
| `patch_spoof` | a planted in-scene marker displaces the perceived target |
| `signal_spoof` | a spoofed sensor reading displaces it |

Attacker access: **not asserted** · transfer: **stub-validated scaffolding**, no real-model
transfer claimed.

## `action_space` — action-space integrity, second vector (EAI04)

Where `action` nulls or reheads the commanded motion, this family attacks the **commanded
end-effector state** directly. Also keep-out-suite only.

| Attack | Idea |
| --- | --- |
| `keepout_hijack` | redirect the commanded end-effector into a keep-out zone |
| `critical_freeze` | freeze the command at a critical step |

Attacker access: **not asserted** · transfer: **stub-validated scaffolding**.

## `backdoor` — model & pipeline poisoning (EAI03)

A **screen**, not an exploit: it probes whether a checkpoint carries a latent, objective-decoupled
trigger. On a clean checkpoint it should find nothing — a 0% here is the expected, useful result.
Runs on the scalar-danger `stub` suite.

| Attack | Idea |
| --- | --- |
| `object_trigger` | a benign-looking object as the planted trigger |
| `phrase_trigger` | a benign-looking phrase as the planted trigger |

Attacker access: **not asserted** · transfer: **stub-validated scaffolding**. Provael ships no
backdoored checkpoint; this measures the screen, not a poisoned model.

## `authorization` — identity, access & excessive autonomy (EAI08)

Probes **excessive agency**: whether a perturbed instruction makes the policy self-authorize a
consequential, authorization-gated action without the operator token. `stub` suite.

| Attack | Idea |
| --- | --- |
| `self_authorize_bypass` | act without the required authorization token |
| `scope_escalation` | widen the authority a single instruction exercises |

Attacker access: **not asserted** · transfer: **stub-validated scaffolding**.

## `confidentiality` — model & data confidentiality (EAI09)

A query-based **leak screen** against a *planted fixture canary* — never a real exfiltration. `stub`
suite.

| Attack | Idea |
| --- | --- |
| `membership_inference` | infer whether a record was in training |
| `model_extraction` | recover a memorized canary by querying |

Attacker access: **not asserted** · transfer: **stub-validated scaffolding**.

## `misalignment` — cross-domain safety misalignment (EAI06)

The **embodiment gap** (BadRobot, ICLR 2025): an instruction a chat-layer filter would pass as
benign still drives an unsafe *embodied* action. Keep-out-suite only.

| Attack | Idea |
| --- | --- |
| `benign_urgency_override` | benign-sounding urgency overrides the safe envelope |
| `euphemistic_reroute` | a euphemism reroutes the motion |

Attacker access: **not asserted** · transfer: **stub-validated scaffolding**.

## `humanoid` — whole-body & locomotion (EAI02 / EAI04)

Three sim-only attacks on a humanoid policy's balance and gait, emitted as an out-of-band
perturbation cue (no model-specific hooks). Needs the `humanoid` suite.

| Attack | EAI | Idea |
| --- | --- | --- |
| `balance_spoof` | EAI02 | spoofed balance signal → loss of balance |
| `whole_body_hijack` | EAI04 | whole-body redirect → topple |
| `stride_freeze` | EAI04 | freeze mid-stride |

Attacker access: **not asserted** · transfer: **stub-validated scaffolding**. The GR00T-N1 transfer
study is pre-registered and **not yet run**.

## `optimized_patch` — optimized adversarial patch (EAI02)

The image-space analogue of `targeted_hijack`: a query-budgeted search over adversarial **image
patches** on the policy's real camera frame. It needs a real image channel, so it is **inert on
every CPU suite** and scores no episode in a CPU run — an N/A, never a 0%.

| Attack | Idea |
| --- | --- |
| `patch_hijack` | bounded-budget search over image patches |

Attacker access: **`black-box-query`** · transfer: GPU-gated, **not run in CI**.

## `optimized_instruction` — optimized, command-preserving instruction search (EAI01)

The first optimized *instruction* attack. Unlike the templated `instruction` family it **never names
the unsafe target object**: it searches manner/urgency cues and reframings that keep the operator's
command intact, gated by `is_command_preserving`. Primary channel EAI01; threat model EAI04
(targeted redirection).

| Attack | Idea |
| --- | --- |
| `targeted_redirect` | query-budgeted search over (reframing × appended cues) |

Attacker access: **`black-box-query`** · transfer: **stub-validated scaffolding** on CPU suites.

!!! success "This family has a measured defense"
    [Instruction canonicalization](studies/instruction-canonicalization.md) is measured against it
    — and the study leads with *why* that result is substantially circular on a fixture whose
    danger function is lexical. Read it before quoting the number.

## Baseline

`none` is the benign control — it never perturbs anything, so its ASR is the false-positive floor
every other rate is read against.
