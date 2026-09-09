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
| `registry.json` | how many attacks, families, policies and suites are registered, and how many of each are runnable rather than scaffolding | `scripts/gen_registry_artifact.py` |
| `release.json` | which version is current, its tag, its PyPI string, and the project's release-drift window | `scripts/gen_release_artifact.py` |
| `measurements.json` | one row per committed measurement: when, on what version, with what result, and whether it counts | `scripts/gen_measurement_ledger.py` |
| `freshness.json` | when **anything** was last measured, as a shields.io badge | `provael watch` |
| `publish-freshness.json` | how far the **published** measurement has drifted from the current release | `scripts/gen_publish_freshness_artifact.py` |
| `coverage.json` | the test-coverage badge | `.github/workflows/coverage-badge.yml` |

## The two freshness files answer different questions

This is worth stating because they disagree today, and both are right.

`freshness.json` asks **when was anything last measured**. A one-episode timing probe satisfies it.
On 8 September 2026 a $0.06 probe put that badge at `today`.

`publish-freshness.json` asks **whether the number a reader is shown was measured against code that
still exists**. The same day, it said the published 44/50 headline was measured with v0.32.0, nine
minor releases back, past this project's own two-release window. A probe cannot move it: the version
it reports is the one behind the *largest* real campaign, not the newest record.

A green `freshness.json` therefore does **not** mean the headline is current. Read both.

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
