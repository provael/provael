# Quickstart

Runs in well under a second on a CPU — no GPU, no model download.

```bash
pip install provael
provael attack --recipe full-sweep --out runs/first-scan
```

```
                        Provael — ASR by attack
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ attack            ┃ EAI   ┃              ASR ┃ successes ┃ attempts ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ freeze            │ EAI04 │ 100.0% [72–100%] │        10 │       10 │
│ patch             │ EAI02 │   80.0% [49–94%] │         8 │       10 │
│ roleplay          │ EAI01 │   80.0% [49–94%] │         8 │       10 │
│ …                 │ …     │              …   │         … │        … │
└───────────────────┴───────┴──────────────────┴───────────┴──────────┘
Attack Success Rate (ASR): 74.4% (67/90)
```

## Commands

```bash
provael list-policies         # 7 policies (stub CPU; smolvla/pi0/groot/openvla need extras)
provael list-attacks          # 9 attacks across instruction/visual/injection/action
provael list-recipes          # named presets: quick / instruction-only / full-sweep / ci-gate
provael list-reproductions    # FreezeVLA / OpenVLA-patch / BadVLA / RoboPAIR
provael reproduce freezevla   # reproduce a published attack on the CPU stub
provael report --in runs/first-scan --format scorecard   # one-page ASR scorecard
provael report --in runs/first-scan --format oscal       # NIST OSCAL evidence
provael export --in runs/first-scan --format avid        # AVID record
```

## Outputs

`report.json` (byte-deterministic), `report.md`, SARIF (`--format sarif`), a compliance evidence
pack (`--format compliance`), an ASR scorecard (`--format scorecard`), OSCAL, and an AVID record.

## Real models & simulators

```bash
pip install 'provael[lerobot]'                 # GPU
PROVAEL_INTEGRATION=1 provael attack --policy smolvla --suite libero \
    --model HuggingFaceVLA/smolvla_libero --attacks none,instruction,visual,injection
```

See the [examples gallery](examples.md) for π0 / GR00T / OpenVLA adapters and the second
(Meta-World) suite.

## Continuous security gate (CI)

Gate every new checkpoint in CI with the reusable Action. It red-teams the policy, uploads findings
as SARIF, and fails the job when the ASR exceeds a threshold **or** regresses past a tolerance versus
a known-good baseline — a slice regresses only when the candidate ASR beats the baseline by more than
the tolerance **and** the two 95% Wilson CIs are disjoint, so small-`n` noise cannot fail a build.

```yaml
# .github/workflows/provael.yml
permissions:
  contents: read
  security-events: write            # upload SARIF to code scanning
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: provael/provael@v0.23.0
        with:
          attacks: instruction,visual,injection
          episodes: "10"
          asr-threshold: "0.5"
          baseline: .provael/baseline.report.json          # the per-checkpoint regression gate
          regression-tolerance: "0.05"
          sign: "true"                                      # emit a signed regression attestation
          signing-key: ${{ secrets.PROVAEL_SIGNING_KEY }}   # empty -> ephemeral key
```

The stub policy/suite run on a CPU runner (a fast wiring smoke); a real policy (`policy: smolvla`,
`suite: libero`) needs a GPU runner + the `[lerobot]` extra.

**Self-maintaining.** Copy the reference workflow `.github/workflows/checkpoint-security-gate.yml`: it
persists the baseline in the Actions cache and promotes each *passing* checkpoint to the next
baseline — the first run establishes the baseline, every run after diffs against it.

**Signed evidence.** Each run emits a signed **regression attestation** — a tamper-evident,
offline-verifiable Ed25519 envelope binding the diff + SARIF + summary under one signature, stating
the verdict with the ASR *and its 95% Wilson CI* (never a bare number). The same runs locally:

```bash
provael report --in runs/candidate --baseline .provael/baseline.report.json \
    --sarif-out runs/candidate/regression.sarif \
    --attest-out runs/candidate/regression.attestation.json    # signed; --key <pem> for an org key
```

The gate is generic across the policy/suite abstraction — point it at your checkpoint. Generality is
intended; it is tested on SmolVLA × LIBERO today. **Evidence, not certification.**
