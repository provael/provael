# Findings

A **finding** is a result measured on a real policy — a real checkpoint, a real simulator, a
recorded seed — and written up with its denominator, its interval and its controls. Anything that
has not been run against a real policy is not here; it is in
[Studies](../studies/index.md), labelled pre-registered.

The distinction is the point. A pre-registered study states what will be measured *before* it is
measured, so a null result cannot be quietly reframed after the fact. A finding reports what came
back, including when nothing did.

## Measured on a real policy

| Finding | What was measured |
| --- | --- |
| [A benign instruction transfers to a real VLA policy — SmolVLA×LIBERO](2026-instruction-transfer.md) | The flagship instruction-family transfer result |
| [Cross-architecture transfer of templated attacks](2026-cross-arch-transfer.md) | Whether an attack templated against one architecture carries to another |

## Measured defenses

Defenses are held to the same evidential bar as attacks — a defense that is only *specified* is
labelled as such and never counted as measured risk reduction. The two that have been measured:

- [Instruction canonicalization](../studies/instruction-canonicalization.md)
- [Action envelope](../studies/action-envelope.md)

And one further measured transfer study:

- [EAI04 action-space-integrity transfer](../studies/eai04-action-space-transfer.md)

## Reading these honestly

Every finding here carries its own scope limits in-band. Before quoting a number from one of these
pages, read the limits section on that page: the denominators are small, the controls are named,
and the gaps are stated rather than omitted. If a page does not say what it did not measure, that
is a defect in the page — please open an issue.
