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
published board reports `measured_with: ["0.1.0"]` against a build commit from the current release
line: the provenance envelope is current, the measurement is the SmolVLA × LIBERO run it has
always been.

Recording that in the JSON was only half the fix. Until 0.29.1 the *rendered* Space showed a fresh
build date and an Ed25519 signature above rows measured many releases earlier, with nothing on the
page saying so — and a signature over stale data is worse than no signature, because it reads as
currency. The Space now derives a staleness-and-coverage banner from `measured_with` and the rows
themselves, above the tables rather than below them.

## Signing and offline verification

The published board is **Ed25519-signed** (via the `provael[attest]` extra). The
signature covers the whole board except the signature field, and verifies offline with no network.

**Verify the published board in two commands** — no network, no trust in this page:

```bash
pip install "provael[attest]"
curl -fsSLO https://raw.githubusercontent.com/provael/provael/main/leaderboard/results/leaderboard.json
curl -fsSLO https://raw.githubusercontent.com/provael/provael/main/leaderboard/results/leaderboard.pub
provael leaderboard verify --in leaderboard.json --pubkey leaderboard.pub
# -> leaderboard OK  keyid 5b9a65790d93d0bc
```

A non-zero exit and `leaderboard signature INVALID` is the answer you should get if anything in the
board was altered — including a single success count. That is the point: the numbers are covered by
the signature, not merely published alongside it.

The public key lives at **`leaderboard/results/leaderboard.pub`** (keyid `5b9a65790d93d0bc`) and is
the only key the published board is signed with. CI enforces three things so this cannot rot: the
board is signed, the signature verifies **against that published key**, and the build commit is no
more than **3 released tags** behind — re-stamping is a GPU-free one-command operation, so the cost
of staying current is low.

Rebuild and re-sign:

```bash
provael leaderboard build --real results/smolvla_libero_object --sign --key provael-ed25519.pem \
    --out leaderboard/results
provael leaderboard verify --in leaderboard/results/leaderboard.json --pubkey leaderboard.pub
```

Signing with an omitted `--key` uses an ephemeral key (integrity, not identity) and writes the
public half next to the board.

## Open-core

The CLI builds and verifies boards for anyone, free and Apache-2.0. The **hosted board, signed with a published project key** — the
board** — signed with Provael's key and backed by real-VLA (GPU) runs rather than the stub — is the
paid surface. Submitting a result is a pull request; see
[CONTRIBUTING-leaderboard.md](https://github.com/provael/provael/blob/main/CONTRIBUTING-leaderboard.md).
