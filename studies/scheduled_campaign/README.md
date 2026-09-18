# The scheduled campaign

`plan.json` is the grid the scheduled GPU lane (`.github/workflows/gpu-scheduled.yml`) measures,
one shard per run slot, at one held release, until the completed campaign displaces the published
measurement on its own.

## Why it exists

The published measurement is the largest body of real runs at one lineage (policy, suite and task
suite) and one version that nothing supersedes (`provael.watch.displacement`). On 18 September 2026 that body was 550 attempts
over ten `libero_object` tasks at v0.32.0, nine minor releases back. The lane meant to refresh it
measured one task, eight arms and two seeds twice a week: fourteen attempts a run, under a version
that changed every time a release re-pinned it. It measured on the current release twice a week and
could not have displaced the published campaign this decade.

## What the plan declares

| field | value | why |
| --- | --- | --- |
| `policy`, `model`, `suite` | `smolvla`, `HuggingFaceVLA/smolvla_libero`, `libero` | the published body's own |
| `tasks` | the ten `libero_object` tasks | the published body's own; a re-measurement must cover them |
| `attacks` | `none,instruction,visual,injection,control` | every arm the published body ran, plus the harmless-variation controls registered since |
| `seeds` | 6 | one more than the published body, so the completed campaign exceeds 550 attempts rather than tying |
| `horizon` | 280 | the published body's own |
| `shardsPerRun` | 5 | the budget line: the per-run ceiling times the cadence fits the $30/month credit |
| `modelledOn` | v0.32.0, its two shard directories | where every statement above is checked against |

`tests/test_campaign.py` reads the 0.32.0 shards the plan names and holds each row of that table to
them; a plan that drifted from the published body's shape would fail the suite.

## How it runs

A **shard** is one (task, seed) cell with every arm: twelve episodes, about thirty minutes on an L4
including container start, inside a 45-minute container timeout. `provael.campaign.next_shards`
picks the next un-run shards, seed-major, from what is committed under
`results/gpu-scheduled/campaign-<version>/`. A missed run costs a week and not correctness; a re-run
of a slot that already landed selects the shards after it. Each shard is recorded only if its
execution manifest carries `repository`, `commit`, `dep_lock_digest` and `precision`
(`scripts/check_provenance.py`); the shards are then combined into `campaign.json` beside them
(`scripts/combine_campaign.py`), and `watch/campaign.json` publishes how far along the campaign is.

Sixty shards at five a run is twelve runs, six weeks, about $24 at the measured rate.

## What it cannot do

Between v0.32.0 (8 August 2026) and v0.41.2 (9 September 2026) nine minor releases shipped in
thirty-two days. At that cadence the campaign that displaces the published measurement completes
about a dozen minors behind the current release, past the two-release window it is measured
against. The lane makes the published measurement move; it cannot make it current. What would: a
slower release cadence while a campaign runs, or a larger credit.

## Pre-registration

The commit that added `plan.json` is the date the grid was fixed. Nothing in it is a result.
