# Provael ↔ XPolicyLab crosswalk

> **Defensive, sim-only.** A comparability and composition artifact. It runs no XPolicyLab harness,
> makes no RoboDojo leaderboard submission, publishes no comparative score, and drives no physical
> robot. See [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

**Source (pinned).** *XPolicyLab: A Unified Standard and Open Ecosystem for Robot Policy Evaluation
and Deployment*, Chen, Chen, Nian, Cai, Chen, Lin, Liang, Chen et al. (68 authors),
arXiv:[2608.09892](https://arxiv.org/abs/2608.09892) (v1 10 August 2026, v2 11 August 2026) ·
[xpolicylab.github.io](https://xpolicylab.github.io/) ·
[github.com/XPolicyLab/XPolicyLab](https://github.com/XPolicyLab/XPolicyLab), Apache-2.0. Led by
MMLab@HKU and Tsinghua. Repository facts below are read at commit `1e5a0bd` (16 August 2026).

**There is no `provael crosswalk --target xpolicylab`.** The four emitting targets are
`robojailbench`, `foresight`, `safevla` and `vla_arena`; this is a doc-only card, like the
[halos integrator card](halos-integrator.md). A machine-readable artifact would imply a mapping
between metrics, and as the next section explains, there is no shared metric to map.

## This is not a comparability crosswalk, because there is nothing to compare

The other four crosswalks answer "their number versus ours, and may they sit in one column". That
question does not arise here, and pretending it did would be the mistake.

**XPolicyLab performs no adversarial, attack, red-team, robustness or safety-envelope evaluation of
any kind.** That is not an inference from its framing. Across the 57 XPolicyLab-authored files in
the repository, the full arXiv text and the site, the terms `adversarial`, `attack`, `robustness`,
`red team`, `jailbreak`, `perturbation` and `safety envelope` return **zero** hits. The two
`safety` hits are a websocket keepalive comment and one sentence placing "safety supervision" on
the environment side of a client/server split. Repository-wide `perturbation` hits exist only
inside vendored third-party model code, where they are data augmentation.

Symmetrically: **Provael is not an evaluation platform.** It does not standardise how a policy is
served, does not rank capability, and integrates nothing. It measures what one policy does under
attack, against a benign twin, and emits evidence.

Neither is a weaker version of the other. They are different layers.

## What XPolicyLab actually standardises

| | |
| --- | --- |
| **Observation** | A dict tree: `instruction`, `env_idx`, `vision/<cam>/{color, depth, intrinsic_matrix, extrinsics_matrix}` across head / wrist / third-view cameras, `state/{left,right}_{arm_joint_state, ee_pose, tcp_pose, …}`, `state/mobile/*`. Poses are `[x, y, z, qw, qx, qy, qz]`, images RGB end to end. |
| **Trajectory** | The same tree, time-major and pluralised: `colors` `(T,H,W,3)`, `left_arm_joint_states` `(T,DOF)`, plus a top-level `action/` block keyed like `state/`. |
| **Action** | `list[dict]` of arrays keyed like `state/`; dimensions from `get_robot_action_dim_info(env_cfg_type)`, never hard-coded. |
| **Adapter** | `class Model(ModelTemplate)` in `policy/<POLICY>/model.py`, implementing `__init__(model_cfg)`, `update_obs(obs)`, `get_action()`, `reset()`, plus batch variants and two optional hooks. Transport is websocket with msgpack and numpy. |

These are dictionary conventions, not Python classes — there is no `Observation` or `Trajectory`
type in the codebase.

Their motivating claim, verbatim from the abstract: connecting N policies to M evaluation
environments "requires O(NM) separate integrations. We present XPolicyLab, a unified standard and
open ecosystem that reduces this cost to O(N+M)."

**On the policy count, cite carefully.** The paper abstract and the site both say **42** policies
("The ecosystem integrates 42 robot policies", Table I "as of August 8, 2026"). The repository
README at the same commit says **41**, and `policy/` contains **40 adapter directories plus a
`demo_policy` template**. The gap is specific rather than rounding: the published list of 42
includes VLAct, UniT and RxBrain, none of which has a directory, and omits π0-Fast, which does. Use
"42, their published figure as of 8 August 2026" or "40 adapters in the repository at `1e5a0bd`",
and say which you mean.

## Where the two touch: the leaderboards

XPolicyLab hosts no leaderboard. It feeds
[RoboDojo](https://robodojo-benchmark.com/leaderboard), whose real-world board carried **10
entries** as of 4 August 2026 across ARX X5, Piper and Piper X on 18 physical tasks, and whose sim
board carried 34.

RoboDojo is stronger than provael's board on the axis provael is weakest, and the entry should say
so plainly. Its protocol states scores are "computed by the official evaluation system rather than
self-reported by participants", it re-scores submissions on **hidden verification layouts** to
catch overfitting to public ones, and it is maintained by a non-profit. Provael's board has
[zero third-party submissions](https://www.provael.com/leaderboard/) and every row is
maintainer-run and labelled as such.

Where provael's protocol is the stronger one is narrower and worth stating exactly. RoboDojo
reports **mean and standard deviation over three seeds**. It has no benign control arm, no matched
pairs and no significance test, and XPolicyLab itself has no statistical machinery at all — its
only evaluation instruction is to run `eval.sh` and "record task success rates". Provael's arms run
in one report, matched at the same `(task, seed)`, with an interval and an exact McNemar p-value.
That is a difference in what the number means, not in how good the number is.

## The interesting sentence

**A policy integrated into XPolicyLab is a policy provael could attack, if provael spoke their
adapter interface.** The two compose, and they compose in one direction: XPolicyLab standardises
the surface, provael attacks whatever is behind it.

The mechanics are unusually favourable. Provael's `PolicyAdapter` ABC needs a load step and an act
step; XPolicyLab's `Model` contract offers `update_obs(obs)` then `get_action()`, with `reset()`
between episodes. That is close to a rename. One adapter on our side would put **40 real policies**
within reach of the attack registry, against the three families that have ever met a real model
today.

## Is that integration planned?

**Yes.** It is planned, and it is the highest-leverage integration available to this project, for
the reason above: one adapter, forty policies.

Stated precisely so it is falsifiable rather than reassuring:

- **Scope.** An `xpolicylab` policy adapter in `src/provael/policies/`, mapping their `Model`
  contract onto our ABC, behind an optional extra, with the same `PROVAEL_INTEGRATION=1` gate every
  other real-policy backend uses.
- **Not in scope.** Submitting to RoboDojo. Their board ranks capability and ours measures attack
  success; putting a provael number on a capability board would be the category error the rest of
  this directory exists to prevent.
- **What gates it.** GPU budget, the same blocker as `provael calibrate` never having run on
  LIBERO. The adapter is cheap to write and expensive to *validate*, and an adapter nobody has run
  against a real checkpoint would be a fourteenth stub-validated backend rather than a result.
- **Precedent.** `robocurve/inspect-robots` has already built an XPolicyLab plugin, so the
  integration path has been walked by another evaluation project.

There is currently **no** public connection between the two projects: zero GitHub issues or PRs
mentioning both, zero occurrences of `xpolicy` in this repository before this file, and zero
occurrences of `provael` in theirs.

## mapping_status

`cited, not crosswalked`. No metric is shared, so no row-level mapping exists to emit. This card
records a **composition** relationship, not a comparability one, and the distinction is the point:
every other file in this directory answers "can these numbers sit together", and this one answers
"can these tools sit together".
