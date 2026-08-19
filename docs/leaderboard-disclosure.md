# Measuring someone else's policy

This page states what Provael does **before** publishing an attack-success rate for a policy it
did not train. It is a commitment, not a courtesy, and it binds the maintainer of this project
more tightly than it binds anyone submitting to the leaderboard.

It exists because [`SAFETY.md`](https://github.com/provael/provael/blob/main/SAFETY.md) already
tells *users* of this tool to "contact the model's maintainers privately first and allow
reasonable time to respond." A project that published third-party numbers without doing that would
be breaking its own rule, and "reasonable time" was never defined. This defines it.

## The rule

**A result about a policy Provael did not train is sent to that policy's authors 14 days before it
is published.** No exceptions for convenience, deadline, or an unresponsive inbox.

The 14 days start when the notice is sent, not when it is read.

## What the authors receive, up front

Not a heads-up — the whole artifact, so the first thing they can do is check our work:

- the signed `report.json` and the leaderboard row derived from it
- the exact command, checkpoint revision, seeds, horizon, and simulator versions
- the predicate used, stated as uncalibrated where it is
- the benign control arm and its rate on the same fixture
- the draft caveat paragraph, in the wording we intend to publish

If we cannot hand over enough for them to re-run it themselves, the result is not ready to publish
to anyone.

## What happens next

**They find an error.** We re-run. If they are right, the result is corrected or withdrawn before
publication and the correction is recorded — not quietly amended.

**They disagree and we are not persuaded.** We publish both positions on the same page. Their
objection is printed in their words, not summarised into agreement.

**They do not respond.** We publish after 14 days, and the entry records that notice was given and
no response was received. Silence cannot become a veto, or the leaderboard would only ever contain
results nobody minded.

**They ask for more time with a reason.** Granted, once, and the entry says the window was
extended. A second open-ended extension is a no.

## Every entry carries the same caveats we apply to ourselves

A third-party row is published to the same standard as the SmolVLA result, which means every one of
these travels with the number:

- the transfer caveat — one policy, one suite, one predicate
- the Wilson interval, including when it is embarrassingly wide
- the benign false-positive rate on the same fixture, because a rate without its control is not a
  result
- an explicit note where the keep-out predicate is **uncalibrated**, which today is everywhere

**Nulls are published as results.** If an attack family does not transfer to a policy, that is
reported at 0/n with the same prominence as a positive rate, exactly as Provael reports its own
three measured nulls.

## What this leaderboard will not do

- **No safety ranking.** Rows are not ordered into "least safe policy". The predicate is
  uncalibrated, the suite is one suite, and a table that sorts by ASR invites a conclusion the
  measurement cannot support.
- **No unflattering framing that would not survive being applied to us.** The test before
  publishing any sentence about someone else's policy is whether we would accept it written about
  SmolVLA on our own page.
- **No result presented as a vulnerability.** These are robustness measurements on openly released
  research artifacts in simulation. Where a genuine security weakness in a specific deployed system
  turns up, `SAFETY.md`'s responsible-disclosure path applies instead, and it is not a leaderboard
  entry.

## Corrections

A published result that later proves wrong is corrected in place, with what was wrong and when it
was found stated on the entry. Results are not silently edited, and a withdrawn result leaves its
withdrawal notice behind rather than vanishing.

## Contact

Reach us at [hello@provael.com](mailto:hello@provael.com). If you maintain a policy on this board
and want a result re-run, re-checked, or removed pending review, say so and we will action it —
being on this leaderboard is not something you consented to, and the burden of getting it right is
ours.
