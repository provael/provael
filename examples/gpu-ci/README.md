# GPU CI — run the real model cheaply, fork-safely

Provael's core is CPU-tested in CI. The credibility move is a **real-model** job that's cheap and
can't be abused by fork PRs. [`modal_provael_gpu.py`](modal_provael_gpu.py) +
[`modal-gpu-tests.yml`](modal-gpu-tests.yml) run the real SmolVLA × LIBERO path on a Modal GPU,
triggered **only** when a maintainer adds the `gpu-tests` label to a PR. **Cost, measured, not
estimated:** the lane's canary (16 episodes at `--seeds 2`) runs about 37 minutes on one L4 and
costs about **$0.49** — the "~$0.02/run" this page and two others advertised until 0.38.1 was an
estimate that had never been run, corrected the day the lane was enabled
([CHANGELOG 0.38.1](../../CHANGELOG.md#0381--2026-08-31)). Scale it by episodes: the repo's own
anchor is ~139 s per LIBERO episode on an L4.

```bash
pip install modal
modal run examples/gpu-ci/modal_provael_gpu.py
```

Set `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` as repo secrets for the Action.

## Same protocol on one machine you already have

[`local_libero_sweep.py`](local_libero_sweep.py) runs the identical sharded screen on a single
Linux GPU box (WSL2 included), N tasks at a time, with the same per-task `report.json` shards,
`--resume` ledgers and cross-shard `aggregate.json` as the Modal recipe — so a workstation run and
a Modal run are the same experiment in two places. `--parallel` is a measured knob: one SmolVLA
process left an RTX 2000 Ada 25–44 % busy, three took it to 99 %. Pass `--commit` so the execution
manifests name the installed release's source commit instead of `null`.

```bash
python examples/gpu-ci/local_libero_sweep.py launch --out ~/data/runs/smolvla-obj --parallel 3 --commit <sha>
python examples/gpu-ci/local_libero_sweep.py status --out ~/data/runs/smolvla-obj
python examples/gpu-ci/local_libero_sweep.py aggregate --out ~/data/runs/smolvla-obj
```
