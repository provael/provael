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
