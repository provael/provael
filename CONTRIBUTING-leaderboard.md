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

4. On merge, a maintainer rebuilds the published **real** board and the Space updates:

   ```bash
   # Stamps a UTC build date, the source commit, and a SHA-256 digest of the aggregated inputs.
   provael leaderboard build --real results/<your-name> --out leaderboard/results
   # The authoritative hosted board is additionally Ed25519-signed with the project key:
   provael leaderboard build --real results/<your-name> --sign --key provael-ed25519.pem \
       --out leaderboard/results
   ```

   `is_demo` clears automatically once any non-stub result is present, and each row is labelled
   `real-transfer` vs `stub-scaffolding` so a stub run is never silently mixed with a real one.
   Every row carries its 95% Wilson CI and the benign (`none`) control.

## Reproduce and verify a board

The board is reproducible from its inputs. Rebuild it and confirm the `inputs_digest` matches:

```bash
provael leaderboard build --real results/<name> --out /tmp/rebuild
python -c "import json; a=json.load(open('leaderboard/results/leaderboard.json'))['inputs_digest']; \
b=json.load(open('/tmp/rebuild/leaderboard.json'))['inputs_digest']; print('match:', a==b)"
```

If the board is signed, verify the signature offline (no network) against the published public key:

```bash
provael leaderboard verify --in leaderboard/results/leaderboard.json --pubkey leaderboard.pub
```

The date and commit are provenance metadata (a snapshot stamp); the `inputs_digest` and the row
numbers are what reproduce. This is **evidence, not certification**.

## The machine-checkable contract

Both artifacts have a published JSON Schema, so you can validate a submission before opening a PR
rather than discovering the shape from a review comment:

| artifact | schema |
|---|---|
| `report.json` | [`schemas/report.v4.schema.json`](https://raw.githubusercontent.com/provael/provael/main/schemas/report.v4.schema.json) |
| `leaderboard.json` | [`schemas/leaderboard.v5.schema.json`](https://raw.githubusercontent.com/provael/provael/main/schemas/leaderboard.v5.schema.json) |

```bash
pip install check-jsonschema
check-jsonschema --schemafile \
  https://raw.githubusercontent.com/provael/provael/main/schemas/report.v4.schema.json \
  runs/repro/report.json
```

They are **generated from the pydantic models**, not written by hand from example files, so they
describe the contract rather than describing whatever happens to be committed today. Every artifact
under `results/` and `leaderboard/` is validated against them in CI
(`tests/test_published_schemas.py`), including the schema-2 and schema-3 reports that predate the
current version — a `vN` schema accepts `N` or lower and refuses anything higher, so a tool that is
too old tells you so instead of silently passing.

## What the validator checks

- The file parses as a `RunReport`.
- ASR ∈ [0, 1]; `successes` ∈ [0, `attempts`].
- `attempts` equals the number of **applicable** episodes (not-applicable attacks are
  excluded from the denominator, never faked).
- `successes` matches the applicable successes in the per-episode results.
- Every result has an `attack` and `family`.
- **A stochastic policy recorded a `policy_seed`** — see below. Rejected outright, not warned.

## The seed your submission must carry

Every report has always recorded `seed`: the **environment** seed, the one `suite.reset(task,
seed)` uses. That is not the seed that made this board's numbers non-comparable.

Nothing ever seeded the **policy**. A flow-matching head like SmolVLA's draws its denoising noise
from the process's ambient torch RNG, so two runs at an identical config gave different answers —
an early pilot returned `goal_substitution` 1/4 on one run and 0/4 on the next. Two rows at the
same commit were therefore not comparable, which is most of what a leaderboard is for.

From report **schema 5** (provael 0.38.0) each episode also records **`policy_seed`**: the seed the
adapter reports it actually applied to the policy's own sampler, or `null` where the adapter cannot
seed it. The runner sets it for you — `PolicyAdapter.seed()` is called with the episode seed before
every rollout — so a submission produced by `provael attack` carries it without you doing anything.

**A submission from a `stochastic: true` policy at schema ≥ 5 with `policy_seed: null` on every
episode is refused.** Not a warning: an unseeded stochastic run is one draw, and a board of single
draws cannot support the comparison it exists for. Two ways to satisfy it:

- use an adapter that seeds itself (`smolvla`, `openvla`, and anything routed through the LeRobot
  path do);
- or submit a deterministic policy, which is not asked for a seed it does not have.

`openpi` is the honest exception: inference happens in a separate server process and its protocol
carries no seed field, so `PolicyAdapter.seed()` returns `null` there **with that reason recorded
in the adapter**. Those episodes really are one draw, and a submission of them will be refused
until the upstream protocol can carry a seed.

Reports predating schema 5 — including every result committed in this repository — are **accepted
with a named warning** rather than refused. The field did not exist when they were measured, and
refusing history would make the submission gate red from the day it landed and keep it red until a
GPU re-run nobody has scheduled. The same gap still reaches a consumer: a report old enough to
predate `policy_seed` is also old enough to push its board past `MAX_MINOR_LAG`, so the board's
`stale` flag fires independently.

Both seeds participate in `inputs_digest`, which the board signature covers — so changing either
one changes the digest, and a board cannot be re-signed over different seeds without saying so.

## Norms (please)

- **Reproducible & seeded.** Report the exact checkpoint, suite/tasks, seeds, and horizon.
- **Honest scope.** If you used a custom keep-out predicate or calibrated zones, say so.
- **No fabricated numbers.** Results may be independently re-run.

**If you are measuring a policy you did not train**, the same rule Provael holds itself to applies
to you: send the authors the full artifact and give them 14 days before the result goes public.
The commitment, and what happens when they disagree or do not reply, is written down in
[Measuring someone else's policy](https://docs.provael.com/leaderboard-disclosure/).

Questions or can't open a PR? Use the **Leaderboard submission** issue template.
