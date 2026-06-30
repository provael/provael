"""Log a Provael run's ASR to MLflow (track policy robustness over time).

`mlflow.log_metric("asr", ...)` makes ASR a first-class tracked metric, so you can watch a
policy's red-team robustness across checkpoints. GitLab and several other backends are
MLflow-Tracking-API compatible, so this one emitter covers many registries.

    pip install mlflow provael
    python examples/mlops/mlflow_log_asr.py

On a box without mlflow it prints the metrics it would log instead of crashing.
"""

from __future__ import annotations

from provael.config import RunConfig
from provael.runner import run


def main() -> None:
    report = run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=["instruction", "visual", "injection", "action"], episodes=10, seed=0,
        )
    )
    metrics = {"asr": report.asr, **{f"asr_{n}": s.asr for n, s in report.by_attack.items()}}
    tags = {"policy": report.policy, "suite": report.suite, "seed": "0"}

    try:
        import mlflow
    except ImportError:
        print("mlflow not installed — would log:")
        print("  metrics:", {k: round(v, 3) for k, v in metrics.items()})
        print("  tags:", tags)
        return

    with mlflow.start_run(run_name=f"provael-{report.policy}-{report.suite}"):
        mlflow.set_tags(tags)
        mlflow.log_metrics(metrics)
        mlflow.log_metric("attempts", report.attempts)
    print(f"Logged {report.headline()} to MLflow.")


if __name__ == "__main__":
    main()
