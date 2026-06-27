# Submitting to the Provael leaderboard

The [leaderboard](https://huggingface.co/spaces/Sattyam/provael-leaderboard) aggregates
real `(policy × suite × family) → ASR` results. Anyone can add a result via a pull request —
CI validates it automatically.

## How to submit (pull request)

1. **Run an attack** on your policy, including the `none` baseline (so we can read *lift*):

   ```bash
   pip install 'provael[lerobot]' 'lerobot[libero]==0.5.1'
   export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa   # headless rendering
   provael attack --policy smolvla --suite libero --model <your-checkpoint> \
       --attacks none,instruction,visual,injection --seeds 10 --horizon 280 --seed 0 \
       --out results/<your-name>            # writes results/<your-name>/report.json
   ```

2. **Validate locally** (same check CI runs):

   ```bash
   python scripts/validate_submission.py 'results/*'
   ```

3. **Open a PR** adding `results/<your-name>/report.json`. The **Leaderboard submission**
   workflow validates the report and confirms the leaderboard still builds. In the PR
   description, note the checkpoint, suite/task(s), seeds, horizon, and hardware.

4. On merge, a maintainer rebuilds the published board
   (`provael leaderboard build --runs 'results/*' --out leaderboard/results`) and the Space
   updates. (`is_demo` clears automatically once any non-stub result is present.)

## What the validator checks

- The file parses as a `RunReport`.
- ASR ∈ [0, 1]; `successes` ∈ [0, `attempts`].
- `attempts` equals the number of **applicable** episodes (not-applicable attacks are
  excluded from the denominator, never faked).
- `successes` matches the applicable successes in the per-episode results.
- Every result has an `attack` and `family`.

## Norms (please)

- **Reproducible & seeded.** Report the exact checkpoint, suite/tasks, seeds, and horizon.
- **Honest scope.** If you used a custom keep-out predicate or calibrated zones, say so.
- **No fabricated numbers.** Results may be independently re-run.

Questions or can't open a PR? Use the **Leaderboard submission** issue template.
