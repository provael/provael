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

### RoboGCG — *Adversarial Attacks on Robotic Vision Language Action Models*
Jones, Robey, Zou, Ravichandran, Pappas, Hassani, Fredrikson, Kolter (2025). arXiv:[2506.03350](https://arxiv.org/abs/2506.03350) · [code](https://github.com/eliotjones1/robogcg)

The successor to RoboPAIR from an overlapping group, and the closest published work to this
project's own threat model. It adapts LLM jailbreaking attacks "to obtain complete control
authority over VLAs", and reports that textual attacks "applied once at the beginning of a
rollout" achieve "full reachability of the action space of commonly used VLAs" and "often
persist over longer horizons". Its sharpest finding is a departure from the LLM jailbreaking
literature, in the authors' own words: "attacks in the real world do not have to be
semantically linked to notions of harm."

**How we differ:** they run a search to obtain control authority; our shipped `instruction`
family is a set of fixed, human-readable templates, and our one optimizing instruction family,
`optimized_instruction`, is a black-box, query-budgeted search over a command-preserving edit
space rather than an attack on the model's parameters. They demonstrate a capability; we
measure a rate, with a benign control and an interval.

**What we take from them:** the finding that a *single* rollout-initial text edit persists over
a horizon is the reason our instruction attacks are applied once and then scored across the
whole episode rather than re-applied per step. Their harm-decoupling observation is more
pointed still: it is the premise our `misalignment` family exists to test, and we had no
citation for it until now.

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
Puthumanaillam, Dongre, Thangeda, Nayyeri, Hakkani-Tür et al. (2026) — UIUC.
arXiv:[2606.12978](https://arxiv.org/abs/2606.12978)v2 · [project page](https://vla-redirection-attack.github.io/)

Formalizes **command-preserving trajectory redirection**: a prompt-only threat model in which the
attacker picks one prompt before the episode (all policy/environment components fixed), and the prompt
must stay close to the benign instruction *while omitting target words and correction language*. It
introduces an **on-policy prompt search** that uses rollouts to discover perturbations whose
closed-loop behaviour tracks an attacker target under those command-preserving constraints, shown in
simulation and on hardware.

**This is the closest work to ours in this file, and it beats us on nearly every axis.** Same threat
class, overlapping models (SmolVLA, π₀.₅), same suite (LIBERO). Verified from their Table 1:
**7 of 9 architectures exceed 90% ASR** — OpenVLA 91.8%, SmolVLA 94.7%, π₀.₅ 97.5%, GR00T-N1 96.8%;
the two below are Octo (88.6%) and VLA-0 (82.8%) — and averaging the edit column gives **≈3.4 character
edits per successful attack**.

The constraint is the contribution. An unconstrained prompt reading "go to the other bin" is not an
attack, it is an instruction. Theirs has to still look like the original task.

**Where provael is weaker, which is most of the comparison:**

- **Breadth** — nine architectures against our one measured policy; our other seven backends are
  stub-validated with no real-model transfer claimed.
- **Hardware** — they run SO-100 hardware. `results/hardware/` reads **0**.
- **Threat-model rigour** — our `roleplay` carries no near-benign constraint and no edit budget. Their
  3.4-character figure bounds how far the attacker had to move; we do not measure distance from the
  benign instruction at all, so we cannot make a claim of that shape.
- **Search** — they search on-policy with rollouts; our instruction family is a fixed hand-written bank.

What we carry that they do not is a matched benign control at the same `(task, seed)` with a reported
false-positive rate, so our number is a lift over a baseline rather than a bare success count. That is
an engineering property, not a scientific one, and it does not offset the above.

**mapping_status: `cited, not crosswalked`.**

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

### Mostly Harmless VLA Steering — *Learning What to Say to Your VLA*
Jeong, Swamy, Bajcsy (2026). arXiv:[2606.12299](https://arxiv.org/abs/2606.12299)

The benign twin of our `instruction` family, opening from the same premise almost verbatim:
"the mapping from language to behavior is often brittle and unintuitive: semantically similar
instructions can induce drastically different behaviors." They interactively search language
space to *improve* closed-loop task performance, distil the result into a test-time language
feedback policy, and conformalize an improvement head so steering is withheld where it would
hurt. On seen environments they report improving base VLA performance by 24.7% in simulation
and 65.0% in hardware — on arbitrary frozen pre-trained VLAs, with no access to the training
distribution and no fine-tuning.

**How we differ:** they search language space to improve behaviour; we search it to break it.
Same space, opposite objective. The symmetry is the point rather than a coincidence: both
projects exist because language-to-behaviour is unstable, and that instability is a capability
to them and an attack surface to us.

**What we take from them:** the strongest available statement that a VLA's sensitivity to
phrasing is a *property of the model* rather than an artefact of adversarial search. That is an
assumption our instruction family rests on and, until this paper, could not cite.

**An open question — addressed to the authors, not offered as a criticism.** Their guarantee
(Eq. 7) bounds a false-positive rate conditional on steering being harmful,
`P(ψ(X) ≥ q̂α | Y = 0) ≤ α`, under the standard conformal exchangeability assumption between
calibration and deployment examples. The calibration set is built from held-out perturbations
that "paraphrase the verb, noun, and a mix of both", generated by a language model — sampled,
not optimised against the policy under test. Our `optimized_instruction` family searches that
same space adversarially, under a query budget. An adversarially optimised perturbation is not
exchangeable with a randomly paraphrased one by construction, so what a conformalized
harmlessness guarantee covers under that shift is genuinely unclear. It may hold, it may
degrade gracefully, or the coverage statement may simply not apply outside its calibration
distribution. **We have not tested this and make no claim about the answer** — we raise it
because it is the question our harness is shaped to ask and theirs is shaped to answer.

### DRIFT — *Derailing Denoising Trajectories of Flow-Matching VLAs with Adversarial Patch Attack*
Tae, Lee (2026). arXiv:[2608.03207](https://arxiv.org/abs/2608.03207) · submitted 4 August 2026

The paper this project should be pointing at rather than competing with. Flow-matching VLAs such as
π0 had been reported to resist perturbations that fool autoregressive VLAs, and the authors state
plainly what that reputation was made of: **"We show that this robustness is largely illusory: it
stems from prior attacks ignoring the multi-step denoising ODE."** DRIFT is a test-time universal
adversarial patch, placed on the robot's gripper, that attacks the denoising *velocity field* of an
off-the-shelf policy. Its central result is the one that matters for a taxonomy: **"attacking only
the first denoising step is both stronger and cheaper than attacking a wider window of steps"** —
which the authors attribute to a gradient conflict specific to input-space optimization, and note is
"exactly opposite to the training-time backdoor regime". On π0 and π0.5 across four LIBERO suites
they report that DRIFT "breaks essentially all originally-solvable tasks with a small single patch,
far exceeding action- and embedding-space attack baselines".

**How we differ:** the threat model is adjacent to our `universal_patch` family — one frozen patch,
placed physically, carried to episodes it never queried — and the method is not comparable at all.
DRIFT is **white-box**: it optimises in input space against gradients of the velocity field. Ours is
an inference-time **black-box query** search over placements, with no gradients and no access to
model internals. A black-box search cannot find what DRIFT found, because the structure it exploits
(which step of the ODE to hit) is invisible without the derivative.

**The gap this exposes, stated rather than hedged:** **Provael has never measured a flow-matching
policy.** The `pi0`, `pi05` and `pi0fast` adapters are registered and `provael list-policies` marks
them scaffolding — they have never loaded a checkpoint. So DRIFT's finding is not a result we can
confirm, contradict or contextualise with a number of our own, and until we can, the honest position
is that this is a capability of theirs sitting on a class of policy we do not cover. The taxonomy
implication is separately argued in [docs/top10-rfc.md](docs/top10-rfc.md); it is a proposal, not a
change.

### SARF and AGSD — *Structure-Aware Robust Fine-Tuning: Defending Vision-Language-Action Robots Against Physical Attention Hijacking*
Zhang, Yin, Yang, Yan, Tian, Yu (2026). arXiv:[2608.03231](https://arxiv.org/abs/2608.03231) · submitted 4 August 2026

Both halves of the loop in one paper. The attack, **AGSD** (Attention-Guided Semantic Disruption),
is an Expectation-over-Transformation-optimised printable patch that "jointly (i) concentrates
action-to-vision attention on the patch and (ii) disrupts vision-language semantic alignment", which
the authors frame as triggering "policy-critical action-to-vision attention hijacking". The defense,
**SARF**, is "a zero-inference-overhead defense that fine-tunes only the visual encoder using
feature anchoring, policy-critical attention correction, and language-guided geometric consistency
restricted to semantically relevant regions". Their headline: **"On LIBERO, SARF reduces OpenVLA's
failure rate under AGSD from 100% to 14.2%-56.8% (28.6% average) across suites while preserving
clean performance, and on a real PiPER manipulator it improves average success under AGSD from 23.0%
to 65.0%."**

**How we differ, and where we are simply behind:** our two shipped defenses
(`instruction_canonicalization`, `action_envelope`) are measured on a deterministic CPU fixture and
are labelled stub-validated scaffolding, with no real-model transfer claimed for either. SARF is
measured on a real model *and on real hardware*. **That comparison should not be softened: they have
a physical-robot defense number and we have none, on any hardware, for any family.** The
`/sim-to-real` protocol is pre-registered and its trials have not been run. Reporting a
mitigation is in our free tool because a mitigation you cannot measure is a marketing claim; that
principle does not earn us a result we have not produced.

**What we take from them:** AGSD's mechanism claim — that the patch works by *diverting
action-conditioned attention*, not merely by corrupting pixels — is a sharper account of what a
patch family is actually attacking than we had a citation for. It also bears on the RFC: attention
hijacking and first-step denoising redirection are two different mechanisms behind the same visual
delivery channel, which is the argument for naming mechanisms rather than channels.

### FLARE and ChromaGuard — *Lights, Camera, Malfunction: When Illumination Robustness Leaves VLA Models Blind to Color*
Watanabe, Sato, Yoshioka (2026). arXiv:[2607.14698](https://arxiv.org/abs/2607.14698) · submitted 16 July 2026

A physical attack with no printed artifact at all. **FLARE** is "an optimized physical spotlight
attack framework that exploits these vulnerabilities via targeted illuminations, dropping baseline
task success rates to zero without any access to model internals" — so it is **black-box**, and its
delivery channel is light rather than a sticker. The more useful half of the paper is a defensive
trap: the authors "identify a critical and previously underestimated defensive pitfall: naive data
augmentations incorrectly condition VLA models to discard color as noise, collapsing their visual
perception into a purely shape-biased processor", exposed by a diagnostic grayscale evaluation in
which the defended model holds up on grayscale while "its success rate on benign, color-dependent
real-world tasks drops to at most 47.5%, well below the undefended baseline". Their **ChromaGuard**
chroma-preserving adversarial training reports "97.5% and 92.5% success rates in benign and attacked
color-dependent tasks" on a physical 6-DoF platform.

**How we differ:** we model no illumination channel. Every `visual`-family attack we ship perturbs
the observation tensor a policy receives, which is a printed-patch-shaped assumption; a spotlight is
a different physical primitive and we do not represent it. We also cannot run their diagnostic:
grayscale-vs-colour benign evaluation needs a real policy on real colour-dependent tasks, and our
benign control is a deterministic fixture.

**What we take from them, and it is uncomfortable:** their pitfall is a direct warning about the
shape of our own defense evidence. A defense that improves an attacked number while quietly
degrading benign capability is exactly what our `action_envelope` study calls a coverage question,
and their grayscale diagnostic is a cleaner instrument for catching it than the
benign-task-success acceptance gate we currently apply. We have not implemented an equivalent
diagnostic and do not claim one.

### World-Model Security Survey — *Security of World-Model-Based Embodied AI: A Lifecycle of Threats, Defenses, and Evaluation*
Liu, Chen, Tan, Meng, Chen, Zhu (2026). arXiv:[2607.28226](https://arxiv.org/abs/2607.28226) · submitted 30 July 2026

**A different indexing axis, and that is the whole value.** Every taxonomy in this file — including
our own Embodied AI Security Top 10 — indexes by **attack channel**: what the adversary touches, be
it the instruction, the pixels, the sensor stream, the action head. This survey indexes by **which
world-model property gets corrupted**. It takes the seven familiar families (poisoning, backdoors,
adversarial examples, sensor spoofing, prompt injection, trajectory manipulation, supply-chain) and
argues they "take on distinct meanings when they corrupt world states, learned dynamics, affordance
estimates, or safety costs".

Those two axes cross; they do not merge. A prompt injection and a sensor spoof are different
channels that can corrupt the same learned dynamics, and one channel can corrupt several properties.
Collapsing either axis into the other loses the thing that made it worth drawing.

**The claim with no counterpart in EAI01–EAI10.** Their duality: world models "can serve as runtime
safety shields, yet when compromised or over-trusted they generate predictive safety illusions". Our
Top 10 has no entry for *the safety mechanism itself becoming the attack surface by being believed*.
That is a real gap on our side, not a difference in scope, and it is the single most useful thing to
take from this paper.

**mapping_status: `not-crosswalked`.** Deliberately, and the reason is measurable rather than
editorial. Verified against the full 18-page PDF this run: **zero** occurrences of `github.com`,
`https://`, "code is available" or "we release" — there is no runnable harness to point at — and
**no reported denominator anywhere**: no `n = N`, no `x/y trials`, no benign control arm. There is
nothing yet that a number of ours could be compared against, so a crosswalk would be prose mapped
onto prose, which is the kind of table that reads as coverage without carrying any.

**Their proposed metric is sharper than "they have no ASR", though, and we should say so.** The
phrase "attack success rate" appears exactly once in the paper, and it appears in order to argue
past it: "The primary metric is not only attack success rate, but the rate of predicted-safe but
actually unsafe executions, together with monitor confidence and intervention recall." That is a
better-specified quantity than the one we report — it measures the safety monitor's failure, not
just the attack's success — and we do not measure it. It is outlined, not operationalized; if they
build that side out, it is the row we should map to first.

**How we differ:** we are a runnable harness with a denominator and no lifecycle theory; this is a
lifecycle theory with no denominator. That is a complementarity, not a competition, and it is the
argument for crossing the two axes once rather than five times.

### SafeVLA-Bench — *A Benchmark for the Success-Safety Gap in Vision-Language-Action Models*
Fan, Xu, Sokolsky, Lee, Kong (2026) — University of Notre Dame and University of Pennsylvania.
arXiv:[2606.00773](https://arxiv.org/abs/2606.00773) · submitted 30 May 2026 · [safevla.org](https://safevla.org)

**Not the SafeVLA entry above.** Two different works, two years apart, with near-identical names:
[SafeVLA](https://arxiv.org/abs/2503.03480) (2025) is a *defense* that aligns policies via
constrained learning; SafeVLA-**Bench** (2026) is an *evaluation framework* that scores existing
rollouts. Cited separately because conflating them would attribute a benchmark's metrics to an
alignment method.

**We already use their vocabulary, which is the reason this entry is overdue.**
`provael.scoring.asr.succ_but_unsafe` implements a Succ-But-Unsafe rate and names SafeVLA-Bench in
its own docstring; `RunReport.succ_but_unsafe` carries it into every report. Borrowing a metric name
without citing its source in prior art is exactly the omission this file exists to prevent.

**The relationship, precisely: different failures on the same policies.** They formalize "task-aware
safety requirements as Signal Temporal Logic (STL) specifications and report native success with two
unsafe-success metrics: Succ-But-Unsafe (SBU) ... and Violation Severity Index (VSI)". Both metrics
are **post-hoc and non-adversarial** — they score rollouts a policy produced *on its own*, under the
benchmark's ordinary instructions, and ask whether success concealed a violation. Provael's ASR is
**pre-hoc and adversarial** — it perturbs the input first and asks whether an attacker can *cause* a
violation.

So the questions do not overlap even where the machinery looks similar:

| | SafeVLA-Bench | `provael` |
| --- | --- | --- |
| When it acts | after the rollout (post-hoc scoring) | before it (input perturbation) |
| Who causes the failure | nobody — the policy's own behaviour | an adversary, by construction |
| Safety definition | STL specifications over the trajectory | a keep-out predicate, currently **uncalibrated** |
| Denominator | rollouts of the native benchmark task | matched (task, seed) pairs against a benign twin |

**Both instantiate on LIBERO**, which is what makes a future crosswalk tractable rather than
hypothetical: they evaluate nine policy-benchmark entries across LIBERO and RoboCasa-365, and our
one measured real-policy result is SmolVLA × `libero_object`. That is a shared substrate, not a
shared metric.

**Their finding is the one that should worry a reader of our numbers most**, and it is independent
of anything we measured: "high-SR tabletop baselines still leave 13 to 15 percent unsafe-episode
rates, and 36 to 56 percent of successful RoboCasa-365 rollouts violate at least one active safety
clause." A policy can be *unattacked* and still unsafe at those rates. Our ASR says nothing about
that floor — it measures lift over a benign control, so a policy that is already unsafe 15% of the
time without any adversary is invisible to us by construction.

**mapping_status: `aspirational`.** We have not implemented this crosswalk and are not claiming one.
Our `succ_but_unsafe` shares their *name* and their per-episode quadrant logic, but not their units:
theirs is an STL-violation judgement over a trajectory, ours is a boolean from an uncalibrated
keep-out predicate. Placing the two in one column would repeat the mistake the ForesightSafety-VLA
crosswalk exists to avoid — borrowing vocabulary is not borrowing units. Calibrating our predicate
is the prerequisite, and it is not done.

**How we differ (complementary):** they measure whether success hides a violation; we measure
whether an adversary can induce one. A policy that scores well on SBU can still have a high ASR, and
a policy with a low ASR can still be routinely unsafe on its own. Neither number substitutes for the
other, and a safety case that cites only one is answering half the question.

### Embodied AI Safety Survey — *Safety in Embodied AI: A Survey of Risks, Attacks, and Defenses*
Li, Zheng, Gao, Xia, Wang, Wang et al. arXiv:[2605.02900](https://arxiv.org/abs/2605.02900) ·
companion list [x-zheng16/Awesome-Embodied-AI-Safety](https://github.com/x-zheng16/Awesome-Embodied-AI-Safety)

**The most complete map of this field we know of, and it is maintained rather than published-once.**
The companion list organises the literature into five taxonomy layers with a daily LLM-screened
arXiv feed behind it, split into an explicitly-marked auto-screened tier and a human-reviewed
Editor's Audit before anything is promoted into the curated survey. That two-tier design is the
same distinction this project draws between `stub-validated` and measured, applied to a reading
list, and it is unusual enough to be worth naming.

**mapping_status: `cited, not crosswalked`.** We have not mapped the Embodied AI Security Top 10
category-by-category onto this survey's taxonomy, and until that exists we claim no coverage parity
with it. Saying so is cheaper than a table that implies the mapping was done.

**Their Open Challenges name the gap this tool was built for**, verified in the list README this
run: "Benchmark Standardization: Lack of unified safety benchmarks across the full embodied AI
pipeline hinders reproducible evaluation." A catalogue of several hundred papers containing, as far
as we can tell, no runnable harness is itself evidence for that sentence.

**Verified this run, because two details are easy to get wrong.** The licence on the companion list
is **CC BY-NC-SA 4.0** — NonCommercial, not the plain CC BY it is sometimes described as, which
matters to anyone planning to reuse it. And **Xiang Zheng, who maintains the list, is the second
author of the survey**; the first is Xiao Li. Cite it as Li, Zheng et al., not Zheng et al.

We did not verify a total paper count. Per-layer headings in the list README show Perception at 199
and Action and Interaction at 112 across five layers; our own crude count of markdown entries is
~570. Any single headline number for this list should be taken from the list, not from us.

### RoboJailBench — *Benchmarking Adversarial Attacks and Defenses in Embodied Robotic Agents*
Yeke, Zhou, Lin, Cai, Bianchi, Celik (2026) — Purdue PurSec.
arXiv:[2605.19328](https://arxiv.org/abs/2605.19328)v1 · [leaderboard](https://purseclab.github.io/benchmark-for-robotics-security/)

**Already crosswalked in depth — see [`docs/crosswalk/robojailbench.md`](https://github.com/provael/provael/blob/main/docs/crosswalk/robojailbench.md)**,
which quotes all 18 security-violation consequence categories verbatim from their Table 2 and maps them
against the Embodied AI Security Top 10. This entry does not repeat that. It records the one thing the
crosswalk does not say.

**Their motivating gap is the problem our benign control solves, and they reached it independently.**
They fault prior work for relying on "ad-hoc datasets, limited metrics" and for emphasising "attack
success while neglecting the trade-off between security and the ability to follow benign commands",
answering it with an intent-contrast dataset pipeline that pairs adversarial and benign goals. That is
**convergent, not derivative** — their pairing and our benign-FPR arm were designed separately and land
on the same conclusion: an attack-success rate without a benign twin is uninterpretable.

Verified: conceptual deception reaches **94–100% ASR** across RoboVQA, RH20T, NVIDIA PhysicalAI-AV and
RJB-Instructions in the no-defense setting.

**The honest difference in what is under test.** They evaluate **VLM planners** — models that read a
scene and emit a plan. Provael evaluates **closed-loop low-level policies** emitting motor commands
every step. A jailbroken planner has produced a bad sentence; a redirected policy has already moved.
Neither number transfers to the other, and a reader comparing the two ASRs is comparing different
quantities.

**Where provael is weaker:** they ship an evolving public repository with standardised metrics, four
integrated attacks, two defenses and an external leaderboard. Ours has **zero third-party
submissions**.

**mapping_status: `crosswalked`** — [robojailbench.md](https://github.com/provael/provael/blob/main/docs/crosswalk/robojailbench.md).

### Altered Thoughts, Altered Actions — *Probing Chain-of-Thought Vulnerabilities in VLA Manipulation*
Trinh, Akhtar, Azam (2026) — University of Melbourne.
arXiv:[2603.12717](https://arxiv.org/abs/2603.12717)v1

**They attack a channel provael cannot reach.** A reasoning VLA emits a natural-language plan before
decoding motor commands; they corrupt that intermediate trace with all inputs left intact. Provael
perturbs the instruction and never touches the reasoning trace, so our harness has no attack for this
vector at all.

Verified from the abstract: substituting **object names** in the reasoning trace costs **8.3 pp**
overall, reaching **−19.3 pp** on goal-conditioned tasks and **−45 pp** on individual tasks — while
sentence reordering, spatial-direction reversal, token noise, and a 70B-parameter LLM crafting
plausible-but-wrong plans all land **within ±4 pp**.

Their conclusion: "the action decoder depends on entity-reference integrity rather than reasoning
quality or sequential structure", and "a sophisticated LLM-based attacker underperforms simple
mechanical object-name substitution, because preserving plausibility inadvertently retains the
entity-grounding structure the decoder needs."

**Where provael is weaker:** 40 LIBERO tasks against our 10, a cross-architecture control against a
non-reasoning VLA, and seven corruptions across three attacker tiers. We have one instruction family
and no reasoning-trace attack. Their result also implies an entire attack surface — the internal text
channel — that our threat model does not enumerate.

Their result has the same shape as
[our semantic-versus-mechanical finding](https://github.com/provael/provael/blob/main/docs/findings/semantic-vs-mechanical-instruction-attacks.md)
seen from the other side: what matters is *which entity is referred to*, not how the sentence is built.
Ours is the adversarial framing of the same contrast — a fixed safety envelope with a benign control,
so the quantity is an envelope-exit rate rather than a task-success delta.

**mapping_status: `cited, not crosswalked`.**

### Q-DIG — *Red-Teaming Vision-Language-Action Models via Quality Diversity Prompt Generation*
Srikanth, Liang, Hsu, Bhatt, Zhao … Nikolaidis (2026) — USC ICAROS.
arXiv:[2603.12510](https://arxiv.org/abs/2603.12510)v3 · [qdigvla.github.io](https://qdigvla.github.io)

**They generate the adversarial instructions; we hand-write ours.** Q-DIG applies quality-diversity
optimisation with a VLM in the loop to find diverse, natural, task-relevant instructions that induce
failures. Verified from their tables: the base VLA succeeds on **37.0%** of unseen adversarial
instructions against **97.4%** on the original phrasing (OpenVLA-OFT in SimplerEnv); fine-tuning on
generated instructions lifts that to 52.2–60.5%.

**This is the sharpest methodological criticism of provael in this file.** Our instruction attacks are
a fixed bank — `benign_reword` holds **four** templates, chosen by a maintainer. A fixed bank measures
the templates it contains and generalises no further. Q-DIG searches the space and reports coverage of
it, and a user study judged its prompts more natural than baselines. When our reword arm returns
near-zero, Q-DIG is the reason that must be read as *"these four rewrites do not fire"* rather than
*"rewording is safe"*.

**Where provael is weaker:** search versus enumeration; a prompt-naturalness user study we have not
run; multiple simulation benchmarks against our one; and real-world evaluation consistent with sim.
They also close the loop — fine-tuning on found prompts improves robustness — where provael measures
and never mitigates.

**mapping_status: `cited, not crosswalked`.**

### VLA Safety Survey — *Vision-Language-Action Safety: Threats, Challenges, Evaluations, and Mechanisms*
Li, Yin, Huang, Liu, Zou, Yu, Ye et al. (2026) — NUS.
arXiv:[2604.23775](https://arxiv.org/abs/2604.23775)v1 · living index:
[github.com/LiQiiiii/Awesome-VLA-Safety](https://github.com/LiQiiiii/Awesome-VLA-Safety)

Organised along two timing axes — attack timing and defense timing, training-time versus inference-time
— which is a cleaner cut than our channel-based Top 10 for one specific purpose: it encodes *at which
stage a threat can be mitigated*, which our taxonomy does not record at all.

**Their fifth open problem is standardised evaluation**, listed with certified robustness for embodied
trajectories, physically realizable defenses, safety-aware training, and unified runtime safety
architectures. That is the problem provael exists to address, which makes this the clearest external
statement of why the tool should exist — and equally the clearest measure of how far one maintainer-run
result falls short of it.

**Where provael is weaker:** it is a survey, so comparing measurement counts is meaningless. The real
gap is elsewhere — they maintain a **living index of the field and provael is not in it**. A tool
arguing for standardised evaluation that is absent from the field's own index has an adoption problem,
not a taxonomy problem.

**mapping_status: `cited, not crosswalked`.**

### !Imperio, smolVLA — *The Implications of Data Poisoning on Open Source Robotics*
Bühler, Schutera (2026) — DHBW.
arXiv:[2607.04146](https://arxiv.org/abs/2607.04146)v1

**Orthogonal rather than competing, and on our exact stack.** A training-time attack: poison a handful
of demonstration episodes with a trigger word and the model carries a backdoor. Provael is an
inference-time harness with no training-time attack, so nothing here overlaps our measurements.

Verified from the abstract: **three poisoned episodes in 320 clean episodes** suffice for complete
denial of service — success drops to **0.0 ± 0.0%** across all trigger-word conditions while the robot
locks into a fixed joint configuration — and **clean-prompt behaviour holds at ≈50%**, so the attack is
stealthy under normal operation. A **single** poisoned episode already drops success to 6.7 ± 6.7%.

Same policy as our one measured result (SmolVLA) and the same ecosystem (LeRobot), which makes it
directly relevant rather than adjacent. **An integrator running provael against a poisoned checkpoint
would see a clean benign control and an unremarkable ASR**, because the backdoor only fires on the
trigger. Our harness cannot detect this class: `provael verify-checkpoint` addresses supply-chain
integrity of the *artifact*, not semantic integrity of its *training data*.

**Where provael is weaker:** they run real hardware — an SO-101 arm from the
[SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) project — and we run none. That is the same
platform our own SO-101 sim-to-real study is **pre-registered against and has not executed**, so they
hold working hardware evidence on the platform we have only planned for.

**mapping_status: `cited, not crosswalked`.** No crosswalk is possible: a training-time backdoor rate
and an inference-time ASR share no denominator.

### DURA — *Hidden in Plain Sight: Diffusion-Based Unrestricted Robotic Attacks on VLA Models*
Han, Yao, Wang, Cao, Zhang, Shan, Deng, Wang, Hu (2026).
arXiv:[2608.10393](https://arxiv.org/abs/2608.10393) · submitted 11 August 2026

**The strongest published attack on the channel where provael measures a null**, and the entry that
should change how that null is read.

DURA generates visually natural adversarial patches by optimising along the latent trajectory of a
pretrained diffusion model, in both white-box and black-box settings — the black-box variant needing
only the victim's *predicted actions*. Verified from their Table 1 (OpenVLA-7B, four LIBERO suites),
reading DURA's own `Ours` rows rather than a neighbouring baseline's:

| setting | simulated patch | physical patch |
| --- | ---: | ---: |
| White-box, target-only | **100.0%** on all four suites | **100.0%** on all four suites |
| Black-box, target-only | **86.0%** avg | **79.3%** avg |
| Benign (no patch) | 23.5% | 23.5% |
| Clean patch (non-adversarial) | 39.5% | 39.5% |

The white-box 100% sits in the **target-only** group — no ground-truth action tokens — which is the
harder supervision setting, not the easier one. A label-supervised baseline (UADA) also reads 100.0
across that table; attributing it to DURA would be the obvious misreading and is worth naming.

Their patch-area ablation: ASR "rises sharply to 77% at only 2% area", reaches "99%" at 5%, and
saturates at 100% beyond. Demonstrated on a real Franka arm, with a **printed patch inserted into the
camera view** — inserting it drives the arm to the target action, removing it lets the arm resume.

**How we differ, and where we are weaker — this is the useful part of the entry.**

Provael's `visual` family is **two attacks**, and neither is an image. `patch` appends the literal
string `adv_patch::{object}::now` to a list called `visual_tokens` in a simulated observation dict;
`decoy_object` appends `salient-decoy-first` alongside a planted object name. They are **symbolic
stand-ins for a perception attack**, evaluated in a simulator that never renders an adversarial
pixel. DURA optimises actual pixels, prints them, and holds them in front of a real camera.

That gap changes what our own null means. The ten-task suite measured the visual family at
**0/100**, and it is tempting to read that as "perception attacks did not transfer to SmolVLA". It
does not support that reading. It supports a narrower one: *our symbolic markers did not fire*. DURA
is the standing evidence that a real optimised patch on the same class of policy reaches 100% —
so the honest gloss on our 0/100 is a **coverage gap in our harness**, not a robustness finding
about the policy.

We also have **zero physical results of any kind**: `results/hardware/` reads 0 and the SO-101
protocol is pre-registered and unrun. DURA's physical column is not a number we can currently
produce at any n.

What we carry that they do not is a matched benign control at the same `(task, seed)` and a reported
false-positive rate. Their table does carry benign and clean-patch baselines (23.5% and 39.5%), which
is the same instinct and more than most of this file's entries manage.

**mapping_status: `cited, not crosswalked`.**

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
- **Not the first anything.** Provael has never claimed to be first, and this file is the reason —
  every entry above is prior work that got there earlier. The claim is stated here explicitly
  because a third party is publishing the opposite: an automated trend-scraper
  (`THTHDGCS/agents-radar`) has 29 bot-generated issues describing Provael as *"a first-of-its-kind
  open-source red-teaming framework for VLA robot policies"*. Those issues are public and indexable,
  nobody here wrote them, and an LLM summary is not a citation.

  If you found that phrasing and came here to check it: it is wrong, we disown it, and the honest
  version is in [What is actually novel here](#what-is-actually-novel-here) — which is narrower than
  "first" and got narrower again after AttackVLA (arXiv:2511.12149) shipped a unified VLA attack
  framework with a comparable ASR.
