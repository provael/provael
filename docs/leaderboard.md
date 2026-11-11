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
- **Task-clustered intervals on the rate and the floor** (from schema v7; the board committed here
  is still v6) — resampled by task, because a suite's episodes are not independent
  ([below](#task-clustered-intervals-on-the-rate-and-the-floor-schema-v7)).
- **A transfer-status label** — `real-transfer` (a real policy in a real simulator) or
  `stub-scaffolding` (the deterministic CPU stub, or a real policy on the stub suite). When any real
  run is present the board is not a demo, and stub and real rows are **never silently mixed** — each
  is labelled.

## The published result

The board aggregates one run — **`results/smolvla_libero_object_suite_2026-09-14`**, the ten
`libero_object` tasks on the real **SmolVLA × LIBERO** policy, **measured with `provael 0.41.2`** on
14 September 2026 — into four family rows. The figures below are copied from
`leaderboard/results/leaderboard.json` and a test holds the page to the file
(`tests/test_leaderboard_version_claim.py`):

| family | rate on the board | Wilson 95% CI | benign control | transfer status |
| --- | ---: | ---: | ---: | --- |
| `instruction` | **50/150 (33.3%)** | [26%, 41%] | 1/50 | `real-transfer` |
| `injection` | 2/50 (4.0%) | [1%, 13%] | 1/50 | `real-transfer` — at the floor |
| `visual` | 2/100 (2.0%) | [1%, 7%] | 1/50 | `real-transfer` — at the floor |
| `baseline` (`none`) | 1/50 (2.0%) | [0%, 10%] | — | the control itself |

Only the **instruction** family separates from the benign floor, and a family row is a coarser
quantity than the per-attack result the run's own README leads with (`roleplay` 42/50; the family
row pools it with `goal_substitution` 7/50 and `paraphrase` 1/50 — 50/150). `mcp_tool_desc` is
listed as **not applicable** (zero applicable episodes), never as a null. The honesty is the point:
the board shows what does and does not move this policy, with intervals, rather than a single
headline number.

## What the published board does *not* cover

The published board does not cover what its one run did not run. Stated plainly, because the
rendered page states it too:

- **Every row was measured with **`provael 0.41.2`** — and with nothing newer.** The board's
  `stale: true` says why that matters: 0.41.2 is two minor versions behind the tool that assembled
  the board (0.43.0), past the one-version limit, so the rows are disclosed as stale until a re-run
  — see [staleness](#staleness-is-a-field-not-a-banner-schema-v6). The build stamp is current; the
  measurement is dated.
- **1 policy, 1 suite.** `smolvla` × the ten `libero_object` tasks. Seven of the eight registered
  policy backends have never produced a board row, and three of those (`groot`, `openvla`,
  `openpi`) have never loaded a checkpoint at all — `provael list-policies` marks them
  `scaffolding`. The π0.5 preliminary leg is committed as a run, not as board rows.
- **3 of 17 adversarial families measured** (`instruction`, `injection`, `visual`). The other
  **fourteen** are absent from the board, which is not the same as scoring 0%: nine have no
  real-model measurement anywhere in this repository, and five have only the three-episode breadth
  probe of the same night (`results/smolvla_libero_object_families_2026-09-14`), a result and not a
  rate. An absent family is `N/A`, and reading it as a pass is the single most likely way to misuse
  this page.
- **The competence control is in the run, not on the board.** The run's benign arm completes the
  task 48/50 (96%) unattacked; the board schema carries the benign false-positive control (1/50)
  but no clean-task-success field, so read the competence figure from the
  [run README](https://github.com/provael/provael/blob/main/results/smolvla_libero_object_suite_2026-09-14/README.md).

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
`results/smolvla_libero_object`, which is the superseded June 2026 single-task run (measured with
**0.1.0**); rebuilding from that one produces a different digest, different rows, and a board forty
minor versions behind the published one. Several such directories are committed and their names differ
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

## Task-clustered intervals on the rate and the floor (schema v7)

`ci95` and `benign_ci95` are episode-level Wilson intervals, and the episodes behind a ten-task row
are not independent: an attack that works on one task tends to work on every seed of it. Schema v7
adds three row fields, derived from the aggregated episodes like every qualifier above:

| field | what it is |
| --- | --- |
| `tasks` | how many distinct tasks the row's rate is pooled over |
| `clustered_ci95` | a 95% percentile interval on `asr` from resampling tasks (2000 seeded draws) |
| `benign_clustered_ci95` | the same interval for the benign floor the row is read against |

Either interval is `null` when the row spans fewer than two tasks, or when every task scored alike,
because a resample there is a zero-width interval that carries no information. The fields are
registered in `_ROW_FIELDS_ADDED_IN[7]`, so a v6 board keeps verifying against its v6 signature, and
the board committed here stays v6 until it is rebuilt and re-signed through
`leaderboard-rebuild.yml`.

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

That shows the board matches the key fetched beside it. Whether that key is the project's is a
separate check: [pin it out of band](#pinning-the-key-out-of-band).

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

Rebuild and re-sign from the run the board names, with a key you hold:

```bash
run="$(python -c "import json; print(json.load(open('leaderboard/results/source.json'))['run'])")"
provael leaderboard build --real "$run" --submitted-by provael --provenance maintainer-run \
    --sign --key provael-ed25519.pem --out leaderboard/results
provael leaderboard verify --in leaderboard/results/leaderboard.json --pubkey <that key's public half>
```

The project's own board is re-signed only by `leaderboard-restamp.yml` and
`leaderboard-rebuild.yml`, which read the key from the repository secret. Leaving out
`--submitted-by` and `--provenance` drops every row's attribution. Signing with an omitted `--key`
uses an ephemeral key (integrity, not identity) and writes the public half next to the board.

### What `leaderboard verify` checks, and what it does not

`provael leaderboard verify` checks one thing: the Ed25519 signature over the board's canonical
bytes ([below](#the-bytes-the-signature-covers)), against the key file you pass. It exits 0 with
`leaderboard OK` when the signature holds, and 1 on an invalid signature or an unsigned board. It
does not check:

- that the key file is the project's key. [Pinning it](#pinning-the-key-out-of-band) is how you
  know.
- the keyid it prints. That id comes from the board's own `signature` block, which the signature
  does not cover, so it names the key the board claims to be signed with. Compare key files, not
  printed ids.
- revocation or expiry. `provael attest --verify --trust-store` reads each key's `status` and
  validity window from a trust store; `leaderboard verify` takes one key file and nothing else.
- freshness. `stale` sits outside the signature on purpose
  ([above](#staleness-is-a-field-not-a-banner-schema-v6)).

Turning the first three into failures waits for the next board schema change, together with the
canonical-bytes change below; neither is in the code today.

### Where the key was made, and where it lives

Where the current private key was generated is not recorded in the repository. The commit that
introduced it, `215a925` on 30 July 2026 (#74), records why it exists: the previous private key was
gone. Its only local copy had been deleted after it was stored as an Actions secret, under a name no
workflow reads, and a secret cannot be read back. The commit re-signed the board with the new key
and noted that the private key still had to be stored as `PROVAEL_SIGNING_KEY`. It does not say
where the new key was made, or with what.

The private key is stored as the repository's GitHub Actions secret `PROVAEL_SIGNING_KEY`, and
`.gitignore` keeps `*.pem` and `*.key` out of git. Three workflows read it:
`leaderboard-restamp.yml` and `leaderboard-rebuild.yml` sign the board with it, and
`checkpoint-security-gate.yml` signs its regression attestations with it. Whether a copy exists outside that secret is not recorded in the
repository.

The public key is `leaderboard/results/leaderboard.pub`, and
`git log --follow -- leaderboard/results/leaderboard.pub` lists every change to it: the current key
arrived in `215a925`, and the retired one is in the history before it.

### Pinning the key out of band

A key downloaded beside the board proves only that the two files agree, and whoever can replace one
can replace both. Pin the key once, from a source that does not share the board's fetch path, and
check every later board against your copy:

1. Get `leaderboard.pub` from two places that do not share a fetch path. `main` on GitHub is one. A
   release's source archive on Zenodo is another (archiving began with v0.34.0, and the concept DOI
   is in `CITATION.cff`), and so is a clone you already hold.
2. Compare the full SHA-256 of the copies (`sha256sum leaderboard.pub`, or `shasum -a 256` on
   macOS). The keyid on this page is only the first 16 hex characters of that digest. The digest
   covers the file's bytes, so a checkout that rewrote line endings gives a different digest for the
   same key; compare the base64 line of the PEM in that case.
3. Keep the checked copy and pass it to every later check:
   `provael leaderboard verify --in leaderboard.json --pubkey <your pinned copy>`.
4. If a later board verifies only against a freshly downloaded key, the key has changed. Look for the
   rotation on this page and in the [errata](errata.md) before you trust it. An unrecorded rotation
   is the case the pin exists to catch.

### Rotating the key

1. Generate a new Ed25519 private key as a PKCS8 PEM. `provael.attest.generate_private_key_pem()`
   returns one, and `provael.attest.public_key_pem()` derives its public half. The CLI has no
   command that keeps a private key: `leaderboard build --sign` without `--key` signs with a
   throwaway key and writes only the public half.
2. On a branch, replace `leaderboard/results/leaderboard.pub` with the new public half and run
   `uv run python scripts/render_keyid.py`, which rewrites the keyid on this page.
   `tests/test_docs_keyid_matches_pubkey.py` fails on any keyid it missed.
3. Store the private key as the `PROVAEL_SIGNING_KEY` secret, under exactly that name: #74 lost the
   previous key to a secret stored under a name no workflow reads. From then on, a re-stamp
   dispatched on `main` fails at its verify step until the branch merges, because `main` still
   carries the old public key, so nothing signed with the new key can land beside the old one.
4. Dispatch `leaderboard-restamp.yml` on the branch. It re-signs the board from the run
   `source.json` names, verifies it against the branch's `leaderboard.pub`, refuses a result whose
   `measured_with` or attribution moved or whose `stale` flag was cleared, and commits to the
   branch.
5. Record the rotation: a CHANGELOG line, and an erratum if a published surface named the old key
   (E-2026-02 records what happened when one did). Say whether the old key was retired or revoked.
6. Merge the branch as one PR. Leave the old public key in git history, so the signatures made with
   it stay checkable.

### Revocation, and the rows already signed

`leaderboard verify` has no revocation input, so the maintainer revokes a key in public: by rotating
it as above, and by recording the revoked key, the date and the reason in the [errata](errata.md).

For rows already signed, that means:

- The rows stay what they were. They are a pure function of the committed `report.json` files,
  bound by `inputs_digest`, so rebuilding the board from the run `source.json` names gives the same
  rows and the same digest ([how](#provenance-and-reproducibility)). #74 checked exactly that: rows
  and `inputs_digest` identical, with only the signature, `generated_at` and `commit` moving.
  Revocation withdraws the signature's word on who published them.
- A signature carries no trusted time. `generated_at` sits inside the signed bytes, but the signer
  writes it, so whoever holds a stolen key can sign a backdated board. After a revocation for
  compromise, treat every board signed with that key as unsigned, whatever its date, and check its
  rows by rebuilding them (the `inputs_digest` must match) or against the re-signed board.
- A key retired without compromise, like the one #74 replaced (its private half was lost, not
  leaked), leaves its earlier signatures as good as they were, because nobody holds it to sign with.

### The bytes the signature covers

The signature is Ed25519 over the DSSE pre-authentication encoding
`DSSEv1 <type length> <type> <payload length> <payload>` (each length a byte count in decimal),
with the payload type `application/vnd.provael.leaderboard+json`. It is stored base64-encoded in
`signature.sig`. The payload is the board as JSON with `signature` removed, and with every field
introduced after the board's own `schema_version` stripped (`_FIELDS_ADDED_IN` and
`_ROW_FIELDS_ADDED_IN` in `src/provael/leaderboard.py`). `provael.attest.canonical_json` serialises
it: Python's `json.dumps(obj, sort_keys=True, separators=(",", ":"))`, encoded as UTF-8. Python's
default `ensure_ascii=True` turns every non-ASCII character into a `\uXXXX` escape, so the bytes are
ASCII.

That is not RFC 8785 (the JSON Canonicalization Scheme), and the two disagree on ordinary values:

| value | the bytes Provael signs | RFC 8785 |
| --- | --- | --- |
| the string café | `"caf\u00e9"` | `"café"`, in UTF-8 |
| the number 1.0 | `1.0` | `1` |
| the number 1e-7 | `1e-07` | `1e-7` |
| the integer 2^64 | `18446744073709551616` | `18446744073709552000` |

A JCS library therefore serialises the same board to different bytes, and the signature does not
verify over them; to check a board without Provael, reproduce the Python rules above.
`tests/test_leaderboard.py` holds the Provael column to `canonical_json` and to this page. Moving to
RFC 8785 would change the bytes of every board, and so every signature, so it needs a new signature
algorithm label and a board schema version. It waits for the next board schema change.

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

