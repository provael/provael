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
