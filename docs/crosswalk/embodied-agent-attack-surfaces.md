# Crosswalk: Embodied-agent attack surfaces (coverage map)

> **Defensive, sim-only.** This card maps Provael's coverage onto an external survey's taxonomy. It
> runs no harness, publishes no comparative score, and drives no physical robot. See
> [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

**Source (pinned).** *Security of Foundation-Model-Powered Embodied Agents: Attack Surfaces,
Attacks, Defenses, and Evaluation*, arXiv:[2608.16843](https://arxiv.org/abs/2608.16843) (submitted
17 August 2026).

**Authors.** Jiawei Liu, Jiacheng Guo, Tian Zhang, Yiwei Xu, Juan Wang, Jinlin Fan, Bowen Xiao.

Metadata above was read from the arXiv abstract page on 20 August 2026. Affiliations are not
reproduced here because they were not read. This card is authored by Provael alone; the authors
have not reviewed, endorsed or been consulted on it.

## What they built

A trust-boundary-centric survey organising the threat landscape for foundation-model-powered
embodied agents into **five layers and twelve attack surfaces**, over **58 attack records** and
**61 defense records** published through 15 August 2026.

**The five layers are not named on the abstract page and are therefore not reproduced here.** The
twelve attack surfaces are, and this card maps onto those rather than onto a layer structure it has
not read. Naming a five-layer taxonomy from inference would be inventing a counterpart's categories
in order to map onto them, which is the failure mode these cards exist to avoid.

Their quantitative finding is a lopsided field: attack research concentrates on **multimodal
perception** and **action interfaces**, defenses concentrate on **action-level and runtime
protection**, and four areas are called comparatively underexplored — **context and long-term
memory**, **middleware and networking**, **world-state integrity**, and **multi-agent trust**.

## How it relates to Provael

`mapping_status: coverage-map, one-directional`

This is a **coverage map, not a comparability claim**. It records which of their twelve surfaces
Provael has an attack for and which it does not. No rate is compared, in either direction, because
a survey publishes no rates to compare against.

The map is one-directional on purpose: it says what Provael covers of their taxonomy, and says
nothing about what their 58 attack records cover of Provael's.

| Their attack surface | Provael | Families |
|---|---|---|
| Model supply chain | **Partial** | `backdoor` (EAI03) screens planted triggers; `weight_integrity` (EAI03) screens weight corruption. Both screen the **asset**; neither models **delivery**. |
| User instructions | **Yes** | `instruction`, `optimized_instruction` (EAI01) — the only surface with a measured real-policy transfer |
| Context and memory | **None** | No attack. One of the four the survey calls underexplored. |
| Physical semantic environments | **Partial** | `injection` scene-text (EAI05), `misalignment` (EAI06) |
| Multimodal perception | **Yes** | `visual`, `sensor_spoof`, `optimized_patch`, `universal_patch` (EAI02) |
| World state | **None** | No attack. Underexplored per the survey. |
| Internal reasoning | **None** | No attack. |
| Task planning | **None** | No attack. |
| Action interfaces | **Yes** | `action`, `action_space`, `optimized` (EAI04) |
| Middleware | **None — out of scope** | EAI07, declared `out-of-scope-for-simulation`: faithful coverage needs real firmware and real ROS-DDS traffic, which a simulator cannot supply. A boundary, not a backlog item. |
| Multi-agent communication | **None** | No attack. Underexplored per the survey. |
| Execution control | **Partial** | `action_space` critical-step freeze (EAI04) |

**Five of twelve surfaces have no Provael attack at all**, and one more is a declared permanent
boundary. Provael's coverage sits exactly where the survey says the field's attention already
concentrates — perception and action interfaces — and is absent from three of the four areas it
calls underexplored.

That is the useful output of this card and it is not a flattering one. Reading it the other way
round: **Provael is well-covered where the field is crowded and empty where the field is thin.**

## What is not done yet

Nothing here is a roadmap commitment. The five empty rows are recorded as empty, not as planned;
this project has seventeen adversarial families of which **three have been exercised against a real
policy**, so breadth of registry is not its constraint and adding surfaces would not change that.
A dated commitment to any of these rows would be a claim this card cannot support.

The one row worth flagging as a genuine gap rather than a choice is **context and long-term
memory**: it is in scope for a simulator, unlike middleware, and Provael has nothing there.
