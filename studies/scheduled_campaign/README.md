# The scheduled campaign

`plan.json` is the grid the scheduled GPU lane (`.github/workflows/gpu-scheduled.yml`) measures,
one shard per run slot, at one held release, until the completed campaign displaces the published
measurement on its own.

## Why it exists

The published measurement is the largest body of real runs at one lineage (policy, suite and task
suite) and one version that nothing supersedes (`provael.watch.displacement`). On the morning of
18 September 2026 that body was 550 attempts over ten `libero_object` tasks at v0.32.0, nine minor
releases back. The lane meant to refresh it measured one task, eight arms and two seeds twice a
week: fourteen attempts a run, under a version that changed every time a release re-pinned it. It
measured on the current release twice a week and could not have displaced the published campaign
this decade.

Later that day the workstation's runs of 14 September landed (`results/*_2026-09-14`) and the
published body became the 0.41.2 Object body: 656 attempts over the same ten tasks, from the
ten-task suite, its control run, the breadth probe, the clip and the canary. The plan was
re-modelled on it before any shard ran; the Spatial, Goal and LIBERO-10 runs of the same night are
their own lineages and are not part of the bar (`Campaign.task_suite`).

## What the plan declares

| field | value | why |
| --- | --- | --- |
| `policy`, `model`, `suite` | `smolvla`, `HuggingFaceVLA/smolvla_libero`, `libero` | the published body's own |
| `tasks` | the ten `libero_object` tasks | the published body's own; a re-measurement must cover them |
| `attacks` | `none,instruction,visual,injection,control` | every arm the published body ran, plus the harmless-variation controls registered since |
| `seeds` | 8 | 880 planned attempts at the incumbent's own not-applicable rate (`mcp_tool_desc` never applies to SmolVLA), against a published body of 656 — the margin is for the 0.41.2 runs still to land from the workstation, since a body that grows past the plan makes the lane a probe again |
| `horizon` | 280 | the published body's own |
| `shardsPerRun` | 5 | the budget line: the per-run ceiling times the cadence fits the $30/month credit |
| `modelledOn` | v0.41.2, the suite's and the control run's shard directories | where every statement above is checked against |

`tests/test_campaign.py` reads the 0.41.2 shards the plan names and holds each row of that table to
them; a plan that drifted from the published body's shape would fail the suite, and so does a
results PR that grows the published body past the plan's attempts — the remedy is a seed bump in
the same PR, dated in this file's history.

## How it runs

A **shard** is one (task, seed) cell with every arm: twelve episodes, about thirty minutes on an L4
including container start, inside a 45-minute container timeout. `provael.campaign.next_shards`
picks the next un-run shards, seed-major, from what is committed under
`results/gpu-scheduled/campaign-<version>/`. A missed run costs a week and not correctness; a re-run
of a slot that already landed selects the shards after it. Each shard is recorded only if its
execution manifest carries `repository`, `commit`, `dep_lock_digest` and `precision`
(`scripts/check_provenance.py`); the shards are then combined into `campaign.json` beside them
(`scripts/combine_campaign.py`), and `watch/campaign.json` publishes how far along the campaign is.

Eighty shards at five a run is sixteen runs, eight weeks, about $32 at the measured rate.

## What it cannot do

Between v0.32.0 (8 August 2026) and v0.41.2 (9 September 2026) nine minor releases shipped in
thirty-two days. At that cadence the campaign that displaces the published measurement completes
a dozen or more minors behind the current release, past the two-release window it is measured
against. The lane makes the published measurement move; it cannot make it current. What would: a
slower release cadence while a campaign runs, or a larger credit.

## Pre-registration

The commit that added `plan.json` is the date the grid was fixed. Nothing in it is a result.
