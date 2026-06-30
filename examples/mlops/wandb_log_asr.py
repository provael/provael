"""Log a Provael run's ASR to Weights & Biases, with a promotion-gate note.

`run.log({"asr": ...})` plus a `wandb.Table` of per-attack results lets a W&B Registry automation
(metric-threshold webhook) **block model promotion** when ASR crosses a ceiling — the same gating
pattern teams already use for accuracy. See
https://docs.wandb.ai/guides/core/registry/model_registry/notifications/

    pip install wandb provael
    python examples/mlops/wandb_log_asr.py

On a box without wandb it prints what it would log instead of crashing.
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
    rows = [[n, s.successes, s.attempts, round(s.asr, 3)] for n, s in report.by_attack.items()]

    try:
        import wandb
    except ImportError:
        print("wandb not installed — would log asr=", round(report.asr, 3))
        for row in rows:
            print("  ", row)
        return

    wb = wandb.init(project="provael", name=f"{report.policy}-{report.suite}", reinit=True)
    wb.log({"asr": report.asr, "attempts": report.attempts})
    table = wandb.Table(columns=["attack", "successes", "attempts", "asr"], data=rows)
    wb.log({"by_attack": table})
    wb.finish()
    print(f"Logged {report.headline()} to W&B.")


if __name__ == "__main__":
    main()
