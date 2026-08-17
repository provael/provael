# The public ASR leaderboard

> **Evidence, not certification.** The leaderboard reports measured Attack Success Rates in
> simulation. It is not a safety rating and not a conformity statement.

The [leaderboard](https://huggingface.co/spaces/Sattyam/provael-leaderboard) aggregates
`(policy × suite × family) → ASR` results into a ranked, reproducible, signable board. Lower ASR is
more robust.

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
- **3 of 15 adversarial families measured** (`instruction`, `injection`, `visual`). **The other
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

```bash
# Build the real board (stamps date + commit + inputs digest)
provael leaderboard build --real results/smolvla_libero_object --out leaderboard/results

# Reproduce: rebuild and confirm the digest matches
provael leaderboard build --real results/smolvla_libero_object --out /tmp/rebuild
python -c "import json; a=json.load(open('leaderboard/results/leaderboard.json'))['inputs_digest']; \
b=json.load(open('/tmp/rebuild/leaderboard.json'))['inputs_digest']; print('match:', a==b)"
```

## What a re-stamp does and does not change

A board is rebuilt by **aggregating committed `report.json` files** — it does not re-run a policy.
So re-running the generator moves `generated_at` and `commit` to today while **every row still
carries the measurement it always did**, possibly made by a much older release.

That is a trap: a board carrying only `generated_at` reads as a fresh measurement. Schema v3 adds
**`measured_with`** — the sorted `tool_version` values of the aggregated reports, i.e. the versions
the *numbers* came from — and `Leaderboard.is_restamp()` answers the question directly. The
published board reports `measured_with: ["0.32.0"]` against a build commit from the current release
line: the provenance envelope is current, the measurement is the ten-task SmolVLA × LIBERO suite
screen those shards recorded.

## Qualifiers travel with the row (schema v5)

A leaderboard is where a number travels furthest from its own report, and until v5 it arrived
stripped: `report.json` recorded `calibrated` and `stochastic`, and the board dropped both. A row
reading `41.3%` with no further context is a stronger claim than the run behind it ever made.

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
provael leaderboard build --real results/smolvla_libero_object --sign --key provael-ed25519.pem \
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
