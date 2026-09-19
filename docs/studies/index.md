# Studies

Two kinds of page live here, and they are not interchangeable.

**Measured** studies have been run against a real policy and report what came back.
**Pre-registered** studies state the protocol, the predicate and the stopping rule *before* the run
— so that a null result is a result, not an embarrassment to be reframed. A pre-registered study
with no numbers in it has not been run yet. That is the intended state, not an oversight.

**Reproduce one before you cite any.** The [reproduction request](../reproduction-request.md) points
at the corrected sample — the delivery pack generated from the published body — and keeps three
levels apart: verify the digests, regenerate the derived artifacts from the committed shards, or
re-execute the policy with the pinned inputs and compare. Level 3 needs a Linux GPU box and the
`[lerobot]` extra; levels 1 and 2 need neither. Report the outcome, whichever way it comes out, with
the [reproduction result form](https://github.com/provael/provael/issues/new?template=reproduction-result.yml);
it lands in the [reproduction register](../errata.md#reproduction-register), which counts nothing
until someone does. The counters further down this page are honest and they are not the point of it.

## Measured

| Study | Kind |
| --- | --- |
| [Instruction canonicalization](instruction-canonicalization.md) | Defense — measured on the stub fixture only (no real-policy defended arm committed) |
| [Action envelope](action-envelope.md) | Defense — measured on the stub fixture only (no real-policy defended arm committed) |
| [EAI04 action-space-integrity transfer](eai04-action-space-transfer.md) | Attack transfer |
| [Offline real-observation (recorded SO-101 frames)](offline-real-observation.md) | Attack on real recorded frames — **open-loop**, measured null |

## Pre-registered, not yet run

These carry a protocol and no results. Do not cite them as evidence of anything except intent.

| Study | Target |
| --- | --- |
| [π0 (openpi) cross-architecture instruction transfer](pi0-openpi-transfer.md) | π0 via openpi |
| [Meta-World second-suite instruction transfer](metaworld-transfer.md) | Meta-World |
| [Sim-to-real correlation (SO-ARM101 + SmolVLA)](sim-to-real-so101.md) | Physical arm |
| [Humanoid whole-body / locomotion transfer (GR00T-N1)](humanoid-locomotion-transfer.md) | GR00T-N1 |

Most of these need a GPU box and a checkpoint that is not yet wired up end-to-end. The
[roadmap](../roadmap.md) says which, and the [findings](../findings/index.md) index says what has
actually been measured so far.

## Where this project is behind, as of 6 August 2026

Three gaps, stated as gaps. Each is a zero, each has a named action, and each action has a date by
which an outcome is published — the number if it exists, and the reason if it does not. A date with
no outcome attached is an aspiration, and this page does not carry those.

### 1. Zero real-robot results. Others are publishing them.

Provael has **never run on hardware**. Every number this project has published is simulation, and
`results/` contains no hardware directory because there is no hardware run to put in one. The
sim-to-real protocol at [sim-to-real (SO-ARM101)](sim-to-real-so101.md) is pre-registered, which
means the design is fixed and the trials have not been run.

This is not a nuance, and this week made that concrete.
[SARF](https://arxiv.org/abs/2608.03231) (submitted 4 August 2026) reports a defense evaluated **on
a real PiPER manipulator**, improving average success under their AGSD attack "from 23.0% to 65.0%".
[FLARE](https://arxiv.org/abs/2607.14698) reports attack and defense numbers on a physical 6-DoF
platform. Those are real-hardware numbers of a kind Provael has not produced for any family, attack
or defense.

**Action, with a date:** the SO-ARM101 protocol is fixed and needs an arm, a GPU host and operator
time, not a design decision. **By 31 October 2026 this page states one of two things: the completed
trial count with its measured sim-to-real correlation, or the specific blocker and its cost.**
Whichever it is, it is written here on that date rather than left to be inferred from silence.

*Stated early, 20 September 2026:* the trial count is **0** and the blocker is known and costed.
The arm (about ₹40,000 landed) has not been bought; the protocol's 1 September amendment added two
hardware prerequisites no kit ships — a physically operated inline cut on the DC supply, and a
per-trial servo-bus voltage trace — because the servos' own over-current protection re-arms on the
next command and a brown-out is indistinguishable from a redirection in the direction that flatters
the hypothesis ([roadmap](../roadmap.md#blocked-on-hardware--sim-to-real-so-arm101)). The
[roadmap](../roadmap.md) now carries the outcome date: **published by 31 December 2026, even if
null.** The 31 October line above is kept because it was the commitment; this paragraph is what it
resolves to.

### 2. Zero results against any flow-matching policy. DRIFT just published several.

*As written on 6 August 2026:* Provael has produced **no measurement against a flow-matching policy
of any kind**; the `pi0`, `pi05` and `pi0fast` adapters were registered with no checkpoint ever
loaded. *Updated 20 September 2026:* that is no longer true of **π0.5** — its preliminary leg on
LIBERO-Object (three seeds, two of eight arms) was committed on 18 September
([results](https://github.com/provael/provael/blob/main/results/pi05_libero_object_2026-09-18/README.md),
[finding](../findings/2026-cross-arch-transfer.md)): `roleplay` 1/30 against `none` 0/30, McNemar
p = 1.0, task success 27/30 unattacked and 8/30 under the frame. The frame breaks the task on both
policies; only SmolVLA leaves its envelope doing so, and **no transfer of the envelope-exit effect
is claimed**. `provael list-policies` now marks `pi05` *measured — preliminary*; `pi0` and `pi0fast`
have no run committed here. The **π0-via-openpi** leg — the framework question, at
[π0 (openpi) transfer](pi0-openpi-transfer.md) — is still pre-registered and unrun.

[DRIFT](https://arxiv.org/abs/2608.03207) (submitted 4 August 2026) reports a universal patch
against **π0 and π0.5 across four LIBERO suites**, and argues the robustness those policies were
credited with "is largely illusory". Provael cannot confirm, contradict or contextualise that,
because it has never measured the class of policy the claim is about. The taxonomy question it
raises is filed as a proposal in the [Top-10 RFC](../top10-rfc.md); the measurement question is this
gap.

**Action, with a date:** this is the cheapest of the three — the openpi adapter is a CPU client
against a GPU policy server, so it needs a served checkpoint rather than new code.
**By 30 September 2026 this page carries either the first Provael instruction-family rate against
π0 with its Wilson interval and benign control, or the reason the served path did not come up.**

*Stated early, 20 September 2026:* the served π0 path has not come up, and the reason is scheduling,
not a defect: the one GPU box is running the π0.5 arms and the LIBERO-10 body, `[openpi]` and
`[lerobot]` pin conflicting numpy majors so the leg needs its own environment, and the calibrated
predicate ([roadmap](../roadmap.md)) now comes before any further architecture leg — a rate
measured under the box that is about to be replaced would be re-measured within weeks. The
flow-matching question itself got its preliminary answer from π0.5 above. The framework question
stays open, dated on the roadmap under the second-architecture item (October–December 2026).

### 3. Zero third-party submissions and zero forks.

The published board carries four rows. All four are the maintainer's own single run, all
`submitted_by: provael`, and the board itself reports **1 submitter, 0 independent**. The repository
has **0 forks**. Nobody outside this project has reproduced a published result, and
[the register that would record it](https://www.provael.com/verification/) is empty.

The submission path stopped being the excuse: `provael submit` validates a run, signs it and opens
the pull request in one command.

**Action, with a date: MET on 8 August 2026, 23 days before the deadline.** The commitment was
that *by 31 August 2026 the release containing `provael submit` is published to PyPI*. It shipped
in **0.32.0** and is in every release since — `pip install provael` then `provael submit --help`
resolves, with no git install required. The original date is kept above rather than deleted,
because a commitment that disappears once it is met is not a record.

Two things that did **not** change, and pretending otherwise would be the easy mistake here.
Shipping the command removed the barrier; it did not produce a submission. The register is still
empty, the board still reports **0 independent**, and the fork count is still **0**. Whether anyone
submits was never something this project could put a date on, and no date is claimed for it now.
The queue is open at
[`Sattyam/provael-leaderboard-requests`](https://huggingface.co/datasets/Sattyam/provael-leaderboard-requests)
— an earlier version of this path pointed at an org that had never been created, which is recorded
in `leaderboard/README.md` rather than quietly repaired.

### Why this section exists

A project whose argument is that its numbers are checkable does not get to report only the numbers
that flatter it. Each item above is a zero that a reader would otherwise have to infer from
absence — and absence is exactly what this project criticises elsewhere. Every one of these three
changes the day it is no longer true, and the changed date is what makes it a record rather than a
posture.
