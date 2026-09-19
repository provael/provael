# When a change needs a real-policy validation before it is claimed to work

The CPU gate (`ruff`, `mypy`, `pytest`, the docs gates, the wheel smoke) exercises everything except
the paths it cannot: a real adapter loading a real checkpoint, the scorer against a real simulator,
a calibration fitted from real rollouts. A green gate on those paths is a statement about the stub.
This page says when a small real-policy validation is required before a change to one of them is
described as working, and what "small" means.

## Trigger

Run a validation when a change touches any of:

- a supported real adapter (`src/provael/policies/lerobot_adapter.py`, `libero` glue) — loading,
  observation renaming, action unnormalisation, the controller convention, seeding;
- scoring that a real run's rate depends on (`scoring/asr.py`, `scoring/paired.py`, the unsafe
  predicate in a real suite);
- calibration fitting or loading (`calibration.py`, `suites/calibrations/`, `cli/calibrate.py`);
- the pins of the `[lerobot]` extra.

A docstring, a README sentence, a CPU-only emitter or a test file does not trigger it.

## What "small" means

- **One task, one arm pair, one seed set** on the supported configuration
  (`--policy smolvla --suite libero --model HuggingFaceVLA/smolvla_libero --tasks libero_object/0
  --attacks none,roleplay --seeds 3 --horizon 280`), on the Modal lane
  (`examples/gpu-ci/modal_libero_suite.py`, manual dispatch) or the workstation. Roughly one
  GPU-hour; not a ten-task sweep on every prose edit.
- **Compare against the committed run of the same task**
  (`results/smolvla_libero_object_suite_2026-09-14/libero_object_0`) with
  `provael report --baseline`: the diff records what changed and whether the runs are like-for-like.
- **Keep the artifacts**: the run directory with its execution manifest is committed under
  `results/` only if it is a measurement worth recording; otherwise it is attached to the pull
  request. Either way its provenance fields are complete (the results gate refuses new runs without
  them).

## What the record says

- Validated: the PR names the run and the diff. The change may say the path works.
- Not available (no GPU, no budget, a broken lane): the PR says so, the change ships with an
  **experimental** limitation on the path it touched, and the limitation is removed by a later
  validated run — never by time passing.
- Failed: the failure and its artifacts are preserved, the change does not ship as working, and the
  finding is recorded (errata if a published number is affected).

Unavailable execution is reported as unverified. It is never reported as passed.
