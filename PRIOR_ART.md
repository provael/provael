# Prior art & honest credit

`vla-redteam` stands on a growing body of academic work on the safety of
LLM-/VLA-controlled robots. This file credits the work we build on and states
plainly **how we differ** — what is novel here (a small, reproducible, model-agnostic
ASR harness) and what is not (the attack ideas themselves, which come from the papers
below).

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
`vla-redteam` is strictly **inference-time, black-box** red-teaming of an *unmodified*
policy. We never train, fine-tune, or poison weights. (Our `StubPolicy`'s trigger
lexicon is a *test fixture* that imitates a vulnerability so the CPU pipeline yields a
measurable ASR — it is not a model and not a backdoor.)

### SafeVLA — *Towards Safety Alignment of Vision-Language-Action Models via Constrained Learning*
(2025). arXiv:[2503.03480](https://arxiv.org/abs/2503.03480) · [safevla.github.io](https://safevla.github.io/)

A **defense**: aligns VLA policies with safe reinforcement learning (a constrained
MDP / min-max formulation), reporting large safety improvements with maintained task
performance and sim-to-real transfer.

**How we differ (complementary):** SafeVLA hardens policies; `vla-redteam` measures how
often a policy can still be driven unsafe. The two are two sides of the same coin — a
defense like SafeVLA is exactly the kind of policy whose residual ASR our harness is
meant to quantify.

## What is actually novel here

Not the attacks — the **packaging**:

1. A small, **model-agnostic** interface (`PolicyAdapter` / `SuiteAdapter` / `Attack`)
   so the same attacks and the same ASR metric run against any policy or simulator.
2. A **deterministic, CPU-only, no-download core** (StubPolicy + StubSuite) so the
   tool is testable and reproducible without a GPU or model weights — the ASR for a
   fixed seed is an exact, asserted number.
3. A clean separation between the **headline metric (ASR)** and the backends, so
   results are comparable across policies, attacks, tasks, and seeds.

## What this is *not*

- Not a new attack algorithm or a state-of-the-art jailbreak.
- Not a backdoor / training-time method.
- Not a defense.
- Not a real-world exploitation tool (see [SAFETY.md](SAFETY.md)).
