# Crosswalk: Bit-Flip VLA

> **Defensive, sim-only.** This is a taxonomy-comparability artifact. Provael's `weight_integrity`
> family flips bits in weights **already loaded in memory**. It contains no hardware fault-injection
> path, no Rowhammer primitive, and nothing that would help deliver a fault on a real machine, and
> none is planned. See [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

**Source (pinned).** *Bit-Flip Attacks on Vision-Language-Action Models: Action-Decoding
Architecture Shapes the Vulnerability*, arXiv:[2608.15475](https://arxiv.org/abs/2608.15475)
(submitted 16 August 2026).

**Authors.** Yudong Gao, Linghan Chen, Wenhan Wu, Mia Zhou, Jiyao Wang, Kaiyan Ji, Mingyu Guo,
Honglong Chen.

Metadata above was read from the arXiv abstract page and the paper PDF on 20 August 2026.
Affiliations are not reproduced here because they were not read; the omission is deliberate rather
than an oversight. This card is authored by Provael alone; the authors have not reviewed, endorsed
or been consulted on it, and nothing here should be read as their claim.

## What they built

An attack on the **parameters** of a quantized VLA rather than on its input. Gradient-selected bit
flips in INT8 weights drive closed-loop task success to zero, while equal-count random flips do
comparatively little. Their headline is that the budget required tracks the **action-decoding
architecture**: roughly **1–5 flips** for direct-regression and discrete-token heads, against
roughly **100–300** for the flow-matching policies they evaluate (π0, π0.5). On a real 6-DoF arm,
task-calibrated emulated K=100 corruption yielded **0/20** successes against **14/20** clean and
**16/20** for an equal-count global-random control.

They scope their own claim carefully, and this card repeats that scoping rather than dropping it:
they evaluate *"logical INT8 corruption rather than end-to-end physical delivery"* and state that
*"physical fault delivery and ECC remain outside scope."*

## How it relates to Provael

`mapping_status: implemented-from, not-corroborated`

Provael 0.36.0 ships `weight_integrity` **because of this paper**, and the family's shape is taken
from it. That makes this the first crosswalk in this directory where Provael implements the
counterpart's construct rather than merely mapping onto it — and it makes the distinction between
*implementing* and *corroborating* the whole content of the card.

### What Provael implements from the paper

| Construct | In `weight_integrity` | Note |
|---|---|---|
| Emulated logical INT8 corruption | **Yes** | Flips applied to loaded weights; every record carries `emulated: true` |
| Gradient-selected bit targeting | **Partially** | One-shot first-order ranking, **not** their progressive re-ranking search |
| Equal-count random control arm | **Yes** | Mandatory, at the same K; `crossing_pair` refuses to return a gradient result without it |
| Budget sweep with a crossing point | **Yes** | Ladder K = 1/4/16/64/256; crossing reported against an explicit floor |
| Closed-loop evaluation | **Yes** | Scored on the suite's own unsafe predicate, not on a proxy |

### What Provael does not implement, and must not be read as having shown

| Construct | Status | Why it matters |
|---|---|---|
| **Architecture-dependence (1–5 vs 100–300)** | **Not reproduced** | Provael's only run is against the deterministic CPU fixture, which has one scalar danger head and **no action-decoding architecture at all**. It cannot exhibit the effect, and does not. |
| Real VLA policies (π0, π0.5, SmolVLA) | **Not run** | Needs a GPU run that has not happened. |
| Flow-matching head | **Not tested** | The half of their result that is most interesting to this project is the half Provael has no data on. |
| Progressive re-ranking search | **Not implemented** | Ours is strictly weaker, so a Provael null is a **lower bound**, never a finding that gradient selection fails. |
| Physical fault delivery | **Out of scope, permanently** | Theirs too. Provael additionally has no hardware run of any kind: its hardware run count is **0**. |
| Defense evaluation | **Not implemented** | The paper presents defense strategies; Provael measures none of them. |

### The one number Provael has, and what it is worth

Against the CPU stub, the gradient arm crosses a 50% unsafe rate at **K = 1** while the equal-count
random arm does not cross within the ladder at all. **This is a property of the fixture and is not
evidence about any real policy.** The fixture's danger head puts a bias parameter one step from the
output and dilutes the rest through a saturating clamp, so a ranking finds the short path
immediately and a uniform draw almost never does. It was built that way so the measurement path
could be exercised end to end on CPU in under a second — it is
[stub-validated](../studies/index.md), the weakest rung on the evidence ladder, and it corroborates
nothing.

## What is not done yet

The comparison this card exists to eventually make — Provael's crossing point beside theirs, per
architecture — **cannot be made today** and no partial version of it is offered here. It needs a
real policy with a real action head, which is a GPU run this project has not funded. Until then
`mapping_status` reads `not-corroborated`, and any external citation of Provael as independent
support for the architecture-dependence claim would be wrong.
