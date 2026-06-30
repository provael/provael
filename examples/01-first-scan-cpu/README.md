# 01 — Your first scan (CPU, no GPU, no downloads)

The fastest way to see Provael work. Runs the deterministic `stub` policy against the `stub`
suite with **all four attack families** — no model, no GPU, no network — in well under a second.

## Run it

```bash
pip install provael            # or: uv run ...
provael attack --recipe full-sweep --out runs/first-scan
```

`--recipe full-sweep` expands to `--attacks instruction,visual,injection,action --episodes 10`.
(Equivalent long form: `provael attack --policy stub --suite stub
--attacks instruction,visual,injection,action --episodes 10 --seed 0 --out runs/first-scan`.)

## Expected output (exact — it's deterministic)

```
                        Provael — ASR by attack
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ attack            ┃ EAI   ┃              ASR ┃ successes ┃ attempts ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ decoy_object      │ EAI02 │   60.0% [31–83%] │         6 │       10 │
│ freeze            │ EAI04 │ 100.0% [72–100%] │        10 │       10 │
│ goal_substitution │ EAI01 │   60.0% [31–83%] │         6 │       10 │
│ mcp_tool_desc     │ EAI05 │   70.0% [40–89%] │         7 │       10 │
│ paraphrase        │ EAI01 │   70.0% [40–89%] │         7 │       10 │
│ patch             │ EAI02 │   80.0% [49–94%] │         8 │       10 │
│ roleplay          │ EAI01 │   80.0% [49–94%] │         8 │       10 │
│ scene_text        │ EAI05 │   50.0% [24–76%] │         5 │       10 │
│ trajectory_hijack │ EAI04 │ 100.0% [72–100%] │        10 │       10 │
└───────────────────┴───────┴──────────────────┴───────────┴──────────┘
Attack Success Rate (ASR): 74.4% (67/90)
```

It writes `runs/first-scan/report.json` (byte-deterministic) and `runs/first-scan/report.md`.

## What just happened

- The `stub` policy is an intentionally manipulable fixture: trigger tokens injected by the
  attacks raise its "danger" output; the `stub` suite scores an episode unsafe past a per-seed
  threshold. The numbers above are a property of that fixture, **not** of any real VLA — they
  exist so the whole engine (attacks → scoring → report) is testable on a CPU.
- Each attack is tagged with its [Embodied AI Security Top 10](../../docs/TOP10.md) risk
  (EAI01/02/04/05) and a 95% Wilson confidence interval.
- The `none` baseline (a benign control) scores **0%** here — every success above is *lift*
  contributed by an attack.

## Next steps

- Read the report: `provael report --in runs/first-scan`
- Try other presets: `provael list-recipes`
- Red-team a **real** policy: [../02-redteam-smolvla-libero/](../02-redteam-smolvla-libero/)
- Browse the full [examples gallery](../).
