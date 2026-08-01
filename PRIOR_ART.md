# Prior art & honest credit

`provael` stands on a growing body of academic work on the safety of
LLM-/VLA-controlled robots. This file credits the work we build on and states
plainly **how we differ** — what is novel here (a small, reproducible, model-agnostic
ASR harness) and what is not (the attack ideas themselves, which come from the papers
below).

> **Looking for the numbers?** This file credits the work qualitatively. For the published
> figures side by side — and, more importantly, for **which of them a Provael ASR can honestly be
> compared against** — see
> [docs/standards/published-asr-baselines.md](docs/standards/published-asr-baselines.md). Most
> published VLA attack results measure *task-success degradation*; a Provael ASR measures
> *envelope breach*. They are not one column.

## The works we build on

### RoboPAIR — *Jailbreaking LLM-Controlled Robots*
Robey, Ravichandran, Kumar, Hassani, Pappas (2024). arXiv:[2410.13691](https://arxiv.org/abs/2410.13691) · [robopair.org](https://robopair.org/)

The first algorithm to jailbreak LLM-controlled robots, eliciting *harmful physical
actions* (not just harmful text) by adapting the PAIR attacker-LLM loop and
fictional/role-play framings to the robotics setting.

**How we differ:** our `RolePlayAttack` is a single, fixed, human-readable template
inspired by RoboPAIR's fictional-framing idea — not RoboPAIR's optimizer. We ship a
reproducible measurement harness, not an attacker-LLM search loop. An optimizer-based
family is explicitly future work (see CHANGELOG v0.2).

### POEX — *Towards Policy Executable Jailbreak Attacks Against LLM-based Robots*
(2024). arXiv:[2412.16633](https://arxiv.org/abs/2412.16633)

Shows that a *harmful text output ≠ a harmful executable policy*: it injects harmful
instructions plus optimized suffixes into the planning module so the resulting policy
is actually executable, evaluated on Harmful-RLbench (136 harmful instructions) on a
real arm and in simulation. Proposes safety-constrained prompts and pre-/post-planning
checks as defenses.

**How we differ:** we adopt POEX's central insight — *score success by whether the
policy reaches an unsafe state, not by what the model says* — as the core of our ASR
metric (`SuiteAdapter.is_unsafe`). Our `GoalSubstitutionAttack` is a templated
goal-hijack; POEX's optimized executable suffixes are a planned family, not shipped in
Part 1.

### BadVLA — *Backdoor Attacks on Vision-Language-Action Models via Objective-Decoupled Optimization*
Zhou, Tie, et al. (2025). arXiv:[2505.16640](https://arxiv.org/abs/2505.16640) · NeurIPS 2025 poster · [project page](https://badvla-project.github.io/)

The first systematic study of *backdoor* vulnerabilities in VLA models: a
training-/fine-tuning-time trigger that causes conditional control deviations with
near-100% attack success and little clean-task degradation.

**How we differ:** BadVLA is a **training-time** threat (it modifies the model);
`provael` is strictly **inference-time, black-box** red-teaming of an *unmodified*
policy. We never train, fine-tune, or poison weights. (Our `StubPolicy`'s trigger
lexicon is a *test fixture* that imitates a vulnerability so the CPU pipeline yields a
measurable ASR — it is not a model and not a backdoor.)

### FreezeVLA — *Action-Freezing Attacks against Vision-Language-Action Models*
Wong, et al. (2025). arXiv:[2509.19870](https://arxiv.org/abs/2509.19870) · [code](https://github.com/xinwong/FreezeVLA) (MIT)

An **optimised, white-box** visual attack: a min-max bi-level optimisation crafts an adversarial
image that makes the VLA *freeze* (emit null/stalled actions), an availability failure, at a reported
~76% average success rate.

**How we differ:** our `optimized_patch` family (`patch_hijack`) is the **inference-time, black-box
query** analogue — it searches over patch placements on the real camera frame, scoring each by the
policy's *emitted motion* via an oracle, and records `attacker_access="black-box-query"` (never
claiming the white-box-gradient access it does not use). We **reimplement the idea, porting no code**;
FreezeVLA's MIT license would permit a port with attribution, but a from-scratch predicate keeps the
core dependency-free. A true white-box-gradient variant and an availability/freeze success predicate
are noted as GPU/P1 follow-ups (see ROADMAP P0.3b). Like our other families, the transfer number is
GPU-gated and unclaimed until the `PROVAEL_INTEGRATION=1` path is run.

### Trajectory-Level Redirection — *Trajectory-Level Redirection Attacks on Vision-Language-Action Models*
(2026). arXiv:[2606.12978](https://arxiv.org/abs/2606.12978) · [project page](https://vla-redirection-attack.github.io/)

Formalizes **command-preserving trajectory redirection**: a prompt-only threat model in which the
attacker picks one prompt before the episode (all policy/environment components fixed), and the prompt
must stay close to the benign instruction *while omitting target words and correction language*. It
introduces an **on-policy prompt search** that uses rollouts to discover perturbations whose
closed-loop behaviour tracks an attacker target under those command-preserving constraints, shown in
simulation and on hardware.

### SABER — *A Stealthy Agentic Black-Box Attack Framework for Vision-Language-Action Models*
Wu, Shi, Wang, Li, Bedi, Manocha (2026). arXiv:[2603.24935](https://arxiv.org/abs/2603.24935) · [code](https://github.com/wuxiyang1996/SABER)

A black-box, agent-driven attacker that generates small, plausible **instruction edits** — character-,
token-, and prompt-level — under a **bounded edit budget** to induce targeted behavioural degradation,
probing the robustness of the *instruction channel* across VLA models.

**How we differ:** our `optimized_instruction` family (`targeted_redirect`) is a compact,
**reproducible reimplementation of the idea** — an on-policy, bounded-budget **greedy** instruction
search with a command-preserving gate (benign-similarity floor + omit target words), scored by the
policy's emitted redirection via an oracle and recording `attacker_access="black-box-query"`. We
**port no code**: the greedy loop and the gate are from-scratch and dependency-free (SABER's
GRPO/ReAct attacker and the paper's full search are not reimplemented). Consistent with our other
families, the **real** SmolVLA×LIBERO redirection number is GPU-gated (`PROVAEL_INTEGRATION=1`) and
unclaimed until run; on the CPU stub it is scored by the danger-threshold predicate with an honest
sub-100% ceiling, plus a held-out transfer-test. We surface the papers' recommended defense —
**instruction canonicalization / repair** — as the mitigation. No "first" claim.

### AttackVLA — *Benchmarking Adversarial and Backdoor Attacks on Vision-Language-Action Models*
(2025). arXiv:[2511.12149](https://arxiv.org/abs/2511.12149)

**The closest work to this repository, and the one that most constrains what we may claim.** A
**unified evaluation framework** for adversarial and backdoor attacks on VLAs: it implements
existing VLA attacks plus attacks adapted from vision-language models, evaluates them in **both
simulation and real-world robotic settings**, and reports attack success rates (58.4% average for
targeted attacks, reaching 100% on some tasks). It also introduces *BackdoorVLA*, a targeted
backdoor forcing an attacker-specified multi-step action sequence. Its stated gap: "current methods
tend to induce untargeted failures or static action states, leaving targeted attacks that drive VLAs
to perform precise long-horizon action sequences largely unexplored."

**How we differ — and where we do not.** Being honest here matters more than sounding novel:
AttackVLA **already occupies** the "one harness, many attacks, comparable ASR" position, and it
does so with **real-robot evaluation we do not have**. We do not claim to have originated a unified
VLA attack harness, and we do not claim parity with a benchmark that has been run on hardware. What
remains genuinely different is narrower and worth stating exactly: a **deterministic CPU-only,
no-download core** so every number is reproducible without a GPU or model weights, and an
**evidence/compliance layer** (SARIF, OSCAL, CycloneDX ML-BOM, signed attestation, a Wilson-CI
regression gate wired into CI) — engineering a research benchmark has no reason to build. See
"What is actually novel here" below, which was rewritten after reading this paper.

### UPA-RFAS — *When Robots Obey the Patch: Universal Transferable Patch Attacks on VLA Models*
(2025). arXiv:[2511.21192](https://arxiv.org/abs/2511.21192) · CVPR 2026

Learns a **single universal physical patch** in a shared feature space and reports transfer across
unknown architectures, finetuned variants, tasks, viewpoints and **sim-to-real shifts**. The method
is white-box and feature-space: an ℓ1 deviation prior plus a repulsive InfoNCE loss, a two-phase
min-max robustness loop (inner: sample-wise invisible perturbations; outer: the universal patch
against that hardened neighbourhood), and two VLA-specific losses — *Patch Attention Dominance*
(hijack text→vision attention) and *Patch Semantic Misalignment* (label-free image-text mismatch).

**How we differ:** our `universal_patch` family reimplements the **threat model, not the method**,
and ports no code. What is shared is the question — does *one frozen patch* keep working on episodes
and tasks it never queried, which is the constraint a printed sticker actually faces and which our
per-episode `optimized_patch` family deliberately does not model. What is **not** shared is how the
patch is found: ours is an inference-time **black-box query** search over placements (the access
class it records), with no gradients, no feature-space access, no InfoNCE and no attention
objective. It will therefore find a **weaker** patch than UPA-RFAS reports, and our numbers must
never be read as reproducing theirs. Consistent with our other image-channel families the real
transfer rate is GPU-gated (`PROVAEL_INTEGRATION=1`) and **unclaimed** until run. Critically, the
paper's sim-to-real component is **theirs, not ours** — we have no hardware result of any kind.

### ADVLA — *Attention-Guided Patch-Wise Sparse Adversarial Attacks on VLA Models*
(2025). arXiv:[2511.21663](https://arxiv.org/abs/2511.21663)

Applies perturbations directly to features projected from the visual encoder into the *textual*
feature space, using attention guidance to keep them focused and sparse. Reports that under an
L∞ = 4/255 constraint, ADVLA with Top-K masking modifies **under 10% of patches** while reaching
near-100% attack success — without the costly end-to-end training or conspicuous patches earlier
methods needed.

**How we differ:** ADVLA is a **white-box** attack requiring encoder-internal feature access. Every
image-channel family we ship is **black-box query** only, so we cannot and do not reproduce its
imperceptibility or its success rate. It is recorded here because it sets the bar for what a
gradient-based variant would need to reach, and because a reader comparing our sub-100% patch
numbers to the literature deserves to know a far stronger white-box attack exists.

### SafeVLA — *Towards Safety Alignment of Vision-Language-Action Models via Constrained Learning*
(2025). arXiv:[2503.03480](https://arxiv.org/abs/2503.03480) · [safevla.github.io](https://safevla.github.io/)

A **defense**: aligns VLA policies with safe reinforcement learning (a constrained
MDP / min-max formulation), reporting large safety improvements with maintained task
performance and sim-to-real transfer.

**How we differ (complementary):** SafeVLA hardens policies; `provael` measures how
often a policy can still be driven unsafe. The two are two sides of the same coin — a
defense like SafeVLA is exactly the kind of policy whose residual ASR our harness is
meant to quantify.

## What is actually novel here

Not the attacks. **And — since AttackVLA (arXiv:2511.12149) — not simply "a unified harness with a
comparable ASR" either.** That claim stood in earlier versions of this file and it no longer
survives contact with the literature: AttackVLA is a unified VLA attack framework with a comparable
ASR *and* real-robot evaluation. Restating it would have been the easy thing and the false thing.

What is left is narrower, and it is the part a research benchmark has no incentive to build:

1. A **deterministic, CPU-only, no-download core** (StubPolicy + StubSuite). The ASR for a fixed
   seed is an exact, asserted number, reproducible in seconds with no GPU, no weights and no
   network. This is what makes a result *auditable by a third party* rather than merely published.
2. An **evidence and compliance layer**: SARIF for code scanning, OSCAL, a CycloneDX ML-BOM, signed
   attestation over a canonical serialisation, and a **Wilson-CI regression gate** wired into CI
   that fails a checkpoint on a statistically-disjoint regression rather than a hand-picked
   threshold. The output is designed to be *evidence*, not a table in a paper.
3. **A refusal to report a number we did not measure.** Inapplicable episodes are reported `N/A`
   and excluded from the denominator, never scored 0%; every rate ships with its 95% Wilson CI and
   a benign-FPR control arm; families that have not been shown to transfer to a real policy are
   labelled stub-validated scaffolding in the README. This is enforced by tests, not by intent.

3 is not a marketing line. It is the reason 1 and 2 are worth anything, and it is the only one of
the three that a better-funded competitor cannot simply out-build.

**What we explicitly do NOT claim:** originating the unified-VLA-harness idea (AttackVLA), any
sim-to-real transfer result (we have never run on hardware — see the README's first limitation),
parity with white-box attacks (UPA-RFAS, ADVLA), or any certification, conformity or functional-safety
status.

## What this is *not*

- Not a new attack algorithm or a state-of-the-art jailbreak.
- Not a backdoor / training-time method.
- Not a defense.
- Not a real-world exploitation tool (see [SAFETY.md](SAFETY.md)).
