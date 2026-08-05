# The Embodied AI Security Top 10 — RFC process (v0.2 → v0.3)

> Status: PLANNED — no results claimed. This document governs how the
> [Embodied AI Security Top 10](top10.md) evolves. It is about process, not measurement: every risk
> entry still stands on its own cited evidence.

The Top 10 is a **community draft, licensed CC-BY-SA 4.0**, deliberately unbranded and donatable —
[not affiliated with OWASP® or MITRE®](top10.md). It is currently at **v0.2**. This page is the
process for reaching **v0.3**: how to propose a new risk, dispute an existing one, and how a change
gets reviewed and merged.

## How a change happens

1. **Open an issue.** Use the
   [Top-10 proposal template](https://github.com/provael/provael/issues/new?template=top10_proposal.yml)
   to propose a new risk, or the
   [propose / dispute / fix template](https://github.com/provael/provael/issues/new?template=top10-feedback.yml)
   to dispute a ranking or fix a framework mapping. State the threat model and link the evidence.
2. **Discuss in the open.** Discussion happens on the issue and in the **Top-10 RFC**
   [discussion category](community.md). The bar is a concrete, adversarially-reachable threat with
   at least one referenceable source (arXiv, CVE, advisory, or a reproducible attack).
3. **Review.** A change is reviewed by the maintainer **and** at least one contributor from a
   different organization (see the goal below). Review checks the threat model, the evidence, the
   cross-framework mapping (MITRE ATLAS / NIST / ISO), and that the change does not overstate what
   is measured.
4. **Versioned merge.** An accepted change lands in `docs/top10.md` with the version bumped and a
   dated line recording what changed. No silent edits: a risk enters, moves, or leaves the list
   only through a merged PR that says why.

A small, concrete fix (a broken mapping, a typo, a clarified sentence) can skip straight to a PR
editing `docs/top10.md` — the issue step is for anything that changes the *set* or the *ranking*.

## Entry template

Every risk on the list carries these fields; a proposal for a new one should fill them in:

- **ID** — the proposed `EAIxx` id, or "renumber" if you are re-ordering existing risks.
- **Title** — a short, specific name (e.g. "Indirect / embodied prompt injection").
- **Threat model** — who the attacker is, what they control, and what they achieve. Must be
  **adversarial** and **embodiment-relevant** (see the [Top-10 scope note](top10.md)).
- **Example attack** — one concrete, referenceable instance. A Provael attack family is ideal but
  not required; a published paper or a real advisory also counts.
- **Measured evidence** — what has actually been measured, and where. If nothing has been measured
  yet, say so: a risk can be listed on threat-model grounds and marked not-yet-measured, but it is
  never dressed up as a result.
- **Mitigations** — the known defenses, and whether any is measured (see [defenses](defenses.md)).
- **References** — the arXiv / CVE / advisory / standard clauses that back the entry.

## Open amendment: first-step denoising redirection (proposed 6 August 2026)

> **Status: PROPOSED. Nothing has moved.** `docs/top10.md` is unchanged at v0.2 and
> `src/provael/eai.py` is unchanged. This section is the proposal and the argument for it, filed
> through the channel above so it can be disagreed with before it is anywhere else. A taxonomy that
> absorbs a paper the week it lands is not a standard, it is a news feed.

### What prompted it

[DRIFT](https://arxiv.org/abs/2608.03207) (Tae and Lee, submitted 4 August 2026) reports a universal
adversarial patch against flow-matching VLAs whose distinguishing property is not *where* it is
delivered but *which part of the computation it corrupts*. Their words: **"attacking only the first
denoising step is both stronger and cheaper than attacking a wider window of steps"**, which they
attribute to a gradient conflict specific to input-space optimization and describe as "exactly
opposite to the training-time backdoor regime". The prior reputation of flow-matching policies for
robustness, they argue, **"is largely illusory: it stems from prior attacks ignoring the multi-step
denoising ODE."**

The Top 10 has no name for this. It names channels (perception, instruction, action space) and it
names training-time compromise, but it has no vocabulary for *a stage of an iterative inference
procedure* being the attack surface. See [PRIOR_ART.md](https://github.com/provael/provael/blob/main/PRIOR_ART.md)
for the full citation and for what Provael has and has not measured here — which is nothing:
**no Provael result exists against any flow-matching policy.**

### The proposal

| Field | Proposed value |
| --- | --- |
| **ID** | Sub-class, not a new top-level risk. Proposed `EAI02.d` (see the placement argument below) |
| **Title** | First-step denoising redirection |
| **Threat model** | An attacker who can place a physical artifact in the scene, with white-box gradient access to the policy, optimises it against the **earliest step of the denoising trajectory** rather than against the emitted action or the perceptual embedding. Achieves targeted trajectory corruption at lower cost than attacking the full step window. |
| **Example attack** | DRIFT (arXiv:2608.03207), on π0 and π0.5 across four LIBERO suites |
| **Measured evidence** | **None by Provael.** DRIFT's own numbers are theirs; no Provael family targets a denoising trajectory, and no Provael run has ever loaded a flow-matching checkpoint. Proposed as not-yet-measured. |
| **Mitigations** | Unknown to us. No measured defense is claimed, by us or, as far as we have read, by anyone |
| **References** | arXiv:2608.03207 |

### Where it belongs, and why we are not deciding

The honest reading is that it does not sit cleanly anywhere, and the ambiguity is the substance of
this proposal rather than a defect in it.

**The case for EAI02 (Adversarial perception).** The delivery channel is a patch in the visual
field. Everything an operator can *do* about it — inspect the workspace, control what enters the
camera frame, constrain lighting and placement — is a perception-layer control. If the taxonomy is
organised by where a defender intervenes, this is EAI02, and the whole discussion is a footnote
under it.

**The case for EAI04 (Action-space integrity).** What is actually corrupted is the trajectory. The
attack does not make the policy *perceive* something false in any way the paper measures; it
perturbs the integration of a velocity field so the emitted action sequence goes somewhere else.
That is the EAI04 outcome — targeted trajectory redirection — reached without touching the action
head. If the taxonomy is organised by what integrity property fails, this is EAI04, and filing it
under perception describes the envelope rather than the letter.

**Why the tension is real and not a labelling quibble.** Provael already carries this exact seam.
`optimized_instruction` / `targeted_redirect` is tagged **EAI01** for its channel while its module
documents its objective as the **EAI04** threat model, and that split is annotated as an honest
cross-reference rather than resolved. DRIFT is the same shape with a different channel: EAI02 by
delivery, EAI04 by mechanism. Two entries now share a structural problem the taxonomy handles by
writing a comment, which is the argument that the taxonomy — not the comment — should change.

**The option we think is worth arguing for, without asserting it.** Name the mechanism as a
sub-class under the delivery channel (hence `EAI02.d`) and require every such sub-class to carry an
explicit *mechanism* field pointing at the integrity property it violates. That keeps a single
place to look for "what enters through the camera" while making the trajectory corruption legible,
and it generalises: AGSD's attention hijacking ([arXiv:2608.03231](https://arxiv.org/abs/2608.03231))
and FLARE's illumination channel ([arXiv:2607.14698](https://arxiv.org/abs/2607.14698)) are two
further mechanisms behind the same channel, and a channel-only taxonomy flattens all three into
"a patch, roughly".

**What would change our mind.** A demonstration that the first-step effect is an artefact of the
optimizer rather than of the ODE would remove the reason to name it at all. A demonstration that it
reproduces on an autoregressive VLA would mean it is not flow-matching-specific and belongs
somewhere else entirely. We can run neither.

### Open question — addressed to Hoseong Tae and Jong-Seok Lee

**We may have this wrong, and you are better placed than we are to say so.**

1. Is "first-step denoising redirection" a fair name for the primitive, or does it over-narrow a
   finding that is really about *gradient conflict across the integration window*, with the first
   step being where that conflict happens to vanish? The distinction matters for a taxonomy: the
   first is a place, the second is a property, and only the second would generalise to solvers with
   different step schedules.
2. Would you place it under a perception channel or an action-integrity mechanism, if forced to
   choose? We have deliberately not chosen.
3. Does the effect survive a change of solver or step count, and is there a reason to expect it on
   an autoregressive VLA? If it does not generalise, a sub-class may be premature and a note on
   EAI02 would be the right size.

**We have measured none of this and claim nothing about the answers.** Provael has never run a
flow-matching policy; see [docs/studies/index.md](studies/index.md) for that gap stated as a gap,
with a date against it. Disagreement is more useful to this list than agreement, and an issue
saying "your sub-class is wrong, here is why" is the outcome this section is filed to get. Use the
[proposal template](https://github.com/provael/provael/issues/new?template=top10_proposal.yml) or
the [dispute template](https://github.com/provael/provael/issues/new?template=top10-feedback.yml).

## Governance

Provael **maintains** the list today; the **goal is community ownership**. The list is CC-BY-SA 4.0
precisely so it can outlive any single maintainer and be forked, cited, or adopted by a neutral
body.

- **Decisions** are made in the open, on issues and PRs. The maintainer holds merge rights; the
  reviewing-contributor requirement above is the check on unilateral changes.
- **Community calls** — a public call to work through open proposals is planned. Schedule: **to be
  announced — watch this file.**
- **Attribution** — every accepted contributor is credited in `docs/top10.md`. The list credits the
  researchers it stands on.

## The v0.3 goal (and the honest current count)

The target for **v0.3** is a genuinely community-owned document: **15 named contributors from 8 or
more organizations.**

**Current count: 2 contributors (the maintainer, plus one co-author at the University of
Pennsylvania), from 2 organizations.**

That gap is the invitation. If you work on embodied-AI or VLA security — in a lab, a company, or on
your own — propose a risk, dispute one, or co-author an entry. The list gets better by being argued
with.
