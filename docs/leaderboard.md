# The public ASR leaderboard

> **Evidence, not certification.** The leaderboard reports measured Attack Success Rates in
> simulation. It is not a safety rating and not a conformity statement.

The [leaderboard](https://huggingface.co/spaces/Sattyam/provael-leaderboard) aggregates
`(policy × suite × family) → ASR` results into a ranked, reproducible, signable board. Lower ASR is
more robust.

Not every row is submitted by the policy's own authors. Where Provael measures a policy it did not
train, the authors get the full artifact **14 days before publication** — see
[Measuring someone else's policy](leaderboard-disclosure.md). That rule binds this project, not
just the people submitting to it.

## What each row carries

Every row is honest about how strong its number is:

- **ASR with a 95% Wilson CI** — the point estimate never travels without its interval.
- **The benign (`none`) control** — the baseline family's rate for that policy × suite, so you read
  lift, not a bare number.
- **A transfer-status label** — `real-transfer` (a real policy in a real simulator) or
  `stub-scaffolding` (the deterministic CPU stub, or a real policy on the stub suite). When any real
  run is present the board is not a demo, and stub and real rows are **never silently mixed** — each
  is labelled.

## The first real result

On the real **SmolVLA × LIBERO** policy, only the **instruction** family transfers today
(roleplay 100%, goal_substitution 60%, paraphrase 10%); **visual and injection attacks are 0%** on
the real model, against a 0% benign control. That honesty is the point: the board shows what does
and does not transfer, with intervals, rather than a single headline number.

## What the published board does *not* cover

The board is one run, and it is old. Stated plainly, because the rendered page now states it too:

- **Measured with `provael 0.1.0`.** Every row on the published board came from that release. The
  build stamp is current; the measurement is not. See [re-stamps](#what-a-re-stamp-does-and-does-not-change).
- **1 policy, 1 suite.** `smolvla` × `libero_object/0`. Seven of the eight registered policy
  backends have never produced a board row, and three of those (`groot`, `openvla`, `openpi`) have
  never loaded a checkpoint at all — `provael list-policies` marks them `scaffolding`.
- **3 of 17 adversarial families measured** (`instruction`, `injection`, `visual`). **The other
  twelve have no real-model measurement whatsoever.** They are *absent* from the board, which is
  not the same as scoring 0% — an absent family is `N/A`, and reading it as a pass is the single
  most likely way to misuse this page.
- **No clean-task-success control.** The underlying run predates `clean_task_success_rate`, so the
  board shows no measured evidence that the policy completes its benign task unattacked. The
  benign false-positive control *is* present and is 0%. The competence control is not, and is not
  back-filled — see the run's own
  [provenance note](https://github.com/provael/provael/blob/main/results/smolvla_libero_object/README.md).

Closing these needs GPU time, not a rebuild: a re-stamp cannot add a family it never ran.

## Third-party submissions: 0

**Every row on this board was produced by the maintainer.** All four carry
`provenance: maintainer-run` and `submitted_by: provael`. Nobody outside the project has reproduced
or submitted a result.

This is stated the same way [`results/hardware/README.md`](https://github.com/provael/provael/tree/main/results/hardware)
states **0** hardware runs, and for the same reason: a board that does not distinguish self-reported
rows from external ones is a changelog of our own runs wearing the word "leaderboard". Four rows from
one maintainer and four rows from four independent labs are identical in every other column.

The count renders on the board itself — an `Independence` line above the table, and a **`provenance`
column per row** so a single external entry is visible in place rather than only in an aggregate. The
day a third-party row lands, both change without anyone editing this page.

**The submission path is exercised, not just documented.** Verified end to end on 12 August 2026
against a dummy submission, which was then deleted:

| step | command | result |
| --- | --- | --- |
| 1. run | `provael attack --policy stub --suite stub …` | `report.json` written |
| 2. validate | `python scripts/validate_submission.py <dir>` | `all submissions valid (1 report(s) checked)` |
| 3. build | `provael leaderboard build --runs … --submitted-by dummy-tester --provenance third-party-submission` | rows carry both fields |
| 4. promote | `provael leaderboard build --real <stub dir>` | **correctly refused** — "no real (non-stub) runs found" |

Step 4 failing is the guard working: a stub run cannot reach the public real board. A submission
process nobody has executed is a process that does not work, so this was run rather than assumed.

## Provenance and reproducibility

A real board is stamped with a **UTC build date**, the **source commit**, and a **SHA-256 digest of
the aggregated input reports** (the same digest approach as [attestation](attestation.md), so a board
and an attestation speak one integrity language). The date and commit are a snapshot stamp; the
`inputs_digest` and the row numbers are what reproduce.

The source directory is named beside the board, in **`leaderboard/results/source.json`** (`run`),
and that pointer is the one place to read it from: it is written by the same workflow that writes
the board, and `tests/test_leaderboard_version_claim.py` holds its `measuredWith` and `generatedAt`
to the board's own fields. It names a ten-task suite directory, not
`results/smolvla_libero_object`, which is an older single-task run measured with **0.1.0**;
rebuilding from that one produces a different digest, different rows, and a board thirty-odd minor
versions behind the published one. Several such directories are committed and their names differ
by a word or a date, which is why the pointer exists rather than leaving it to be inferred.

```bash
# Which run the committed board aggregates
run="$(python -c "import json; print(json.load(open('leaderboard/results/source.json'))['run'])")"

# Build the real board (stamps date + commit + inputs digest)
provael leaderboard build --real "$run" --out leaderboard/results

# Reproduce: rebuild and confirm the digest matches
provael leaderboard build --real "$run" --out /tmp/rebuild
python -c "import json; a=json.load(open('leaderboard/results/leaderboard.json'))['inputs_digest']; \
b=json.load(open('/tmp/rebuild/leaderboard.json'))['inputs_digest']; print('match:', a==b)"
```

Two dispatch-only workflows move the committed board, and they are different acts on purpose.
`leaderboard-restamp.yml` re-aggregates the **same** run and refuses a result whose `measured_with`
moved — it exists so a release tag never trips the stamp-lag gate, and it must not be able to
launder staleness. `leaderboard-rebuild.yml` takes a **named** committed run as its input and
expects `measured_with` to move with it; it refuses a run that is not a committed results directory,
a board whose `measured_with` is not what that run's shards say, a source older than the current
one, a board that drops a (policy, suite) or its attribution, and a signature that does not verify
against the published `leaderboard.pub`. Both sign with the key that lives only in the repository
secret, so the key reaches no workstation. The rebuild commits to the ref it was dispatched on, so
it is run on a branch and merged with the prose that has to move with the board.

## What a re-stamp does and does not change

A board is rebuilt by **aggregating committed `report.json` files** — it does not re-run a policy.
So re-running the generator moves `generated_at` and `commit` to today while **every row still
carries the measurement it always did**, possibly made by a much older release.

That is a trap: a board carrying only `generated_at` reads as a fresh measurement. Schema v3 adds
**`measured_with`** — the sorted `tool_version` values of the aggregated reports, i.e. the versions
the *numbers* came from — and `Leaderboard.is_restamp()` answers the question directly. The
published board reports `measured_with: ["0.41.2"]` against a build commit from the current release
line: the provenance envelope is current, the measurement is the ten-task SmolVLA × LIBERO suite
screen those shards recorded on 14 September 2026 (until 18 September 2026 it read `["0.32.0"]`,
the run of 9 August, which the re-run reproduced).

### Staleness is a field, not a banner (schema v6)

`measured_with` and `is_restamp()` let a reader work it out. **A consumer should not have to.** The
published board carried four rates, an Ed25519 signature, and nothing machine-readable saying the
signature vouches for a *measurement* rather than for its *currency* — a distinction that only
lived in prose the Space renders. So v6 records the verdict:

| field | what it is |
| --- | --- |
| `tool_version` | the version that **assembled** the board — distinct from `measured_with`, which is what **measured** the rows. The gap between them is the staleness. |
| `stale` | `true` when some row is more than `MAX_MINOR_LAG` (1) minor versions behind. `null` when it cannot be determined — never `false` by default. |
| `stale_reason` | why, naming both versions, so the verdict is re-derivable from its own text. |

The lag is counted on `(major, minor)` and ignores the patch, because a patch by definition changes
no measured behaviour. Across a major bump it is not a subtraction: 0.40 → 1.0 is one release, not
minus thirty-nine, so a differing major reports "too far" rather than a negative number that would
read as fresh.

**`stale` sits outside the signature, on purpose.** Staleness is a function of today, not of the
board: a board that was current when signed becomes stale without a byte changing. Inside the
signed subject it would need either a signature re-issued as time passes, or a flag frozen at a
value that was true once. Being registered in `_FIELDS_ADDED_IN[6]` means it is stripped from the
signing payload of any board declaring an earlier schema — which is exactly what lets the
already-signed v5 board be annotated with `stale: true` and still verify against the committed
public key.

The verdict is also **monotone**: a row's measured version never changes and the release only moves
forward, so a `true` can never become wrong. Only a `false` can decay, and
`scripts/check_leaderboard_staleness.py` re-checks that single direction in CI. It fails on
**undeclared** staleness only — a board past the limit that does not say so. Failing on staleness
itself would be red until a GPU re-run nobody has scheduled, and a permanently-red detector reports
nothing. Disclosed staleness is the honest state; silent staleness is the bug.

## Qualifiers travel with the row (schema v5)

A leaderboard is where a number travels furthest from its own report, and until v5 it arrived
stripped: `report.json` recorded `calibrated` and `stochastic`, and the board dropped both. A row
reading `33.3%` with no further context is a stronger claim than the run behind it ever made.

Each row now carries three fields derived from the aggregated reports — never passed in, for the
same reason `measured_with` is not:

| field | reduction | why that direction |
| --- | --- | --- |
| `calibrated` | ALL | one uncalibrated run makes the row uncalibrated |
| `stochastic` | ANY | one unseeded sampler makes the row one draw |
| `checkpoint` | unanimous, else `None` | naming one of several would attribute the rate to a checkpoint that did not wholly earn it |

Each collapses toward the *weaker* claim on purpose: the reduction step is exactly where an
aggregate is tempted to launder a qualifier.

The board also carries **`not_applicable`** — attacks with episode records but zero applicable
episodes. Scoring excludes them from every denominator, so without the list they vanish entirely
and a reader counts one fewer null than was attempted. On the published board that is
`mcp_tool_desc`: 50 records, 0 applicable. *Not measured* and *measured zero* are different claims.

**Adding these fields did not invalidate older signatures.** `_signing_payload` strips fields
introduced after a board's own `schema_version` before canonicalising, so a v4 board still verifies
against its v4 signature under the v5 model. Without that, adding any defaulted field would have
silently broken every signature ever issued — and a correctly-signed older board would verify as
INVALID, indistinguishable to the checker from a tampered one.

Recording that in the JSON was only half the fix. Until 0.29.1 the *rendered* Space showed a fresh
build date and an Ed25519 signature above rows measured many releases earlier, with nothing on the
page saying so — and a signature over stale data is worse than no signature, because it reads as
currency. The app in this repo (`leaderboard/app.py`) derives a staleness-and-coverage banner from
`measured_with` and the rows themselves, and places it above the tables rather than below them.

The [published Space](https://huggingface.co/spaces/Sattyam/provael-leaderboard) is a **mirror of
this repo's `leaderboard/` directory with its own deploy state**, and for a month it was the
untreated version of the paragraph above: last deployed 30 June 2026, it served a schema-v1 board
with `signature: null` and no `measured_with` — and no banner, because the app that renders the
banner had never reached it. Space deployment is now driven from this repo whenever `leaderboard/`
changes (see `.github/workflows/leaderboard-submission.yml`), and that path has now been **verified
live**: the deployed Space serves the same `schema_version` 5 board this repo signed, same rows,
same `keyid 8d62aa33ed5162f3`. This paragraph had been holding a softened claim until that check
passed rather than after it. Two practical notes: **the canonical, signed board is the one
committed in this repo** —
verify that one, not a rendering of it — and the Space runs on the free tier, so it sleeps when
idle and the first visitor after a quiet period waits through a cold start rather than getting an
instant page.

## Signing and offline verification

The published board is **Ed25519-signed** (via the `provael[attest]` extra). The
signature covers the whole board except the signature field, and verifies offline with no network.

**Verify the published board in two commands** — no network, no trust in this page:

```bash
pip install "provael[attest]"
curl -fsSLO https://raw.githubusercontent.com/provael/provael/main/leaderboard/results/leaderboard.json
curl -fsSLO https://raw.githubusercontent.com/provael/provael/main/leaderboard/results/leaderboard.pub
provael leaderboard verify --in leaderboard.json --pubkey leaderboard.pub
# -> leaderboard OK  keyid 8d62aa33ed5162f3
```

A non-zero exit and `leaderboard signature INVALID` is the answer you should get if anything in the
board was altered — including a single success count. That is the point: the numbers are covered by
the signature, not merely published alongside it.

The public key lives at **`leaderboard/results/leaderboard.pub`** (keyid `8d62aa33ed5162f3`) and is
the only key the published board is signed with. The keyid shown above is not typed into this page
— `scripts/render_keyid.py` derives it from that key file, and a repo-wide test fails the build on
any keyid the key does not derive to (the id printed here was wrong for four days after the #74 key
rotation; see the [errata register](errata.md)). CI enforces four things so this cannot rot: the
board is signed, the signature verifies **against that published key**, every documented keyid is
derived from the key file, and the board's stamp lags the newest released tag by at most **14
days** — re-stamping is a GPU-free one-command operation, so the cost of staying current is low.

Rebuild and re-sign:

```bash
provael leaderboard build --real results/smolvla_libero_object_suite --sign --key provael-ed25519.pem \
    --out leaderboard/results
provael leaderboard verify --in leaderboard/results/leaderboard.json --pubkey leaderboard.pub
```

Signing with an omitted `--key` uses an ephemeral key (integrity, not identity) and writes the
public half next to the board.

## Open-core

The CLI builds and verifies boards for anyone, free and Apache-2.0. The **hosted board** — signed
with Provael's published project key and backed by real-VLA (GPU) runs rather than the stub — is
the paid surface. Submitting a result is a pull request; see
[CONTRIBUTING-leaderboard.md](https://github.com/provael/provael/blob/main/CONTRIBUTING-leaderboard.md).

## The board, as the README described it

> *Moved here from the repository README on 20 September 2026, when the README was cut to what a new reader needs. The text is as it stood there; links were re-pointed.*


`provael leaderboard build --real <results-dir>` builds the public board from real-model runs. Every
row carries its **95% Wilson CI**, the benign (`none`) control, and a **transfer-status** label
(`real-transfer` vs `stub-scaffolding`), so a stub run is never silently mixed with a real one. The
board is stamped with a UTC date, the source commit, and a **SHA-256 digest of the aggregated
inputs** — rebuild it and check the digest matches to reproduce. Add `--sign` (needs the
`provael[attest]` extra) to Ed25519-sign it, and verify offline:

```bash
uv run provael leaderboard verify --in leaderboard/results/leaderboard.json \
  --pubkey leaderboard/results/leaderboard.pub   # -> leaderboard OK  keyid 8d62aa33ed5162f3
```

The published board is the **ten-task `libero_object` suite screen**: on the real
**SmolVLA × LIBERO** policy only the **instruction** family transfers, at **41.3% (62/150)
[34–49%]** against a **4.0% (2/50, Wilson 95% [1.1%, 13.5%])** benign control; **injection is 0/50 and visual 0/100** —
measured nulls, published as such.

Since `schema_version` 5 each row also carries the qualifiers its report always had —
`calibrated` (false here: the keep-out predicate is the default box, see
[#136](https://github.com/provael/provael/issues/136)), `stochastic` (true: one draw, not a
reproducible constant — these rows predate `policy_seed`), and `checkpoint` — plus a board-level
`not_applicable`
(`mcp_tool_desc`, which produced records but zero applicable episodes). A rate that outlives its
qualifiers is the overclaim this board exists not to make, and the board was the one artifact
where they were being dropped.

The board is also **live as a Hugging Face Space** —
[huggingface.co/spaces/Sattyam/provael-leaderboard](https://huggingface.co/spaces/Sattyam/provael-leaderboard)
— rendering the same signed `leaderboard.json` this repo commits, with an open submission queue.
The Space is a *rendering*; the canonical artifact is the signed JSON in this repository, so verify
that one rather than a view of it.

The free core builds and verifies boards; a hosted, operator-signed board is the intended operated
surface (experimental today). See [docs/leaderboard.md](leaderboard.md).
**Evidence, not certification.**

**What the published board does not cover.** It is one run: measured with
**`provael 0.41.2`** on 14 September 2026 (`results/smolvla_libero_object_suite_2026-09-14`, the
directory named in `leaderboard/results/source.json`), covering **1 policy on 1 suite** and **3 of
the 17 adversarial families**. The other **fourteen families are absent from the board**, which is
not the same as scoring 0%: nine of them have no real-model measurement anywhere in this repository,
and five have only the three-episode breadth probe of the same night
(`results/smolvla_libero_object_families_2026-09-14`), a result and not a rate. The run carries a
benign false-positive control (1/50) and a clean-task-success baseline (48/50), so its rates are
read against a measured competence, not assumed one. The Space states all of this above its own
tables; rebuilding cannot fix it, because a rebuild re-aggregates committed reports and never
re-runs a policy. Closing the gap needs GPU time.

The board is one minor version behind the shipping tool. That gap is bridged by
[`leaderboard/method-equivalence.json`](https://github.com/provael/provael/blob/main/leaderboard/method-equivalence.json), whose own
`what_this_is_not` field says it plainly: **"This is a code-inspection argument, NOT a
re-measurement."** Its previous entry, for 0.32.0, was settled the only way such an entry can be:
the suite was re-run on 0.41.2 and the family moved (62/150 to 50/150). The re-run moved the board;
the argument never could.
