# Studies

Two kinds of page live here, and they are not interchangeable.

**Measured** studies have been run against a real policy and report what came back.
**Pre-registered** studies state the protocol, the predicate and the stopping rule *before* the run
— so that a null result is a result, not an embarrassment to be reframed. A pre-registered study
with no numbers in it has not been run yet. That is the intended state, not an oversight.

## Measured

| Study | Kind |
| --- | --- |
| [Instruction canonicalization](instruction-canonicalization.md) | Defense — measured |
| [Action envelope](action-envelope.md) | Defense — measured |
| [EAI04 action-space-integrity transfer](eai04-action-space-transfer.md) | Attack transfer |

## Pre-registered, not yet run

These carry a protocol and no results. Do not cite them as evidence of anything except intent.

| Study | Target |
| --- | --- |
| [π0 (openpi) cross-architecture instruction transfer](pi0-openpi-transfer.md) | π0 via openpi |
| [Meta-World second-suite instruction transfer](metaworld-transfer.md) | Meta-World |
| [Sim-to-real correlation (SO-ARM101 + SmolVLA)](sim-to-real-so101.md) | Physical arm |
| [Offline real-observation (recorded SO-101 frames)](offline-real-observation.md) | Real recorded frames, **open-loop** |
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

### 2. Zero results against any flow-matching policy. DRIFT just published several.

Provael has produced **no measurement against a flow-matching policy of any kind**. The `pi0`,
`pi05` and `pi0fast` adapters are registered and `provael list-policies` marks them scaffolding:
none has loaded a checkpoint. The cross-architecture protocol at
[π0 (openpi) transfer](pi0-openpi-transfer.md) is pre-registered and unrun.

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

### 3. Zero third-party submissions and zero forks.

The published board carries four rows. All four are the maintainer's own single run, all
`submitted_by: provael`, and the board itself reports **1 submitter, 0 independent**. The repository
has **0 forks**. Nobody outside this project has reproduced a published result, and
[the register that would record it](https://www.provael.com/verification/) is empty.

The submission path stopped being the excuse: `provael submit` validates a run, signs it and opens
the pull request in one command, and it is merged on `main`. It is **not yet in a published
release**, so today it requires installing from git — which is a real barrier for exactly the
person most likely to try.

**Action, with a date:** **by 31 August 2026 the release containing `provael submit` is published to
PyPI**, so reproducing a result and submitting it needs `pip install provael` and one command. If
that date passes without the release, the reason is recorded here. Whether anyone then submits is
not something this project can put a date on, and no date is claimed for it.

### Why this section exists

A project whose argument is that its numbers are checkable does not get to report only the numbers
that flatter it. Each item above is a zero that a reader would otherwise have to infer from
absence — and absence is exactly what this project criticises elsewhere. Every one of these three
changes the day it is no longer true, and the changed date is what makes it a record rather than a
posture.
