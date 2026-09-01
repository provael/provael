# Errata

Corrections to published Provael artifacts. Entries are append-only and dated. Nothing is removed
from this page once added — an erratum that disappears is worse than the error it recorded.

If you hold a Provael artifact, check here before relying on a regulatory date in it.

---

## E-2026-01 — Signed attestations carry a superseded EU AI Act application date

**Status:** corrected in the tool · previously issued bundles are unaffected in authenticity
**Date raised:** 1 August 2026
**Affects:** any attestation bundle signed before this correction shipped

### What is wrong

The regulatory clock embedded in every attestation payload recorded the EU AI Act Annex I
(product-embedded high-risk) application date as:

```
applies_from: 2027-08-02
```

with a note stating that the Digital Omnibus deferral to 2028 had been agreed only provisionally
and had not been published in the Official Journal.

That was accurate when written. It stopped being accurate on **24 July 2026**, when
**Regulation (EU) 2026/1744 (Digital Omnibus on AI)** was published in the OJ; it entered into force
on **27 July 2026** and moved product-embedded Annex I application to **2 August 2028**
(stand-alone Annex III moves to 2 December 2027).

The clock's own `last_verified` field read `2026-07-23` — the fact was checked one day before it
changed, and nothing re-read it.

### What is correct

| Field | Superseded value | Correct value |
| --- | --- | --- |
| AI Act Annex I `applies_from` | `2027-08-02` | **`2028-08-02`** |

`2027-08-02` remains meaningful as the **superseded statutory baseline** under Regulation (EU)
2024/1689, and is still named in the corrected note for that reason. It is no longer the operative
date.

### What this does and does not affect

**Signatures remain valid.** The cryptographic properties of an affected bundle are unchanged: it is
still an authentic, tamper-evident record of the run it describes, and `provael verify` will still
verify it. The defect is in a *fact carried inside* the payload, not in the binding between the
payload and the run.

**No measured result changes.** The regulatory clock is contextual metadata. It is not an input to
any attack, score, ASR, confidence interval or verdict. No number in an affected bundle moves.

**What does change** is planning. A reader who took the embedded date at face value would be
planning against 2 August 2027 for embedded Annex I obligations, roughly twelve months earlier than
the instrument now requires.

### How to tell whether a bundle is affected

Decode the payload and read the clock entry:

```bash
provael verify bundle.json --print-payload | jq '.crosswalk.regulatory_clock[]
  | select(.framework_id == "eu-ai-act") | {applies_from, last_verified}'
```

`applies_from: "2027-08-02"` means the bundle predates this correction.

### What to do

No action is required for the integrity of the artifact. If the bundle has been filed anywhere that
its dates inform a schedule, re-run `provael attest` on the same report to produce a bundle carrying
the corrected clock, or cite this erratum alongside the original.

### What was changed to prevent recurrence

The correction landed with `tests/test_regulatory_consistency.py`, which scans every tracked file
for the superseded framing and asserts that the one restatement of the date outside the clock
(`hosted/report.py`) agrees with it.

The more useful lesson is the one that made this possible in the first place: the test suite had
been *asserting* the superseded framing — it required the note to state the deferral was still
pending — so from 24 July onward, a correct fix would have failed CI. A guard that pins a fact must
be revised with the fact, or it stops protecting the fact and starts protecting the error.

---

## E-2026-02 — The documented verify command printed a pre-rotation signing keyid

**Status:** corrected · the published board and its signature were correct throughout
**Date raised:** 3 August 2026
**Window:** 30 July 2026 (key rotation, #74) to 3 August 2026 (this correction)

### What was wrong

The project signing key was rotated on 30 July 2026 (#74; the old private key was
unrecoverable). The published board was re-signed with the new key the same day, and verifying it
per the documented steps succeeded — printing the new key's id, `8d62aa33ed5162f3`.

The documentation did not move with the key. `README.md` and `docs/leaderboard.md` kept showing
the pre-rotation id, `5b9a65790d93d0bc`, as the verify command's expected output, and
`docs/leaderboard.md` additionally stated that the pre-rotation id belonged to *the only key the
published board is signed with*. So for four days, anyone who ran the documented verification got
a result the documentation called impossible. The natural reading of that contradiction — that the
signature is fraudulent — was wrong in the worst direction available to this project: the check
was working and the prose about the check was not.

### What is correct

The keyid is not an independent fact; it is **derived** — the first 16 hex characters of SHA-256
over `leaderboard/results/leaderboard.pub`. Compute it yourself rather than trusting either this
page or the README:

```bash
python -c "import hashlib; print(hashlib.sha256(open('leaderboard/results/leaderboard.pub','rb').read()).hexdigest()[:16])"
```

That value, the id in `leaderboard.json`'s signature block, and the id `provael leaderboard
verify` prints must all agree — today they read `8d62aa33ed5162f3`.

### What this does and does not affect

**Every signature verdict issued during the window was correct.** `verify` checks the signature
against the key you hand it; the stale prose changed what a reader *expected*, never what the tool
*computed*. No board, signature or measured number was wrong.

### What was changed to prevent recurrence

The keyid is no longer typed into documentation. `scripts/render_keyid.py` derives it from the
published key and rewrites both surfaces, and `tests/test_docs_keyid_matches_pubkey.py` sweeps
every tracked file and fails the build on any 16-hex value following the token `keyid` that the
published key does not derive to — the same single-source discipline the family counts and
version pins already have. A future rotation that forgets the docs now fails CI instead of
waiting for a reader to find the contradiction.

---

## E-2026-03 — Two READMEs published a zero-width confidence interval for three null arms

**Status:** corrected in the tool and on both surfaces · the signed board and its signature were correct throughout
**Date raised:** 30 August 2026
**Window:** 9 August 2026 (#110 and #113, first publication) to 30 August 2026 (#157, this correction) — 21 days
**Affects:** `README.md` and `results/smolvla_libero_object_suite/README.md` as published in that window. No signed artifact is affected.

### What was wrong

Both READMEs published the task-clustered 95% confidence interval for the three null arms
(`patch`, `decoy_object`, `scene_text`, each 0/50) as:

```
[0%, 0%]
```

A zero-width interval states that the true rate is known exactly. It is not: the arms are null
because nothing succeeded in fifty attempts, which is a very different claim from a rate of
precisely zero.

The mechanism was a guard that checked a proxy. `provael.scoring.paired.cluster_bootstrap_ci`
already refused to answer below two tasks, and the reasoning recorded beside that refusal was
correct — a bootstrap over one task resamples the same thing every time and returns a zero-width
interval carrying no information. But the guard counted **clusters**, not the interval it produced.
Ten tasks that all score zero pass a cluster count and are just as degenerate: every resample
returns the same rate, so the percentiles collapse onto it.

Worse for a reader trying to check the work, the project contradicted itself in public.
provael.com published a **non-zero** upper bound for those same three 0/50 results throughout.
Same dataset, two Provael surfaces, incompatible claims.

### What is correct

| Arm | n | Superseded value | Correct value |
| --- | ---: | --- | --- |
| `patch` | 0/50 | `[0%, 0%]` | **no clustered interval** — the bootstrap declines |
| `decoy_object` | 0/50 | `[0%, 0%]` | **no clustered interval** — the bootstrap declines |
| `scene_text` | 0/50 | `[0%, 0%]` | **no clustered interval** — the bootstrap declines |

Both tables now render `—` for these arms and say why. Pooled as a plain binomial rather than
clustered, 0/50 is consistent with a true rate as high as **7.1%** (exact 95% upper bound), and the
corrected prose states that figure so the reader is left with a bound rather than nothing.

Declining is the right answer rather than a gap to be filled: a caller that receives no interval
must fall back to a bound that stays honest, where one that receives `[0%, 0%]` will print it.

### What this does and does not affect

**No signed artifact is affected, and no signature verdict was ever wrong.** The published
leaderboard carries **Wilson** intervals, not the clustered bootstrap, and has always recorded
`[0.0%, 7.1%]` for the 0/50 injection row and `[0.0%, 3.7%]` for the 0/100 visual row. Attestation
bundles are likewise unaffected. The defect lived only in two hand-maintained Markdown tables.

**No measured result changes.** The rates, denominators, McNemar p-values and Holm-adjusted values
in those tables were correct. Only the interval column was wrong, and only for the three arms whose
rate is zero.

**What does change** is how strong those three nulls look. A reader taking `[0%, 0%]` at face value
would conclude the attack had been shown to have no effect. The measurement supports only that it
was not observed to succeed in fifty attempts, which leaves a true rate of up to 7.1% on the table —
and 7.1% of a keep-out violation is not nothing.

### How to tell whether a copy you hold is affected

Search it:

```bash
grep -n '\[0%, 0%\]' README.md results/smolvla_libero_object_suite/README.md
```

Any match outside the paragraph explaining this correction predates the fix.

### What was changed to prevent recurrence

`cluster_bootstrap_ci` now guards **the interval it computed** rather than the shape of its input:
if the lower and upper bounds are equal it returns nothing, whatever the cluster count.
`tests/test_paired.py` pins that with an all-zero and an all-success sweep, and
`test_bootstrap_still_answers_when_one_task_differs` keeps the refusal narrow — one dissenting task
is a real measurement and must not be declined.

The second guard is the one that earned its place. Because these tables are hand-maintained and
`cluster_bootstrap_ci` has no caller in `src/`, fixing the function would never have corrected a
published number. `tests/test_no_zero_width_intervals.py` scans tracked Markdown for a degenerate
interval in a table row, and **on its first run it found the second copy under `results/` that the
first fix had missed**. It carries `test_the_guard_can_actually_fail`, which pins the regex against
the exact row that shipped, so it cannot quietly stop matching.

---

## E-2026-04 — The CRA severe-incident final report was published with the wrong start point

**Status:** corrected on provael.com and in its machine-readable clock · no signed artifact is affected
**Date raised:** 1 September 2026
**Window:** 25 August 2026 (#86, first publication of the Article 14 sub-deadlines) to 1 September 2026 — 7 days
**Affects:** `provael.com/regulatory-clock` and `/regulatory-clock.json` as published in that window. Nothing in this repository, and no attestation bundle, carried the defect.

### What was wrong

The CRA Article 14 reporting clock published both of its final-report deadlines as a single row:

```
Final report, due once a corrective or mitigating measure is available
  — 14 days for an actively exploited vulnerability, one month for a severe incident.
```

The start point named in that sentence is correct for the vulnerability branch and **wrong for the
incident branch**.

### What is correct

Article 14(2)(c) and Article 14(4)(c) measure from different events:

| Branch | Deadline | Runs from |
| --- | --- | --- |
| Actively exploited vulnerability, Art. 14(2)(c) | 14 days | after a corrective or mitigating measure **is available** |
| Severe incident, Art. 14(4)(c) | one month | after **submission of the 72-hour incident notification** under Art. 14(4)(b) |

The incident clock does not wait for a fix at all. Collapsing both into one sentence applied the
first branch's anchor to the second, which points a reader at a later start than the regulation
allows.

### What this does and does not affect

**No measured result, signed artifact or attestation is affected.** The defect was in a regulatory
date rendered on the website, not in any number this tool produces, and not in any payload it signs.

**The 24-hour, 72-hour and 14-day figures were correct throughout.** Only the anchor for the
one-month incident deadline was wrong.

**What does change** is a runbook. A reader who took the superseded wording at face value would wait
for a corrective measure before starting the one-month count — a count that had already been running
since their own 72-hour filing.

### How to tell whether a copy you hold is affected

```bash
curl -s https://www.provael.com/regulatory-clock.json \
  | jq '.entries[] | select(.id == "eu-cyber-resilience-act") | .reportingSubDeadlines'
```

Three sub-deadlines rather than four, with no `one month` row, means the copy predates this
correction.

### What was changed to prevent recurrence

The two branches are now separate rows carrying their own anchors, and the clock entry's
`reportingSubDeadlinesSource` was moved from the Commission's CRA summary to the OJ text on
EUR-Lex. That is the reusable lesson: the sub-deadlines had been transcribed from a **secondary
summary**, whose phrasing does not carry the distinction the regulation makes. A secondary source is
fine for finding a fact and not for pinning one.

The entry also now records Article 69(3) — the express derogation from 69(2) that puts the entire
in-scope installed base under Article 14 reporting while leaving it outside the product
requirements, which is the clause most often missed.

