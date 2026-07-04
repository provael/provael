# Regression-gate a checkpoint update in CI

Block a pull request when a policy retrain makes it **more** attackable, the cheapest insurance a
team with no security headcount can buy. The pattern: run Provael on the new checkpoint, diff its
ASR against the last known-good baseline, fail the PR if it regressed.

"Regressed" is a real, statistical test, not a bare threshold. A slice (overall, per-EAI-risk, or
per-attack) regresses only when **both** hold:

1. the candidate ASR beats the baseline by more than `--regression-tolerance` (a point gate on
   noise), and
2. the two **95% Wilson confidence intervals are disjoint** in the worse direction.

So a wider-but-overlapping rise on a small sample shows as a delta but does not fail the build.

## The check

```bash
# 1. Run the gate recipe on the candidate checkpoint.
provael attack --recipe regression-gate --format scorecard --out runs/candidate

# 2. Diff overall + per-EAI ASR against the committed baseline. Exits non-zero on a regression.
provael report --in runs/candidate \
  --baseline .provael/baseline.report.json \
  --regression-tolerance 0.05 \
  --out runs/candidate/regression.json \
  --sarif-out runs/candidate/regression.sarif
```

Step 1 also writes `runs/candidate/report.scorecard.md` (the one-page PR artifact). Step 2 prints a
diff table, writes a machine-readable `regression.json` and a `regression.sarif` (regressed EAI
families become error-level code-scanning findings), and returns a non-zero exit if the candidate
regressed. For a hard ceiling instead of a delta, keep gating on the scorecard verdict too:
`provael report --in runs/candidate --format scorecard --threshold 0.5`.

## GitHub Actions

Use the reusable Action, which runs the attack, diffs against the baseline, uploads both SARIFs, and
fails on either the absolute threshold or a regression. A complete consumer workflow is in
[regression-gate.yml](regression-gate.yml):

```yaml
- uses: provael/provael@v0.8.0
  with:
    baseline: .provael/baseline.report.json   # the last known-good report.json
    regression-tolerance: "0.05"
    fail-on-regression: "true"
    asr-threshold: "0.9"                       # the absolute ceiling still applies
```

The Action exposes `regressed` and `asr-delta` outputs and writes the per-family diff into the job
summary.

## How to store and roll the baseline

The baseline is just a committed `report.json` from the last checkpoint you accepted.

- **Store it in-repo** at a stable path (e.g. `.provael/baseline.report.json`) so `actions/checkout`
  brings it into the runner. This keeps the gate hermetic and reviewable in the PR diff.
  (Alternatively, download it from a release asset or an artifact store into that path before the
  Action runs.)
- **Roll it deliberately.** When an ASR change is real and intended (you accept the new checkpoint),
  regenerate and commit the baseline in the same PR, so the reviewer sees the number move:

  ```bash
  provael attack --policy stub --suite stub \
    --attacks instruction,visual,injection,action --episodes 10 --seed 0 --out runs/new
  cp runs/new/report.json .provael/baseline.report.json
  git add .provael/baseline.report.json && git commit -m "chore: roll Provael baseline"
  ```

Keep the baseline's `policy`, `suite`, `attacks`, `episodes`, and `seed` identical to the gate run,
so the diff compares like with like.

The default `stub` policy runs on a CPU runner (a smoke test of the gate wiring). Point it at a real
policy (`--policy smolvla --suite libero`, GPU + `[lerobot]`) to gate on real-model ASR; see
[github-actions.yml](github-actions.yml) for the GPU job shape.

> This is **evidence**, not certification. Per-checkpoint regression evidence maps to standing
> assurance expectations (e.g. EU Machinery Regulation 2023/1230 Annex III §1.1.9 on safe behaviour
> across updates), but it is not a conformity statement. The real-VLA (GPU) transfer run behind the
> gate is the open-core paid surface.
