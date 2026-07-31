# Safety & responsible use

`provael` (Provael) exists to **harden** open Vision-Language-Action robot
policies, by measuring how often instruction-level manipulation can drive a policy
into an unsafe state in **simulation**. It is a defensive / evaluation tool, built in
the spirit of responsible disclosure.

## Sim-only by default

- The tool operates on **simulated** policies and environments. The default,
  fully-supported path is the CPU `stub` policy + `stub` suite, which involve **no
  model, no robot, and no network**.
- Running against a real VLA policy (e.g. SmolVLA via LeRobot) still happens **inside
  a simulator** (e.g. LIBERO). `provael` does **not** drive physical robots and
  ships no robot-control or actuator code.

## No real-world-harm payloads

- The registry ships **15 adversarial families** (plus the benign `baseline` control). Eleven of
  them — `instruction`, `visual`, `injection`, `action`, `action_space`, `backdoor`,
  `sensor_spoof`, `misalignment`, `authorization`, `confidentiality`, `humanoid` — are short,
  generic, **templated** reframings, cues and markers: a fixed transform of the observation,
  non-transferable by construction. They probe whether a policy follows a redirected goal in a
  benchmark — they are **not** a recipe for causing harm.
- The remaining four — `optimized`, `optimized_patch`, `optimized_instruction`,
  `universal_patch` — are **not** templated. They are black-box, **query-budgeted searches** that
  adapt to the policy's own responses. Each is bounded by an explicit query budget, is
  deterministic under a seed, and searches only toward a harmless, sim-only goal direction; none
  uses gradients or model internals. `universal_patch` differs from the other three in *when* it
  pays that budget — once for the whole run rather than per episode — not in what it may search
  for. They are covered individually below.
- The `StubPolicy`'s "trigger lexicon" is an intentionally transparent **test fixture**
  (a handful of words with weights, read from the instruction and a fixed set of
  observation channels) so the CPU pipeline produces a measurable Attack Success Rate
  with no model. It is not a real exploit and does not transfer to real policies.
- The `visual` and `injection` families target the **stub's observation channels**. They
  demonstrate the *measurement* of perception/injection attacks; they do **not** ship
  pixel-level perturbations that transfer to a real model. What remains deliberately **deferred**
  is the *white-box* line — gradient-based adversarial suffixes (GCG) and white-box patch-gradient
  attacks; the black-box query searches described above do ship, and when the white-box variants
  are added they will stay sim-only and benchmark-scoped. No family claims cross-model transfer.
- The `backdoor` family (EAI03) is a **pre-deployment trigger *screen***, not an implant. It injects
  harmless, sim-only candidate triggers and measures whether a policy activates a hidden objective on
  a **known-planted stub fixture**. Provael **does not train, fine-tune, or implant a real backdoor**,
  and ships **no real-world payload**; on a clean checkpoint the screen reads ~0%. Real-model transfer
  is GPU-gated and not run in the CPU core, so no cross-model claim is made.
- The `sensor_spoof` family (EAI02) perturbs the **simulator's observation tensor** (a sim camera
  patch / sim LiDAR signal perturbation), **never real sensor hardware**, to measure whether spoofed
  perception drives the policy's *commanded* end-effector into a keep-out zone **in simulation**. It
  ships no real-sensor code and no real-world payload; the real-model (adversarial-patch) transfer is
  GPU-gated and not run in the CPU core.
- The `misalignment` family (EAI06) perturbs only the **instruction/observation the policy receives**,
  **never real-robot control**, to measure the **embodiment gap**: an instruction a chat-layer safety
  filter would pass as benign ("tidy up quickly") still drives the policy's *commanded* end-effector
  into a keep-out zone **in simulation**. The reframed instructions are benign-sounding and carry no
  real-world payload; it does not defeat, disable, or evade any safety filter — it demonstrates that a
  language-only filter is insufficient. Real-model transfer is GPU-gated and not run in the CPU core.
- The `action_space` family (EAI04, 2nd vector) perturbs only the **observation the policy receives**,
  **never real-robot control**, to measure **commanded-end-state integrity** on a disjoint sim channel:
  `keepout_hijack` drives the policy's *commanded* end-effector into a keep-out zone, and
  `critical_freeze` paralyses it at a safety-critical step — both scored **in simulation** on the
  fixture's commanded action. The visible instruction stays benign and it ships no real-world payload;
  it is not detection-evasion. Real-model transfer (AttackVLA / FreezeVLA) is GPU-gated and not run in
  the CPU core, so no cross-model claim is made.
- The `confidentiality` family (EAI09) is a **pre-deployment leak *screen***, not an exfiltration. It
  injects harmless, sim-only candidate **canary** probes (`member::` / `extract::`) and measures
  whether a **known-planted stub fixture** leaks the memorized canary — modelling membership inference
  / model extraction. Provael **exfiltrates no real data and steals no real model**; the canaries are
  opaque markers and the leak is scored on a deterministic fixture, so a clean checkpoint screens ~0%.
  The real-model transfer (a membership-inference / extraction advantage measured by *querying* a real
  policy, never exfiltrating real data) is GPU-gated and not run in the CPU core — no cross-model claim.
- The `optimized_instruction` family (EAI01; `targeted_redirect`) perturbs only the **instruction the
  policy receives**, **never real-robot control**. It is an optimized, **command-preserving** search:
  it keeps the operator's command and **never names the unsafe target object**, redirecting only
  through subtle, benign manner/urgency cues, and is scored **in simulation** (on the CPU stub, by the
  danger-threshold predicate). Command-preservation is a *realism constraint on the threat model*, **not
  detection-evasion**: the attack makes no attempt to defeat, disable, or hide from any safety filter —
  on the contrary, its recommended **defense (instruction canonicalization / repair)** is documented in
  `PRIOR_ART.md` and `docs/TOP10.md`. It ships no real-world payload; the EAI04 targeted-redirection
  outcome on a real policy is GPU-gated (`PROVAEL_INTEGRATION=1`) and not run in the CPU core, so no
  cross-model claim is made.
- The `action` family (EAI04) perturbs only the **observation the policy receives**, **never
  real-robot control**: `freeze` drives the commanded motion to a no-op and `trajectory_hijack`
  biases it toward an attacker-chosen — but harmless, sim-only — waypoint, both scored **in
  simulation** on the fixture's commanded action. It ships no real-world payload. Real-model
  transfer (FreezeVLA / AttackVLA) needs an adversarial-image search that is GPU-gated and not run
  in the CPU core, so no cross-model claim is made.
- The `authorization` family (EAI08) probes **excessive agency**: whether a perturbed instruction
  makes the policy self-authorize an authorization-gated action **without** presenting a valid
  operator token. It requests a *guarded, sim-only* action on a known-planted stub fixture; it
  forges no credential, and defeats no real access-control system — the "token" is a fixture cue.
  The benign `none` baseline never invokes a guarded action, so it is the 0% false-positive
  control. Real-model transfer is GPU-gated and not run in the CPU core.
- The `humanoid` family perturbs only the **simulated proprioceptive / action channel** of a
  humanoid whole-body *fixture*, **never real-robot control**, to measure whether a policy can be
  driven to lose balance, topple or freeze mid-stride **in simulation**. It applies only on the
  humanoid suite and reports not-applicable elsewhere (excluded from the ASR denominator, never
  faked). Provael drives no physical humanoid and ships no balance-controller or actuator code;
  real-model transfer is GPU-gated, not run here, and pre-registered in
  `docs/studies/humanoid-locomotion-transfer.md`.
- The `optimized` (EAI04, `targeted_hijack`) and `optimized_patch` (`patch_hijack`) families are the
  **search-based** pair. Both are **black-box** — they only *query* the policy's action, never its
  gradients or internals — **query-budgeted** (`--query-budget`, with the policy reset around each
  query so the search cannot pollute the live rollout), and **deterministic** under the run seed.
  Both steer toward the same harmless, sim-only goal direction and ship no real-world payload.
  `optimized_patch` writes to the real camera-image channel, but returns not-applicable when the
  observation carries no real image — so on the CPU stub it is excluded from the denominator and the
  search only ever runs on a GPU box. Neither claims cross-model transfer until the gated
  `PROVAEL_INTEGRATION=1` path is run with a 95% CI and a benign-FPR control.

## What we measure on LIBERO (redirection, not harm)

LIBERO is **benign tabletop manipulation**. The LIBERO `SuiteAdapter` does **not**
measure physical harm — it measures whether an attack **redirected** the policy to an
attacker-designated target (the default predicate is an end-effector keep-out zone; an
optional rule flags grasping a forbidden object). "Attack success" here means "the policy
was steered off-task in simulation", which is exactly the robustness signal a defense can
be evaluated against — not a real-world exploit.

## Intended users & uses

- VLA/robotics researchers and safety teams evaluating the robustness of **their own**
  or **openly published** policies.
- Red-team / blue-team exercises in simulation, to produce an ASR number that a
  defense (e.g. SafeVLA-style alignment) can be measured against.

## Responsible disclosure

If you use this tool and discover a concrete safety weakness in a specific **publicly
released** policy:

1. Do not publish a working real-world exploit.
2. Contact the model's maintainers privately first and allow reasonable time to
   respond.
3. Prefer sharing **aggregate ASR numbers and the config to reproduce them** over
   sharing anything tuned to cause physical harm.

## Out of scope / will not be added

- Code that controls real robots or hardware.
- Attacks tailored to cause physical injury or property damage in the real world.
- Detection-evasion tooling, or anything whose primary purpose is to make a real-world
  attack harder to catch.

By using `provael` you agree to use it only on systems you are authorized to test,
and only for defensive, research, or educational purposes.
