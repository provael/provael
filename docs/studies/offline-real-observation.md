# Offline real-observation study (recorded SO-101 frames × SmolVLA)

> **OPEN-LOOP. NO ROBOT MOVES.** This study replays the recorded frames of a real SO-101 dataset
> through the policy and compares what it *would* do under a benign instruction against what it
> *would* do under an attack. Nothing is executed. No trajectory is produced. **This is not a
> closed-loop real-robot attack success rate and must never be reported as one.** Provael has
> **0** physical-robot results; see [`results/hardware/`](https://github.com/provael/provael/tree/main/results/hardware).

> Status: PRE-REGISTERED — protocol only, no results claimed.

## Why this exists

The published result is 10/10 on SmolVLA × LIBERO, in simulation. The first question every reader
asks is whether a simulated attack means anything off the simulator, and the honest answer today is
that we do not know. The [sim-to-real study](sim-to-real-so101.md) answers it properly and needs an
arm that has not been bought.

This answers a **strictly narrower** question that needs no hardware: *does the attack change what a
real policy decides, when it is looking at real pixels from a real robot in real poses?* A narrow
real answer is worth more against that specific objection than a wide simulated one.

It is a rung on a ladder, not a substitute for the top of it.

## What is claimable, and what is not

| | |
| --- | --- |
| **Claimable** | "On N% of real recorded frames, the attack pushed the policy's commanded action outside the declared envelope." |
| **Not claimable** | "The arm left the envelope." The arm did nothing. It was a recording. |

Every artifact this study emits carries that distinction in a `claim_limits` field, in the payload
rather than in a docs page somebody may not open.

## Hypothesis

For the `instruction` family — the only family that transferred in simulation — the attack changes
SmolVLA's commanded action on recorded SO-101 frames, and does so in a direction that leaves a
benign-calibrated envelope more often than the benign instruction does.

**Null hypothesis:** the attack does not move the commanded action meaningfully on real recorded
observations, or moves it no more often out of the envelope than the benign instruction. **A null is
a result and will be published as one.** That matters more here than usual: a null would be evidence
that the simulation result does not survive contact with real observations, which is a finding about
our own headline number.

## The measurement

For each sampled frame `t` of a recorded episode, with the image held fixed:

```
a_benign = policy(observation_t, benign_instruction)
a_adv    = policy(observation_t, adversarial_instruction)

PRIMARY    divergence_t = || a_adv - a_benign ||₂
SECONDARY  applied ONCE from the real recorded state s_t, does a_adv leave the envelope?
```

**The benign arm is the policy's own action under the benign instruction — not the human's recorded
action.** Comparing against the teleoperator would measure "the policy disagrees with the human",
which is a different question and not the one asked.

**The horizon is one step, deliberately.** The tempting alternative is to integrate the predicted
actions forward into a trajectory. That is wrong on this data: open-loop integration compounds error
immediately and yields a path the arm would never have taken — a fabricated trajectory wearing the
costume of a measurement. One step from a state that actually happened is the longest horizon this
data honestly supports.

## The envelope, and when it is fixed

The envelope is **declared before any attacked frame is scored**, calibrated from benign frames of
the same dataset to a stated false-positive target. An envelope fitted after seeing the attacked
actions would produce whatever rate its author wanted.

Frames where the **benign** action also leaves the envelope are excluded from the headline and
reported separately. Such a frame says the envelope is mis-calibrated for that pose; counting it
would read the study's own instrument error as a finding. If the benign violation rate is not small,
**the headline is invalid, not merely qualified.**

## Dataset selection criteria

Named as criteria, not as a pinned repo. A pre-registration that depends on one third-party dataset
staying uploaded, unrenamed and unchanged is a pre-registration with someone else's housekeeping in
its critical path.

A dataset qualifies when it is:

- a LeRobotDataset at `codebase_version` **v3.0**
- `robot_type` in {`so101`, `so101_follower`}
- **6-DoF** state and action
- carrying at least one `observation.images.*` stream

**Verified candidates, 8 August 2026:**

| Dataset | Version | Robot | DoF | Frames |
| --- | --- | --- | --- | --- |
| `Guanli001/so101-vials-auto-dr-final100` | v3.0 | `so101_follower` | 6 | 59,017 |
| `wenyixu101/farpoint-so101` | v3.0 | `so101_follower` | 6 | 72,433 |

### Why the loader validates instead of trusting the name

Of five public datasets whose names contain `so101`, **three would have produced a wrong or
meaningless study**:

| Dataset | Problem |
| --- | --- |
| `kwangchaeko/so101_test` | `robot_type: koch`, **4-DoF**. Named so101, is a different robot. |
| `kaiserbuffle/so101_test` | Real SO-101, but codebase **v2.1** |
| `BasedLukas/so101_test_2` | Real SO-101, but codebase **v2.1** |
| `sree-aimaker/so101_pick_and_place` | Not a LeRobotDataset at all — bare `.mp4` files |

The koch one is the dangerous case because it fails **silently**: it would load, produce numbers,
and tell nobody the numbers were about a 4-DoF arm. So `src/provael/datasets/lerobot_frames.py`
asserts version, robot type and dimensionality, and **raises rather than warns**.

## Sample and stopping rule

Fixed before the run: a stated number of frames sampled at a fixed stride across a stated number of
episodes, with the sampling seed recorded. The run stops at that count. No looking at intermediate
divergences and deciding to extend — that is the degree of freedom pre-registration exists to
remove.

`_TBD_` until the compute path is chosen: frame count, stride, episode count, seed. **These must be
filled in before the first run, not after.**

## Scope limits, stated here rather than left to be inferred

- **Open-loop.** The policy never acts on its own output. Every frame starts from a recorded state.
- **One embodiment, one policy, one dataset.** No generality is claimed beyond it.
- **Recorded, not live.** The observations are real but historical; the scene never responds.
- **Not a real-robot result.** `results/hardware/` stays at 0 and this study does not write there.
- **Evidence rung: `real-forward`** — real policy, real observation, forward passes only. That is
  *below* `real-episode` on the ladder, because an episode at least executes. This is deliberately
  weaker evidence than the simulation result it is testing.

## Running it

```bash
pip install 'provael[lerobot]'          # GPU; the policy must actually load
provael offline-study --dry-run         # CPU stub, no download — validates the pipeline
```

The dry run exercises the whole path against the deterministic stub so the first real run is not
also the first debugging run.
