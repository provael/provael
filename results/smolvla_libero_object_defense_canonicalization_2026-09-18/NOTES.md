The `instruction_canonicalization` defense on the ten `libero_object` tasks, three seeds per arm,
against the benign control and `roleplay`. Run on the workstation on 18 September 2026 under
provael 0.41.2.

The attack survives the defense: 20/30 with a benign floor of 1/30, McNemar p=3.8e-06, and a
competence control of 29/30 — so unlike the envelope run beside this one, the policy could still do
the task.

**What this is not.** It is tempting to read 20/30 (67%) against the undefended 42/50 (84%) on
`smolvla_libero_object_suite_2026-09-14` and call it a reduction. Do not. The two runs use different
seed counts (3 vs 5 per task) and their task-clustered intervals overlap ([43%, 87%] against
[62%, 100%]), so the difference this run supports is "the attack still works with the defense on",
not a measured effect size. A paired defended-vs-undefended comparison at matched seeds has not been
run.
