# MLOps — track ASR as a tracked metric

Log a Provael run's ASR to your experiment tracker so policy robustness is watched across
checkpoints, and gate model promotion on it.

| File | Tracker | Note |
| --- | --- | --- |
| [`mlflow_log_asr.py`](mlflow_log_asr.py) | MLflow | one emitter covers MLflow-compatible backends (incl. GitLab) |
| [`wandb_log_asr.py`](wandb_log_asr.py) | Weights & Biases | pair with a Registry threshold automation to block promotion |

Both run the CPU stub and print what they'd log if the tracker isn't installed:

```bash
pip install mlflow provael && python examples/mlops/mlflow_log_asr.py
```
