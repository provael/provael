# `watch/` — the consumption surface

Generated artifacts that let a consumer **derive** a fact about this project instead of keeping its
own copy. Every file here is written by a script and gated by `make check-docs`; none is hand-edited,
and that is the point — the failure this directory exists to prevent is a downstream copy going
stale while everything around it stays green.

The incident that produced it: on 6 September 2026, fourteen pages of www.provael.com rendered
v0.39.3 against a repo, tag, GitHub release and PyPI all at 0.39.4. Nothing was broken; a human had
simply not re-typed a number.

| file | answers | written by |
| --- | --- | --- |
| `registry.json` | how many attacks, families, policies and suites are registered, how many of each are runnable rather than scaffolding, how many adversarial families have met a real policy (`realPolicyTested`), and how many distinct real policies have a committed applicable adversarial episode (`realPoliciesTested`, with the names) | `scripts/gen_registry_artifact.py` |
| `release.json` | which version is current, its tag, its PyPI string, and the project's release-drift window | `scripts/gen_release_artifact.py` |
| `measurements.json` | one row per committed measurement: when, on what version, with what result, and whether it counts | `scripts/gen_measurement_ledger.py` |
| `freshness.json` | when **anything** was last measured, as a shields.io badge | `provael watch` |
| `publish-freshness.json` | how far the **published** measurement has drifted from the current release, and which newer body is nearest to replacing it | `scripts/gen_publish_freshness_artifact.py` |
| `campaign.json` | how far the scheduled re-measurement campaign has got: its plan, its pinned release, the attempts it has to exceed, what is banked, and the completion its cadence projects | `scripts/gen_campaign_progress.py` |
| `coverage.json` | the test-coverage badge | `.github/workflows/coverage-badge.yml` |

## The two freshness files answer different questions

This is worth stating because they disagree today, and both are right.

`freshness.json` asks **when was anything last measured**. A one-episode timing probe satisfies it.
On 8 September 2026 a $0.06 probe put that badge at `today`.

`publish-freshness.json` asks **whether the number a reader is shown was measured against code that
still exists**. The same day, it said the published 44/50 headline was measured with v0.32.0, nine
minor releases back, past this project's own two-release window. A probe cannot move it: the version
it reports is the one behind the published *body* of measurement, not the newest record.

A green `freshness.json` therefore does **not** mean the headline is current. Read both.

## What displaces the published measurement, and how far along the replacement is

The rule is `provael.watch.displacement`, and it is stricter than the size-only rule it replaced.
A **body** is every real, recorded run at one lineage and one tool version, where a lineage is the
policy, the suite and, where the task ids carry one, the task suite (`smolvla` x `libero` x
`libero_object`; the artifact calls it `taskSuite`). A body **supersedes** the published one only by
re-measuring what it measured: the same lineage, every task it covered, with at least as many
attempts (a tie goes to the newer version). A probe cannot displace a campaign; neither can a longer
run on fewer tasks, which the old rule allowed; and a run on another LIBERO task suite is another
measurement altogether, the way the adapter already treats it ("one run is one suite"), so a Spatial
null does not join the Object body or raise the bar for re-measuring it.

Bodies are one version each on purpose. `provael.combine` refuses to pool shards whose tool version
differs, because a rate over two builds describes a run that never happened, so a body pooled across
releases would be a number no evidence manifest can be built over and no site can re-pin. What
accumulates is a campaign at one pinned release, and the scheduled lane holds its pin until that
campaign supersedes the published body (`examples/gpu-ci/modal_provael_gpu.py`).

`publish-freshness.json` therefore carries two more blocks:

- `published`: the body behind `measuredWith`: its attempts, its runs, and the tasks it covered.
- `challenger`: the newer body at the same lineage nearest to superseding it, with
  `attemptsNeeded` and `tasksMissing` stating exactly what it still lacks. `null` when nothing newer
  has been measured, which is not the same as a deficit of zero.

Before these existed a reader could see that the published measurement was nine minors old and that
a GPU lane ran twice a week, and had no way to learn that the lane was accumulating fourteen attempts
a run on one task toward a body of five hundred and fifty over ten, in a version bucket that reset on
every release. `provael doctor` prints the same as a `re-measurement` row.

`measurements.json` rows carry `tasks` for the same reason: a fourteen-attempt canary and a
ten-shard campaign are not the same kind of row, and a reader should not have to open either report
to tell them apart.

## What a ledger row carries, since 0.43.0

Each row now names what a consumer used to have to re-derive from the run — and re-derived
differently in different places: the checkpoint (`model`), the adversarial numerator and
denominator (`adversarialSuccesses` / `adversarialAttempts`) and the benign control's
(`benignSuccesses` / `benignAttempts`), so nobody divides the all-episode `asr` again; the
predicate (`calibrated`) and `evidenceState`; `intervalMethod`, which is the episode-level Wilson
score for every per-run interval (a sharded run's task-clustered interval lives in its
`aggregate.json` under its own name and is a different estimate); and `published` — whether the
row belongs to the body behind the published headline, by the same `displacement` rule
`publish-freshness.json` applies. `publishedLineage` at the top says which body that is. A row
that is newer than the published body and not in it says `published: false`, which is the
distinction between "the newest number" and "the number a reader is shown".

## Four dates, kept apart

A reader asking "how old is this number" is asking one of four different questions, and this
directory answers each with a different field rather than a blended one:

| date | where it lives | what it dates |
| --- | --- | --- |
| execution date | `measurements.json` → `measuredAt` (the manifest's `ended_at`) | when the run finished measuring |
| tool release date | `CHANGELOG.md` (the `[x.y.z] — date` heading); `release.json` names the version, not the day | when the code that measured it was released |
| assembly commit | the commit a consumer pins (`repo-facts.json` upstream, `evidence-manifest.json`'s `commit`) | the repository state a number was read from |
| source-review date | beside the claim it reviewed (a "verified 12 September 2026" in the docs, a `_AS_OF` in the site) | when a human last checked an outside source |

None of these is written from this directory's wall clock. The August and September runs stay
separate rows with their own execution dates; nothing here averages them into one.

## The campaign, and what `campaign.json` says about it

The scheduled lane no longer probes; it measures the next shards of a declared campaign
(`studies/scheduled_campaign/plan.json`: the published body's checkpoint, suite, ten tasks and
horizon, every arm it ran plus the harmless-variation controls, eight seeds) at one held release, and
`watch/campaign.json` publishes where that stands:

- `plan`: the shape and size of the grid, and `shardsTotal`.
- `toolVersion`: the release the campaign is pinned at (read from the lane's own `PROVAEL_PIN`).
- `target.attemptsToDisplace` and `target.publishedWith`: the body it has to exceed, from the same
  rule `publish-freshness.json` applies.
- `banked`: attempts and shards committed so far, and the newest shard's `ended_at`.
- `cadence`: the workflow's own cron, as runs per week, and shards per run.
- `projected.completion`: the newest shard's date plus the runs still needed at that cadence. Null
  until the first shard lands; before that the only anchor would be the clock, and no file here
  carries a wall-clock value.

This is the field a page can render in place of a flat STALE banner: a re-measurement in progress,
with a denominator. It is not a rate, and it does not become one; the rate lives in the shards and in
the campaign's own combined view, `results/gpu-scheduled/campaign-<version>/campaign.json`, which
is written continuously and says `complete: false` in its own words until every planned shard is
present. That combined view is never `report.json` and never a ledger row: a combined view has no
single execution behind it, so the rows stay the shards, exactly as the 0.32.0 and 0.41.2 campaigns
are recorded.

## Two properties every file here holds

**No wall-clock values.** Each artifact is a pure function of committed inputs, so re-generating on
an unchanged tree is a no-op and `--check` means "this is current" rather than "this was written a
moment ago". A `generatedAt` field would make every gate fail on a clean checkout.

**No unverifiable fields.** `release.json` carries no commit sha and no `published_at`, because the
script that writes it runs offline and could only guess. A consumer cannot tell a guess from a fact,
and the whole point of this directory is that nobody types these values.

## Where a duplicate constant is safe, and where it is not

`staleAfterReleases` appears in both `release.json` and `publish-freshness.json`. That is safe: both
render from `provael.watch.STALE_AFTER_RELEASES` and both are gated by `make check-docs`, so a
change that misses one fails the build.

The same constant living in *another repository* was not safe, and was the bug. www.provael.com held
its own `STALE_AFTER_RELEASES = 2` in `src/lib/freshness.ts` with no shared source — the site could
not see the CLI's copy and the CLI could not see the site's, so a drift would have shown a reader one
window and `provael doctor` another with nothing failing anywhere. Fixed in 0.41.1 by publishing it
here.
