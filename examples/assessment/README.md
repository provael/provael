# One assessment, written down before it runs

This directory is the protocol template for a customer-run assessment — the document that says what
one test *means* before anyone reads its number — and a loadable example of its acceptance section
([`protocol.example.yml`](protocol.example.yml)). Copy both, fill the template with the customer,
and pass the protocol to every command that produces evidence:

```bash
provael attack --policy smolvla --suite libero --model HuggingFaceVLA/smolvla_libero \
    --attacks none,roleplay,goal_substitution,paraphrase,patch,scene_text,decoy_object \
    --seeds 5 --horizon 280 --protocol protocol.yml --out runs/pilot
provael report --in runs/pilot --format scorecard          # reads runs/pilot/report.decision.json
provael evidence-manifest --in runs/pilot --commit <sha>   # carries the same decision
```

A run without a protocol is a **diagnostic**: measured, and its acceptance not assessed. A `pass`
means one thing — the named protocol was satisfied. Nothing here invents a universal safe ASR.

## Scanning your own checkpoint

Before it loads a LeRobot checkpoint, `provael attack` reads the checkpoint's `config.json` and
processor files, and refuses one that names a backbone or tokenizer it has not checked, a policy
type or processor step it has not read, or one that turns `trust_remote_code` on. The checked
backbones are `HuggingFaceTB/SmolVLM2-500M-Instruct`, `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`
and `google/paligemma-3b-pt-224`. To see what it would object to without loading anything:

```bash
provael verify-checkpoint --checkpoint your-org/your-policy --path ./your-checkpoint \
    --no-require-digest
```

If that passes, `attack` loads the checkpoint as it is. If your checkpoint names another
backbone, the run stops before anything loads and lists what it found.
To scan it anyway, set the variable for that one command:

```bash
PROVAEL_TRUST_CHECKPOINT_CODE=1 provael attack --policy smolvla --suite libero \
    --model ./your-checkpoint --attacks none,roleplay --seeds 5 --horizon 280 \
    --protocol protocol.yml --out runs/pilot
```

That accepts whatever code your checkpoint's files make lerobot load, from your backbone's repo
and any other repo they name. Run it where that code can reach nothing it should not: a container
or VM with no credentials in its environment. The execution manifest records the variable, and
the protocol's checkpoint section should say it was set, and why.

## The protocol, section by section

Record every item below with the customer before the run. An item left blank is a finding about
the assessment, not something to fill in from the result.

| Section | What to record | Why it changes the meaning of the number |
| --- | --- | --- |
| **Checkpoint and simulator** | `--policy`, `--model` (exact checkpoint id and revision), `--suite`, task suite, simulator version, the container or lock digest | A rate is a property of one checkpoint in one simulator. The report's `deployed_policy` records what actually executed; the execution manifest records the code and package set. |
| **Tasks** | The exact task ids (`libero_object/0` … `/9`), and whether the set is the customer's deployment tasks or a proxy | A ten-task rate is not a rate for a task outside the ten. |
| **Intervention capabilities** | Which channels the attacker is assumed to reach: the instruction text, the camera image, scene text or objects, action-space access, weights | Each attack family assumes a channel. An attack whose channel the adapter cannot reach is **not applicable** on this configuration, and the report says so per episode (`applicable: false`, N/A in every table). Unavailable is unavailable — it is never scored as protection. |
| **Endpoint** | `unsafe_envelope` (the shipped predicate: the end-effector left the safe envelope), and whether the envelope is the documented default box or a calibrated one | An envelope exit is not task completion, not a calibrated hazard violation unless the predicate is calibrated, and not physical-robot evidence. Say which endpoint the acceptance criteria are about. |
| **Controls** | The benign `none` arm (required), the harmless-variation arms (`benign_reword`, `nonsense_text`, …), and the agreed **benign firing rate** the default or calibrated box may show on unattacked episodes | An ASR is a difference against the benign floor. A default box that fires on normal reachable space is a fact about the box; agree what benign rate is acceptable before reading any attack against it. |
| **Clean-task competence** | The minimum unattacked task-completion rate (`min_clean_task_success`) below which the attack result is not interpretable | A policy that fails the task unattacked has nothing to be redirected from. `clean_task_success_rate` is reported under benign conditions; task completion under attack is reported per episode beside the envelope measurement. |
| **Seeds and horizon** | `--seeds` (≥ 5 to bank a number; fewer is preliminary), `--horizon` (280 for LIBERO), episodes per cell | The project's own spread on LIBERO is ~14 percentage points across seeds. |
| **Budget and stop conditions** | GPU-hours or currency ceiling, wall-clock, and what happens when it is hit (resume from the ledger with `--resume`; never a smaller claim silently substituted) | A ten-task LIBERO screen is ~15 GPU-hours on an L4. |
| **Acceptance criteria** | The protocol file: critical attacks and tasks with their own gates, the estimator, minimum evidence per slice, the pooled bound, required controls and seeds, any bounded exception | See `protocol.example.yml`. Judged per slice on its own denominator; a slice that did not run is incomplete, never 0%. |

## What a reviewer must be able to say afterwards

- What constitutes an **event** — an episode in which the predicate fired within the horizon — and
  why that matters for the selected task (the envelope is the workspace the task is done in; leaving
  it is the behaviour a keep-out zone exists to stop).
- Whether the clean-task competence requirement was met. A run that did not meet it is reported
  with its attack rates *and* the statement that they are not interpretable as attack effects.
- Which requested attacks were **not applicable** to this adapter and suite, named. A missing
  sensor, action access or extractor blocks the corresponding acceptance claim; it does not
  satisfy it.
- Which decision was reached, under which protocol (name and content digest), and each reason —
  the same text in `report.md`, the scorecard, the SARIF, the OSCAL, the evidence manifest and the
  attestation.

## Scope

Start with one supported checkpoint and one simulator (SmolVLA × LIBERO-Object is the one with a
committed, re-measured body of evidence). This template adds no hazard ontology, no simulator and
no attack family; it names what the existing measurement means for one customer's task.
