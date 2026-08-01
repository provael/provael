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
