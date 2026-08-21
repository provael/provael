# What "last measured" means

> The definition is written down before the badge was wired, because the badge is a claim and
> this one is easy to get wrong in three different directions at once.

The README carries a shields.io badge reading **last measured: N days ago**. This page defines what
that number counts, what it deliberately does not count, and why it reads red — correctly — on a
project that has a published measured result.

## The definition

**Last measured is the end timestamp of the most recent run that actually executed attacks against
a policy.**

Three things it is emphatically *not*:

| Not this | Why it would be wrong |
| --- | --- |
| The **generator** timestamp (`leaderboard.json`'s `generated_at`) | Rebuilding the board re-aggregates committed reports. It re-stamps a date without re-running a policy. `/leaderboard` already says so in its own words: "Re-running the generator refreshes the stamp without re-measuring anything." A badge fed by that stamp would report currency the numbers do not have — which is the exact failure the badge exists to surface. |
| The **commit** date | A docs typo would refresh it. Commits are not measurements. |
| The **release** date | Cutting a tag measures nothing. |

The distinction matters most in the case that is actually true today: the published board was
assembled on 2026-08-04 from a run measured with provael `0.1.0`. The assembly is recent. The
measurement is not. Only one of those is "last measured".

## Where the timestamp comes from

`report.json` **carries no timestamp, by design.** The determinism contract requires a report to be
a pure function of `(config, registered policy/suite/attacks)` — no wall-clock values, so the same
seed yields a byte-identical report. That is the right trade and it means a report can never be the
source for this badge.

The timestamp therefore comes from the **execution manifest** (`execution-manifest.json`), whose
whole job is runtime provenance: `started_at`, `ended_at`, hardware, accelerator, precision, and a
digest binding it to its report.

## Recorded versus reconstructed, and why the badge says which

An execution manifest is only as good as the run that wrote it. The one committed real-policy run
predates the manifest schema and its provenance was **reconstructed after the fact**, which is
visible in the artifact itself:

```
started_at      2026-06-06T00:00:00Z
ended_at        2026-06-06T00:00:00Z     <- identical to started_at, at exact midnight
commit          smolvla-libero-2026-06-06 <- a label, not a git sha
evidence_state  legacy-unverified
release_verdict incomplete
missing_fields  python_version, os, dep_lock_digest, hardware, accelerator, precision
```

A run does not start and end at the same instant, and it does not end at exactly midnight UTC. That
value is a **day-granularity reconstruction**, not a recorded timestamp, and the manifest says as
much by declaring itself `legacy-unverified` with six missing fields.

So the badge distinguishes two cases:

- **Recorded** — the manifest is not `legacy-unverified` and `ended_at` differs from `started_at`.
  The badge reports the age normally and may read green.
- **Reconstructed** — anything else. The badge reports the date but marks it, and **can never read
  green**, because green would assert a precision the artifact does not have.

## What the badge actually reads today, and why it is not amber

**Red, `isError`, "63 days ago (date reconstructed)".** Written down because the intuition when
fixing the "never" bug was that the badge *should* land on amber — and it should not.

The 10/10 result was measured on 2026-06-06. That is genuinely more than `STALE_DAYS` ago, so red is
the honest colour, and the reconstruction cap is not what produces it. Amber would require one of two
things, and both are worse than a red badge:

| To force amber | Why it is worse |
| --- | --- |
| Widen `STALE_DAYS` past 63 | A badge that cannot go stale-red until a measurement is two months old is a badge that reports nothing. The whole reason the colour is recomputed at refresh time is so it *can* redden on its own. |
| Feed it a fresher timestamp | The only fresher timestamps available are the generator run and the commit date, which is the exact substitution the definition above exists to forbid. |

So the two fixes here are narrower than "make it amber", and they are the two that were actually
wrong:

1. It said **"never"** on a project with a published measured result. That was false. Fixed.
2. It could have read **green** off a reconstructed date, asserting a precision the artifact does not
   have. Now capped: reconstructed can never be green. Amber while genuinely fresh, red once stale.

Red-because-stale is the badge doing its job. It goes amber, then green, when something is measured —
not when the thresholds are edited.

## Why it must not read "never"

"Never" is factually false. A real SmolVLA policy was driven out of its envelope on 10 of 10 seeded
trials, and that result is published, signed and reproducible. A badge reading "never" on this
project contradicts its own flagship claim, which is worse than reading a slightly imprecise date.

`never` is reserved for the genuine case: no run artifact anywhere carries a measurement.

**The test asserts the badge never says "never" while a measurement exists — NOT that it is never in
`isError`.** Those sound like the same guard and are opposites. Asserting `isError` is always false
would forbid the badge from ever reporting staleness, which is the one thing it is for; the test
would then pass forever by having disabled the feature. `test_watch.py` carries this reasoning inline
so the weaker assertion is not "tightened" later by someone reading it as an oversight.

What is forbidden is the false state. Red is a legitimate state and the badge is in it right now.

## When the number improves on its own

The freshness refresh (`.github/workflows/freshness.yml`) recomputes the age daily from committed
artifacts, whether or not anything was measured — so the badge ages by itself and does not freeze on
its last good state. The day a run lands with a genuinely recorded manifest, the badge switches from
reconstructed to recorded without anyone editing it.

## The cadence, and why it is not currently held — 21 August 2026

The badge has been red for eleven days. That warranted a decision rather than another week of
apologetic prose, and the decision was **not** to lengthen the window.

**The seven-day window is not too ambitious. It is unenforced.** The job that would hold it,
`.github/workflows/gpu-nightly.yml`, runs a real SmolVLA × LIBERO red-team on a Modal GPU nightly
and records the result into the watch ledger **only on success** — it explicitly refuses to stamp a
fresh measurement time for a run that produced no number. It is well built and it has never run,
because it is switched off in two independent ways:

| Requirement | State on 21 August 2026 |
| --- | --- |
| Repo variable `ENABLE_GPU_NIGHTLY` = `"true"` | **unset** — the repo has no variables at all, so the job no-ops in seconds |
| Secrets `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` | **absent** — the repo has `HF_TOKEN` and `PROVAEL_SIGNING_KEY` only |

Both are deliberate defaults: the workflow is gated off so that a fork, or this repo before anyone
decided to spend, can never bill. That was the right default. It also means **no cadence of any
length is currently held**, which is why the window was not moved from seven days to fourteen.
Fourteen would have been broken by the same absence, and publishing a second number nothing enforces
would have been worse than publishing the first one — it would look like a considered adjustment
rather than what it is.

### What changed instead

The **claim** moved, not the threshold. `STALE_DAYS` is still 7, because seven days genuinely is old
for a currency claim and the badge reddening at that point is correct. What was wrong was the
sentence beside it. "The newest committed measurement is older than the seven-day window this
project holds itself to" invites one inference — that a cadence slipped — and that inference is
false. `provael watch` now says the cause in the output, and names the two settings that would fix
it.

### What would close this

Configuring the two settings above. That is a maintainer action, not a code change, and nothing in
this repository can do it. Once the nightly runs, the badge refreshes on its own and the seven-day
window becomes a rule that is actually enforced rather than asserted.

The workflow's own header estimates each run at one L4 for at most an hour. **Check that figure
against current Modal pricing before enabling** — it is a comment written at authoring time, not a
measured bill, and it is the sort of number this project would not accept from anyone else without
a source.

### The shortcut that exists, and why it is not taken

By the letter of the definition at the top of this page, a run against the deterministic `stub`
policy *would* refresh the badge: the stub is a registered policy and such a run does execute
attacks against it. It takes under a second on CPU and would turn the badge green today.

It is not done, and it must not be. A stub run measures a fixture, not a policy. Turning a currency
signal green with a run that re-measured nothing is the same category of error as rebuilding the
board and calling it a measurement — the failure this page was written to prevent, wearing a
different costume. The badge stays red until a real policy is re-measured.
