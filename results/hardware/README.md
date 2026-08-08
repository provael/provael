# results/hardware — physical-robot runs

**Runs executed to date: 0.** This directory is empty of results and exists anyway, deliberately.

## Why an empty directory is committed

A directory that appears only once results exist is a directory nothing can count. Two things read
this one:

1. `provael coverage` / the pinned public-evidence manifest derive a `hardwareResults` count from
   it, and provael.com renders its sim-to-real claim from that count — so the site stops saying
   "not yet measured" the day a run lands here, rather than waiting on someone to remember a docs
   edit. The website build **fails** if the count moves while the page still asserts "not yet run",
   which is deliberate: a page that half-corrects itself is worse than one that stops.
2. The protocol below is the pre-registration this directory is the destination for. Publishing the
   destination before the result is the same discipline as publishing the protocol before the run.

So: zero runs, said out loud, in the place a reader would look for the first one.

## Status

| | |
| --- | --- |
| Runs executed | **0** |
| Protocol | [`docs/studies/sim-to-real-so101.md`](../../docs/studies/sim-to-real-so101.md) — PRE-REGISTERED 24 July 2026 |
| Blocker | Physical hardware not yet in hand. The software path is installable (see below). |
| What exists | The protocol, the `[hardware]` extra (resolves today), and a dry-run that validates the pipeline end to end against the stub policy. |

## The hardware this is written for

| Item | Specification |
| --- | --- |
| Arm | SO-ARM101 (SO-101), the LeRobot-supported low-cost 6-DoF follower arm |
| Policy | SmolVLA (`HuggingFaceVLA/smolvla_libero`), the checkpoint behind the published simulation result |
| Cameras | Two synchronised RGB streams (top + wrist), matching the LeRobot v3.0 dataset convention |
| Host | A CUDA GPU host for policy inference; the arm itself is driven over USB by LeRobot |
| Software | `pip install 'provael[hardware]'` — resolves today, see below |

Nothing in this repository controls a robot. `provael` emits actions and scores outcomes; moving a
physical arm is LeRobot's job, under a human operator with an E-stop. See
[SAFETY.md](../../SAFETY.md).

## The protocol, in one paragraph

The pre-registration fixes the design before the data exists: run the instruction family that
transferred in simulation (`roleplay`, `goal_substitution`, `paraphrase`) plus the benign `none`
control against the same policy on the physical arm, with the keep-out predicate calibrated from
benign rollouts to a stated false-positive target *before* any attack runs. The question is whether
the simulation ASR predicts the physical one — and the honest answer may be no. A null is a result
here and will be published as one.

## What a run in this directory will contain

The same artifact set as every other committed run, so a hardware result is comparable to a
simulation one by construction:

```
results/hardware/<run-id>/
  report.json               the measured rates (no timestamps — determinism contract)
  execution-manifest.json   runtime provenance: started_at, ended_at, hardware, accelerator,
                            precision, dep_lock_digest — RECORDED, not reconstructed
  evidence-manifest.json    the evidence-state ladder for this run
```

The `execution-manifest.json` matters more here than anywhere else. The one existing real-policy run
has a *reconstructed* timestamp, which is why the README badge reads "date reconstructed" — see
[docs/standards/last-measured.md](../../docs/standards/last-measured.md). A hardware run must record
its provenance properly, and the dry-run below asserts the shape.

## Installing the hardware path

```bash
pip install 'provael[hardware]'        # lerobot[smolvla,libero,feetech]==0.5.1
```

`[hardware]` is `[lerobot]` plus LeRobot's own `feetech` extra — the STS3215 servo-bus driver
(`feetech-servo-sdk`) that the SO-101 uses. It is a **separate** extra rather than folded into
`[lerobot]`, because someone installing provael to red-team a policy in simulation should not end up
with a package that can address a motor bus. The sim path never pulls it.

It resolves today, against the same pinned `lerobot==0.5.1` as the policy, and that is the whole
point of wiring it before the arm exists: the alternative is resolving a second environment under
time pressure with a robot on the bench. Installing it adds **no** robot-control code to provael —
provael scores, it does not actuate; the teleop and record steps are LeRobot's own tooling.

Being one `pip install` from a physical run is not evidence of one. The count above stays **0**.

## Before the arm arrives

```bash
provael sim-to-real --dry-run          # validates the whole protocol against the stub policy
```

The dry-run exists so the first physical session is not also the first debugging session. It walks
the same code path a real run takes, against the deterministic CPU stub, and asserts the artifact
shape a real run must produce. It refuses to write into this directory, because this directory is
counted as physical evidence and a dry run must not inflate it.
