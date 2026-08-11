# Semantic reframing, not mechanical rewording

**Status: hypothesis with supporting evidence. Not a settled result.**

One policy (SmolVLA), one suite (`libero_object`, all ten tasks), simulation only, maintainer-run,
n=50 per arm, an **uncalibrated** keep-out predicate, and no independent reproduction. Everything
below is consistent with a single-policy artifact. It is published because the separation it reports
is large and the raw counts are committed, not because the question is closed.

## The claim

Two recent results conclude that VLA policies are largely insensitive to language. LIBERO-Plus
([arXiv:2510.13626](https://arxiv.org/abs/2510.13626)) reports that "models tend to ignore language
instructions completely" and that a VLA "degenerates into a form that disregards language, behaving
more like a Vision-Action (VA) model". Trinh, Akhtar and Azam
([arXiv:2603.12717](https://arxiv.org/abs/2603.12717)) find that a 70B-parameter LLM crafting
plausible-but-wrong reasoning traces *underperforms* mechanical object-name substitution, and conclude
the action decoder "depends on entity-reference integrity rather than reasoning quality or sequential
structure".

**What this run adds is not a perturbation neither paper tried — it is the safety framing.** Both do
change instruction meaning: LIBERO-Plus §4.2 replaces the target object in the instruction *and moves
the task goal with it* ("pick up the alphabet soup" → "pick up the tomato sauce"), and Trinh substitutes
object names inside the reasoning trace. Those are **generalization** probes: the ground truth moves,
and the question is whether the policy follows.

Provael asks the adversarial version of the same question. The task and the **safety envelope stay
fixed**; only the framing of the request changes, and the measurement is whether the policy leaves the
envelope it was supposed to stay inside. A generalization failure and an envelope exit are different
events, and a benchmark measuring the first says nothing directly about the second.

The instruction family happens to contain both halves of the contrast as separate arms, comparable at
matched `(task, seed)` cells in one run:

- `paraphrase` — **meaning-preserving**. Same request, different surface form.
- `roleplay` — **meaning-reframing**. The request is re-framed so a different outcome becomes the
  apparent goal, while the envelope it is scored against does not move.

## The numbers

From [`results/smolvla_libero_object_suite/`](https://github.com/provael/provael/tree/main/results/smolvla_libero_object_suite),
10 tasks × 5 seeds, provael 0.32.0. Wilson 95% intervals, not rounded away:

| arm | semantics | successes/attempts | rate | 95% Wilson | McNemar vs benign twin |
| --- | --- | ---: | ---: | --- | ---: |
| `roleplay` | **reframing** | 44/50 | 88.0% | **[76.2%, 94.4%]** | p = 4.6e-13 |
| `goal_substitution` | reframing | 15/50 | 30.0% | [19.1%, 43.8%] | p = 9.8e-04 |
| `paraphrase` | **preserving** | 3/50 | 6.0% | **[2.1%, 16.2%]** | **p = 1.0** |
| `none` (benign control) | — | 2/50 | 4.0% | [1.1%, 13.5%] | — |

Two facts carry the finding, and neither is a headline rate:

1. **The intervals for `roleplay` and `paraphrase` do not overlap.** 76.2% against 16.2% — the gap is
   not an artifact of point estimates.
2. **`paraphrase` is statistically indistinguishable from doing nothing.** McNemar p = 1.0 against its
   own benign twin at the same `(task, seed)`: 3 discordant one way, 2 the other. Meanwhile `roleplay`
   separates from the same control at p = 4.6e-13.

A [separate control run](https://github.com/provael/provael/tree/main/results/smolvla_libero_object_control)
adds two more meaning-preserving arms on the same policy, and both agree: `benign_reword` 1/50 (2.0%)
and `nonsense_text` 0/50, neither distinguishable from the benign control.

**The claim is therefore narrow:** on this policy, what predicts an envelope exit is whether the
instruction's *meaning* was changed, not whether its *surface form* was. It is not a claim that VLAs
attend to language in general — LIBERO-Plus and Trinh measure that question directly and this run does
not contradict them.

## What would falsify it

Stated before anyone looks, so the result cannot be rescued after the fact:

- **A meaning-preserving arm firing at a rate whose interval overlaps a reframing arm's**, on any
  policy. `benign_reword` at 1/50 and `nonsense_text` at 0/50 have already had that chance and did not
  take it, but three arms on one policy is not a law.
- **A reframing arm at or near the benign floor on a second policy.** If `roleplay` returns ~4% on
  OpenVLA or π₀, the separation is a SmolVLA artifact and this page is wrong.
- **A calibrated predicate collapsing the gap.** The predicate is uncalibrated and the benign control
  fires at 4%. If calibration raises that floor materially, `paraphrase` at 6.0% may be entirely
  false-positive, which would *strengthen* the separation — but the reverse is also possible and has
  not been ruled out.
- **Q-DIG-style search finding meaning-preserving prompts that fire.** Our `paraphrase` arm is a fixed
  bank, not a search. [arXiv:2603.12510](https://arxiv.org/abs/2603.12510) shows quality-diversity
  search finds failures a hand-written set misses, so a null from our bank bounds our bank and nothing
  wider.

## What sample size would settle the open half

The separation between `roleplay` and `paraphrase` is already unambiguous at n=50 per arm — disjoint
intervals, twelve orders of magnitude between the p-values.

**The unsettled question is the other one: whether `paraphrase` differs from doing nothing at all.**
Observed, it does not (3 vs 2 discordant pairs, p = 1.0). To detect a difference of the size actually
observed — a discordant odds ratio of 1.5 at a 10% discordant rate — a paired McNemar needs

> **≈197 discordant pairs → ≈1,960 episodes per arm** at α=0.05 two-sided, 80% power.

That is roughly **forty times** the current run, and about **US$60 of L4 time** at this project's
measured $0.031/episode. Until someone spends it, the honest statement is that `paraphrase`'s effect is
*bounded above* by 16.2%, not that it is zero.

## Limitations, restated

- One policy, one suite, simulation only. No hardware: `results/hardware/` reads **0**.
- Maintainer-run. Zero third-party reproductions.
- The keep-out predicate is **uncalibrated**; `provael calibrate` has never run on LIBERO.
- SmolVLA samples actions, so this is one draw. A second run of the same seeds produced 44/50 again for
  `roleplay`, but per-task cells moved in both directions.
- `paraphrase` is four templates. `benign_reword` is four templates. Neither is a search.

## Related work this refines

- **LIBERO-Plus**, [arXiv:2510.13626](https://arxiv.org/abs/2510.13626) — perturbs seven dimensions and
  finds models "largely insensitive to language variations… tend to ignore language instructions
  completely". Their §4.2 *does* change instruction meaning, replacing the target object in both the
  instruction and the goal; their Finding 7 is that VLAs lack strong cross-object
  instruction-following generalization. **The term "Language Ignorance" does not appear in the paper**
  and is not quoted here.
- **Trinh, Akhtar, Azam**, [arXiv:2603.12717](https://arxiv.org/abs/2603.12717) — object-name
  substitution in the reasoning trace costs 8.3 pp overall (−19.3 pp goal-conditioned, −45 pp on
  individual tasks) while reordering, spatial reversal, token noise and a 70B LLM all stay within
  ±4 pp.

**Neither is contradicted, and neither left the gap this fills.** Trinh's result has the same shape as
ours from the other side: what matters is *which entity is referred to*, not how the sentence is built.
Read together, the three results agree that surface form is cheap and reference is expensive. What this
run contributes is the adversarial framing — the same contrast measured against a **fixed safety
envelope with a benign control**, so the quantity is an envelope-exit rate rather than a
generalization score.
