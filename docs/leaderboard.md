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

## Provenance and reproducibility

A real board is stamped with a **UTC build date**, the **source commit**, and a **SHA-256 digest of
the aggregated input reports** (the same digest approach as [attestation](ATTESTATION.md), so a board
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

## Signing and offline verification

The authoritative hosted board is **Ed25519-signed** (via the `provael[attest]` extra). The
signature covers the whole board except the signature field, and verifies offline with no network:

```bash
provael leaderboard build --real results/smolvla_libero_object --sign --key provael-ed25519.pem \
    --out leaderboard/results
provael leaderboard verify --in leaderboard/results/leaderboard.json --pubkey leaderboard.pub
```

Signing with an omitted `--key` uses an ephemeral key (integrity, not identity) and writes the
public half next to the board.

## Open-core

The CLI builds and verifies boards for anyone, free and Apache-2.0. The **hosted, project-key-signed
board** — signed with Provael's key and backed by real-VLA (GPU) runs rather than the stub — is the
paid surface. Submitting a result is a pull request; see
[CONTRIBUTING-leaderboard.md](https://github.com/provael/provael/blob/main/CONTRIBUTING-leaderboard.md).
