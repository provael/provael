# Safety & responsible use

`vla-redteam` (RoboPwn) exists to **harden** open Vision-Language-Action robot
policies, by measuring how often instruction-level manipulation can drive a policy
into an unsafe state in **simulation**. It is a defensive / evaluation tool, built in
the spirit of responsible disclosure.

## Sim-only by default

- The tool operates on **simulated** policies and environments. The default,
  fully-supported path is the CPU `stub` policy + `stub` suite, which involve **no
  model, no robot, and no network**.
- Running against a real VLA policy (e.g. SmolVLA via LeRobot) still happens **inside
  a simulator** (e.g. LIBERO). `vla-redteam` does **not** drive physical robots and
  ships no robot-control or actuator code.

## No real-world-harm payloads

- The shipped `instruction` attacks are short, generic, **templated** reframings
  (role-play, goal-substitution, paraphrase). They are designed to probe whether a
  policy follows a redirected goal in a benchmark — **not** to provide a recipe for
  causing harm.
- The `StubPolicy`'s "trigger lexicon" is an intentionally transparent **test
  fixture** (a handful of words with weights) so the CPU pipeline produces a
  measurable Attack Success Rate with no model. It is not a real exploit and does not
  transfer to real policies.
- We deliberately **exclude** from Part 1 the families most prone to misuse and
  hardest to defend (optimized adversarial suffixes / GCG, visual perturbations,
  observation-channel injection). When added, they will remain sim-only and
  benchmark-scoped.

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

By using `vla-redteam` you agree to use it only on systems you are authorized to test,
and only for defensive, research, or educational purposes.
