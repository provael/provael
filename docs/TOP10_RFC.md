# The Embodied AI Security Top 10 — RFC process (v0.2 → v0.3)

> Status: PLANNED — no results claimed. This document governs how the
> [Embodied AI Security Top 10](TOP10.md) evolves. It is about process, not measurement: every risk
> entry still stands on its own cited evidence.

The Top 10 is a **community draft, licensed CC-BY-SA 4.0**, deliberately unbranded and donatable —
[not affiliated with OWASP® or MITRE®](TOP10.md). It is currently at **v0.2**. This page is the
process for reaching **v0.3**: how to propose a new risk, dispute an existing one, and how a change
gets reviewed and merged.

## How a change happens

1. **Open an issue.** Use the
   [Top-10 proposal template](https://github.com/provael/provael/issues/new?template=top10_proposal.yml)
   to propose a new risk, or the
   [propose / dispute / fix template](https://github.com/provael/provael/issues/new?template=top10-feedback.yml)
   to dispute a ranking or fix a framework mapping. State the threat model and link the evidence.
2. **Discuss in the open.** Discussion happens on the issue and in the **Top-10 RFC**
   [discussion category](COMMUNITY.md). The bar is a concrete, adversarially-reachable threat with
   at least one referenceable source (arXiv, CVE, advisory, or a reproducible attack).
3. **Review.** A change is reviewed by the maintainer **and** at least one contributor from a
   different organization (see the goal below). Review checks the threat model, the evidence, the
   cross-framework mapping (MITRE ATLAS / NIST / ISO), and that the change does not overstate what
   is measured.
4. **Versioned merge.** An accepted change lands in `docs/TOP10.md` with the version bumped and a
   dated line recording what changed. No silent edits: a risk enters, moves, or leaves the list
   only through a merged PR that says why.

A small, concrete fix (a broken mapping, a typo, a clarified sentence) can skip straight to a PR
editing `docs/TOP10.md` — the issue step is for anything that changes the *set* or the *ranking*.

## Entry template

Every risk on the list carries these fields; a proposal for a new one should fill them in:

- **ID** — the proposed `EAIxx` id, or "renumber" if you are re-ordering existing risks.
- **Title** — a short, specific name (e.g. "Indirect / embodied prompt injection").
- **Threat model** — who the attacker is, what they control, and what they achieve. Must be
  **adversarial** and **embodiment-relevant** (see the [Top-10 scope note](TOP10.md)).
- **Example attack** — one concrete, referenceable instance. A Provael attack family is ideal but
  not required; a published paper or a real advisory also counts.
- **Measured evidence** — what has actually been measured, and where. If nothing has been measured
  yet, say so: a risk can be listed on threat-model grounds and marked not-yet-measured, but it is
  never dressed up as a result.
- **Mitigations** — the known defenses, and whether any is measured (see [DEFENSES.md](DEFENSES.md)).
- **References** — the arXiv / CVE / advisory / standard clauses that back the entry.

## Governance

Provael **maintains** the list today; the **goal is community ownership**. The list is CC-BY-SA 4.0
precisely so it can outlive any single maintainer and be forked, cited, or adopted by a neutral
body.

- **Decisions** are made in the open, on issues and PRs. The maintainer holds merge rights; the
  reviewing-contributor requirement above is the check on unilateral changes.
- **Community calls** — a public call to work through open proposals is planned. Schedule: **to be
  announced — watch this file.**
- **Attribution** — every accepted contributor is credited in `docs/TOP10.md`. The list credits the
  researchers it stands on.

## The v0.3 goal (and the honest current count)

The target for **v0.3** is a genuinely community-owned document: **15 named contributors from 8 or
more organizations.**

**Current count: 1 contributor (the maintainer), from 1 organization.**

That gap is the invitation. If you work on embodied-AI or VLA security — in a lab, a company, or on
your own — propose a risk, dispute one, or co-author an entry. The list gets better by being argued
with.
