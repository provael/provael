# Regression-gate a checkpoint update in CI

Block a pull request when a policy retrain makes it **more** attackable — the cheapest insurance
a team with no security headcount can buy. The pattern: run Provael on the new checkpoint, compare
its ASR to the last known-good baseline, fail the PR if it regressed past a tolerance.

## The check

```bash
# 1. Run the gate recipe on the candidate checkpoint.
provael attack --recipe regression-gate --format scorecard --out runs/candidate

# 2. Compare overall ASR to the committed baseline (runs/baseline/report.json).
python - <<'PY'
import json, sys
new = json.load(open("runs/candidate/report.json"))["asr"]
base = json.load(open("runs/baseline/report.json"))["asr"]
tol = 0.05  # allow 5 percentage points of noise
print(f"baseline ASR={base:.3f}  candidate ASR={new:.3f}  tol={tol}")
sys.exit(1 if new > base + tol else 0)
PY
```

Step 1 also writes `runs/candidate/report.scorecard.md` — the one-page artifact to attach to the
PR (verdict, EAI heatmap, CIs). For a hard ceiling instead of a delta, gate on the scorecard
verdict directly: `provael report --in runs/candidate --format scorecard --threshold 0.5`.

## GitHub Actions

```yaml
name: Provael regression gate
on: [pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4          # baseline lives at runs/baseline/report.json
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install provael
      - run: provael attack --recipe regression-gate --format scorecard --out runs/candidate
      - run: |
          python - <<'PY'
          import json, sys
          new = json.load(open("runs/candidate/report.json"))["asr"]
          base = json.load(open("runs/baseline/report.json"))["asr"]
          sys.exit(1 if new > base + 0.05 else 0)
          PY
      - uses: actions/upload-artifact@v4
        with: { name: provael-scorecard, path: runs/candidate/report.scorecard.md }
```

The default `stub` policy runs on a CPU runner (a smoke test of the gate wiring). Point it at a
real policy (`--policy smolvla --suite libero`, GPU + `[lerobot]`) to gate on real-model ASR; see
[github-actions.yml](github-actions.yml) for the GPU job shape.
