# Hugging Face Community Evals — the benchmark side

`provael export --format hf-eval` writes the **model-side** entries (`.eval_results/*.yaml`). The Hub
also needs a **benchmark dataset** carrying an `eval.yaml` before those entries render as a
leaderboard. This directory holds the files for that dataset, generated from the registry so the
benchmark declares every arm provael can measure:

```bash
uv run python - <<'PY'
from provael.attacks.registry import ATTACKS
from provael.hf_eval import benchmark_eval_yaml
print(benchmark_eval_yaml("libero", ["none", *ATTACKS], name="Provael LIBERO-Object red team", description="..."))
PY
```

Publishing it is a person's action, from a machine where `hf auth login` has run:

```bash
hf repo create Sattyam/provael-libero-object-redteam --repo-type dataset
hf upload Sattyam/provael-libero-object-redteam examples/hf-benchmark/provael-libero-object-redteam . --repo-type dataset
```

Two Hub-side steps remain outside this repo, and both are pull requests under a person's name:
`provael` must be added to the `evaluation_framework` enum in `huggingface.js`
(`packages/tasks/src/eval.ts`), and the Hugging Face team allow-lists the benchmark (the feature is
in beta; their docs say "get in touch"). Until both land, the entries still display on the model
page as community-provided results; only the benchmark leaderboard waits.
