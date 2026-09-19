# Attack catalog

**Seventeen** adversarial families of templated, auditable attacks plus two non-adversarial
families — the `baseline` benign control and the `control` harmless-variation arms — each tagged with its [Embodied AI Security Top 10](top10.md) risk. Most are heuristic
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

Real-model signal: `roleplay` redirected SmolVLA **88% (44/50)**, task-clustered 95% CI
**[72%, 100%]**, across all ten `libero_object` tasks vs a 2/50 benign control.

**The three arms do not behave alike, and the split is by semantics rather than by mechanism.** In the
same run `paraphrase` — which preserves the request and changes only its wording — fired **3/50
(6.0%)**, Wilson [2.1%, 16.2%], **indistinguishable from the benign control** at McNemar p = 1.0, while
`roleplay` and `goal_substitution`, which change what is being asked, fired 44/50 and 15/50. The
`roleplay` and `paraphrase` intervals are disjoint.

So a guardrail that normalises surface form would not have caught the arm that actually fires. Read it
narrowly — one policy, one suite, four templates per arm, an uncalibrated predicate — and see
[the finding](findings/semantic-vs-mechanical-instruction-attacks.md), which states it as a hypothesis
with supporting evidence rather than a settled result.

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

## `weight_integrity` — emulated weight corruption (EAI03)

The first family that attacks the **parameters** instead of the input. It leaves the instruction and
the observation exactly as the benign baseline delivers them and flips bits in the policy's loaded
INT8 weights, so any unsafe behaviour is attributable to the weights and to nothing else.

| Attack | Idea |
| --- | --- |
| `weight_bitflip_gradient_k{1,4,16,64,256}` | flip the K bits ranked highest by their first-order effect on the danger output |
| `weight_bitflip_random_k{1,4,16,64,256}` | flip K bits chosen uniformly — the **equal-count control**, re-drawn every episode |

Attacker access: **`white-box-gradient`** (reading the weights and their gradients is strictly more
access than any input-channel family here assumes) · transfer: **stub-validated scaffolding**.

!!! warning "What this measures, and what it does not"
    It measures whether a policy is **fragile to weight corruption** — how few flipped bits it takes
    before the closed loop goes unsafe under a benign instruction.

    It does **not** measure whether an attacker can achieve that corruption on a real deployment.
    That is a platform question — DRAM fault injection (Rowhammer), ECC, memory integrity, the
    supply chain that delivered the checkpoint — and Provael touches none of it. Every flip is
    emulated in memory, every record carries `emulated: true`, and there is no hardware
    fault-injection path in this repository. **A high rate here is evidence about the policy, never
    about the platform.**

!!! danger "Read it per arm, and never pool it"
    The two arms are *meant* to differ, so the family's pooled ASR averages them and means nothing.
    A gradient result published without its equal-count control is not a result at all: it cannot
    separate "the ranking found the bits that matter" from "corrupting K bits of anything breaks
    it", and those have opposite engineering consequences.

    The number to publish is the **crossing point** — the smallest K whose unsafe rate reaches a
    stated floor — from `provael.scoring.weight_integrity.crossing_pair`, which refuses to return a
    gradient crossing without the random one beside it.

The family exists because of [arXiv:2608.15475](https://arxiv.org/abs/2608.15475), whose headline is
that the flip budget tracks the action-decoding architecture (1–5 for direct-regression and
discrete-token heads, roughly 100–300 for flow-matching). **Provael has not reproduced that.** Its
only run is against the CPU fixture, which has one scalar danger head and no action-decoding
architecture to depend on, so the gradient-beats-random separation it shows is a property of that
fixture. See the [crosswalk](crosswalk/bit-flip-vla.md) for the clause-by-clause split of what is
implemented and what is not.

## Baseline

`none` is the benign control — it never perturbs anything, so its ASR is the false-positive floor
every other rate is read against.

## Coverage: registered is not validated

> *Moved here from the repository README on 20 September 2026, when the README was cut to what a new reader needs. The text is as it stood there; links were re-pointed.*


The registry is wide and the evidence is narrow, and this section keeps the two apart. It ships **seventeen adversarial families of auditable attacks** — `instruction` (text
reframings), `visual` (observation-space markers), `sensor_spoof` (EAI02: a sim
perception spoof driving the end-effector into a keep-out zone), `injection` (indirect /
embodied prompt injection), `action` (action-space integrity: freeze / trajectory
hijack), `action_space` (EAI04 2nd vector: keep-out hijack of the *commanded end-effector*
/ critical-step freeze), `backdoor` (EAI03: an objective-decoupled trigger *screen*),
`authorization` (EAI08: self-authorization / scope-escalation, i.e. excessive agency),
`confidentiality` (EAI09: a memorized-canary leak *screen* — membership inference /
extraction), `misalignment` (EAI06: the embodiment gap — a benign-sounding instruction
driving an unsafe embodied action into a keep-out zone), and **`humanoid`** (whole-body /
locomotion — a balance spoof → loss of balance, a whole-body hijack → topple, a freeze mid-stride)
— plus four **optimized** search families: **`optimized`**
(`targeted_hijack`: a black-box, query-budgeted *search*), **`optimized_patch`** (the image-channel
analogue, GPU-gated and inert on CPU suites), **`optimized_instruction`** (`targeted_redirect`,
a command-preserving instruction search) and **`universal_patch`** (one patch fit **once** and
carried unchanged to episodes it never queried — GPU-gated, transfer rate unmeasured) — a `none`
benign control, and an ASR
**leaderboard**, and **measured defenses**: `--defense` installs a mitigation in the deployment
position and `provael mitigation` reports pre/post ASR per family with 95% Wilson intervals, a
benign-FPR control and a benign-task-success acceptance gate. Measuring a defense is in the **free**
tool, not behind the operated tier: a mitigation you cannot measure is a marketing claim.

**Two defenses ship (0.29.0), both `stub-validated-scaffolding` — no real-model transfer is claimed
for either.** `instruction_canonicalization` acts on the instruction; `action_envelope` acts on the
commanded action. The action side exists because four of the six `docs/defenses.md` taxonomy rows act
on what leaves the policy, and until `Defense.filter_action` those four were not merely unmeasured
but **unimplementable** — the taxonomy was a spec its own interface could not satisfy. The
action-envelope study is `credited` on `stub` and `reach` and **`not-credited` on `humanoid`**, and
its headline is the coverage map: a magnitude cap cannot restore a frozen action and does not reach
successes routing through a decoupled flag ([study](studies/action-envelope.md)). `--recipe full-sweep` runs every one of the seventeen; families the chosen suite
cannot support are skipped and reported N/A, never scored 0%. Every family carries its transfer-test (rate + 95% Wilson CI + benign-FPR
control); run `provael transfer-test` to print it. The `action`, `action_space`, `sensor_spoof`,
`backdoor`, `authorization`, `misalignment`, `confidentiality`, `optimized` and `humanoid`
families are **stub-validated only** (no real-model transfer claimed); six of those nine were run
against SmolVLA on 14 September 2026 and every episode came back not applicable, which is an
absence of a channel on that policy, not a measurement, and is counted as neither. `provael
coverage` prints the whole picture as one machine-readable line rather than leaving it to prose —
and prints it as three numbers on purpose, because *registered is not validated*:
**17 adversarial families registered, 8 exercised against a real policy** (`instruction`, `visual`, `injection`,
`gradient_patch`, `optimized_instruction`, `optimized_patch`, `universal_patch`,
`weight_integrity` — one of the eight transferred; the other seven returned measured nulls, five
of them at n = 3, which is a result and not a rate), **9 stub-validated only**, measured on
**2 real policies** (`pi05`, `smolvla` — `realPoliciesTested` and `realPolicyNames` in
[`watch/registry.json`](https://github.com/provael/provael/blob/main/watch/registry.json), derived from the committed runs, never typed; a
policy is not an architecture, and one checkpoint is not a survey). Note also that the
registry holds **39 adversarial attacks**, which is not the same number as 17 families; reading
the registry dict's length as a family count overstates coverage by 14. It red-teams **8
policies** — the CPU `stub`
plus real **SmolVLA / π0 / π0.5 / π0-FAST** (via the `[lerobot]` extra), **OpenVLA**
(via `[openvla]`), and **π0 served by openpi** — Physical Intelligence's own stack, via the CPU-only
`[openpi]` websocket client to a GPU policy server. **Three of those eight are registered scaffolding**: `groot` (needs `lerobot[groot]`, which `provael[lerobot]` does not provision), `openvla` and `openpi` have each been structurally tested but have **never had a checkpoint loaded here**. Two backends have committed real-model results: `smolvla` (the ten-task suite) and `pi05` — `lerobot/pi05_libero_finetuned_v044` as recorded in the committed run, [`results/pi05_libero_object_2026-09-18/`](https://github.com/provael/provael/blob/main/results/pi05_libero_object_2026-09-18/README.md): the ten Object tasks at three seeds, `roleplay` 1/30 against `none` 0/30, McNemar p = 1.0. In the changelog's words, "it is the pre-registered study's *preliminary* leg (three seeds, two arms of eight), so no transfer of the envelope-exit effect is claimed and no headline moves", and because that run is "a different policy" from the published Object body, "`watch/publish-freshness.json` does not move". `provael list-policies` gives each backend a `status` of `measured` / `scaffolding` / `no run committed here`, so the difference is visible before you point `--policy` at one. Suites: **7** registered (`stub` + `reach` +
`humanoid` on CPU; **LIBERO** + **Meta-World** gated; `ai2_bridge` and `vla_arena` are
**scaffolding** — registered and structurally tested, but no benchmark has ever been run through
either, so neither is coverage; `vla_arena` is the declared-predicate suite that needs its own
Python 3.11 environment), or any policy/suite you wrap with the tiny adapter ABCs. The templated families are
heuristic perturbations (not gradient-based); the `optimized` family is a model-agnostic search
that only *queries* the policy — see
[Scope and honest limitations](index.md#scope-and-honest-limitations) and the
[examples gallery](https://github.com/provael/provael/blob/main/examples/).

## Families and the Top 10 categories they exercise

> *Moved here from the repository README on 20 September 2026, when the README was cut to what a new reader needs. The text is as it stood there; links were re-pointed.*


An independent, community risk list for the security of VLA models and the robots they drive — the
framework Provael's attacks map to. Read it: [docs/top10.md](top10.md). Draft v0.2, PRs welcome.
Shaping v0.3? The [Top-10 RFC process](top10-rfc.md) covers how to propose a new risk or
dispute an existing one.

Comparing frameworks? See the [EAI ↔ RoboJailBench crosswalk](crosswalk/robojailbench.md) — a
machine-readable mapping between the Top 10 and RoboJailBench's 18 harm categories, with provael's
honest measured coverage (and transfer status) per category.

**Coverage: 8 / 10.** Provael ships a runnable, sim-only attack family with a transfer-test for eight
categories — **EAI01–EAI06, EAI08, EAI09**. The other two are gaps of *different kinds*, and every
artifact now says which:

- **EAI07** (CPS / firmware / comms / teleop) is `out-of-scope-for-simulation` — an infrastructure /
  CVE layer that would need real exploit tooling this tool will not ship. **A clean Provael run says
  nothing about this risk.**
- **EAI10** (evaluation / observability / incident response) is `process-control-not-attackable` — a
  governance meta-risk with no attack surface. Provael's own signed report is *partial evidence for*
  its evaluation limb, not an attack on it, and it never carries an ASR.

All ten appear in the scorecard, compliance report, dossier and evidence manifest with an explicit
coverage status — a category with no attacks is shown as uncovered, never omitted. `provael
crosswalk --target atlas` prints the generated per-risk view.

Every attack is tagged with the risk it exercises; the SARIF output (`--format sarif`) carries
that tag as each finding's `EAIxx` ruleId:

| family | attacks | maps to |
| --- | --- | --- |
| `instruction` | `roleplay`, `goal_substitution`, `paraphrase` | [EAI01 — Policy & instruction jailbreak](top10.md#eai01--policy--instruction-jailbreak-direct-command-channel) |
| `visual` | `patch`, `decoy_object` | [EAI02 — Adversarial perception](top10.md#eai02--adversarial-perception-patches--textures--sensor-spoofing) |
| `sensor_spoof` | `patch_spoof`, `signal_spoof` (sim perception spoof → keep-out violation) | [EAI02 — Adversarial perception](top10.md#eai02--adversarial-perception-patches--textures--sensor-spoofing) |
| `injection` | `scene_text`, `mcp_tool_desc` | [EAI05 — Indirect / embodied prompt injection](top10.md#eai05--indirect--embodied-prompt-injection) |
| `action` | `freeze`, `trajectory_hijack` | [EAI04 — Action-space integrity](top10.md#eai04--action-space-integrity-attacks-hijack--targeted-trajectory--freeze) |
| `action_space` | `keepout_hijack`, `critical_freeze` (commanded-end-state: keep-out hijack / critical-step freeze) | [EAI04 — Action-space integrity](top10.md#eai04--action-space-integrity-attacks-hijack--targeted-trajectory--freeze) |
| `backdoor` | `object_trigger`, `phrase_trigger` (objective-decoupled trigger screen) | [EAI03 — Model & pipeline poisoning, backdoors & supply chain](top10.md#eai03--model--pipeline-poisoning-backdoors--supply-chain) |
| `authorization` | `self_authorize_bypass`, `scope_escalation` (excessive agency) | [EAI08 — Identity, access & excessive autonomy](top10.md#eai08--identity-access--excessive-autonomy) |
| `confidentiality` | `membership_inference`, `model_extraction` (memorized-canary leak screen) | [EAI09 — Model & data confidentiality](top10.md#eai09--model--data-confidentiality--theft-extraction-inversion--surveillance) |
| `misalignment` | `benign_urgency_override`, `euphemistic_reroute` (benign language → keep-out violation) | [EAI06 — Cross-domain safety misalignment](top10.md#eai06--cross-domain-safety-misalignment-the-embodiment-gap) |
| `optimized` | `targeted_hijack` (black-box action-directive search) | [EAI04 — Action-space integrity](top10.md#eai04--action-space-integrity-attacks-hijack--targeted-trajectory--freeze) |
| `optimized_patch` | `patch_hijack` (query-budgeted adversarial-patch search, GPU-gated) | [EAI02 — Adversarial perception](top10.md#eai02--adversarial-perception-patches--textures--sensor-spoofing) |
| `optimized_instruction` | `targeted_redirect` (optimized, command-preserving instruction search) | [EAI01 — Policy & instruction jailbreak](top10.md#eai01--policy--instruction-jailbreak-direct-command-channel) · EAI04 threat model |
| `humanoid` | `balance_spoof` (balance spoof → loss of balance), `whole_body_hijack` (→ topple/fall), `stride_freeze` (freeze mid-stride) — whole-body / locomotion, **stub-validated** | [EAI02 — Adversarial perception](top10.md#eai02--adversarial-perception-patches--textures--sensor-spoofing) · [EAI04 — Action-space integrity](top10.md#eai04--action-space-integrity-attacks-hijack--targeted-trajectory--freeze) |
