# GPU CI — run the real model cheaply, fork-safely

Provael's core is CPU-tested in CI. The credibility move is a **real-model** job that's cheap and
can't be abused by fork PRs. [`modal_provael_gpu.py`](modal_provael_gpu.py) +
[`modal-gpu-tests.yml`](modal-gpu-tests.yml) run the real SmolVLA × LIBERO path on a Modal GPU
(~$0.01–0.02/run), triggered **only** when a maintainer adds the `gpu-tests` label to a PR.

```bash
pip install modal
modal run examples/gpu-ci/modal_provael_gpu.py
```

Set `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` as repo secrets for the Action. Nobody else in VLA
red-teaming ships a fork-safe real-model CI job at this price point.
