# Crosswalk: LIBERO-Safety

> **Defensive, sim-only.** This is a taxonomy-comparability artifact. It runs no LIBERO-Safety
> harness, makes no submission to their benchmark, publishes no comparative score, and drives no
> physical robot. See [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

**Source (pinned).** *LIBERO-Safety: A Comprehensive Benchmark for Physical and Semantic Safety in
Vision-Language-Action Models*, arXiv:[2606.23686](https://arxiv.org/abs/2606.23686) (v1 submitted
22 June 2026, v2 26 June 2026; arXiv comment records "Accepted by ECCV 2026") ·
[libero-safety.github.io](https://libero-safety.github.io/).

**Authors.** Rongxu Cui\*, Zongzheng Zhang\*, Jingrui Pang, Haohao Chi, Jinbang Guo, Saining Zhang,
Shaoxuan Xie, Xin Jin, Yao Mu, Jiaolong Yang, Guocai Yao, Xianyuan Zhan, Ya-Qin Zhang, Hao Zhao†.
(\* equal contribution, † corresponding.)

**Affiliations.** Institute for AI Industry Research (AIR), Tsinghua University · Beijing Academy of
Artificial Intelligence (BAAI) · Beihang University · Eastern Institute of Technology, Ningbo ·
Shanghai Jiao Tong University · Microsoft Research Asia (MSRA).

Metadata above was read from the arXiv abstract page and the authors' project page on
18 August 2026. This card is authored by Provael alone; the LIBERO-Safety authors have not
reviewed, endorsed or been consulted on it, and nothing here should be read as their claim.

## What they built

A parametric safety benchmark that procedurally generates safety-critical scenarios, a
keypose-driven data-generation pipeline, and a dataset of **19,664 strictly collision-free
demonstrations** with extensive domain randomization. They evaluate **eight VLA models and two
embodied foundation models**, and report what they call "a critical generalization-safety
tension": higher-diversity training produced safer trajectories while task success stayed
bottlenecked by trajectory synthesis and semantic misalignment.

## How it relates to Provael

`mapping_status: complementary-axis, not-yet-crosswalked`

Their "strictly collision-free" construct and Provael's keep-out envelope violation measure the
same physical property from opposite directions. Same benchmark family, same simulator lineage.

The difference is the **threat model**, and it is the whole reason both can exist:

| | LIBERO-Safety | Provael |
|---|---|---|
| Regime | **Distributional** — randomisation, human-object scenarios, no attacker | **Adversarial** — an attacker chooses the instruction or the observation |
| Question answered | What does a policy do when the world varies? | What does a policy do when someone is trying? |
| Model coverage | Ten policies (8 VLA + 2 embodied foundation) | One real policy (SmolVLA × LIBERO) |

Neither subsumes the other and this card does not claim it does. Their model coverage is ten
policies against our one. Our attacker is real and theirs is absent. Read as a pair, they answer
different halves of the same safety question.

## What is not done yet

A concrete mapping from their safety-scenario taxonomy to the
[Embodied AI Security Top 10](../top10.md) has **not** been built. It is the obvious next artifact
and it is recorded here as owed, not as delivered — which is why `mapping_status` reads
`not-yet-crosswalked` rather than naming a coverage level this card cannot support.

The rates are also not comparable today, in either direction, because neither side publishes a
benign false-positive rate on shared fixtures. Provael's is **4% (2/50), Wilson 95% [1.1%, 13.5%]**,
and it is **uncalibrated** — the same default keep-out box on every task, tracked as
[issue #136](https://github.com/provael/provael/issues/136). Putting our number and theirs in one
column would assert a comparability that neither project has established.
