"""Emit a CycloneDX ML-BOM for a red-teamed policy (audit evidence for the AI Act file).

A CycloneDX ML-BOM (spec 1.7) is the standard machine-readable record of a model — its identity,
the datasets/benchmarks it was evaluated on, and metrics. Attaching the Provael ASR as a metric in
an ML-BOM ties the red-team result into the same supply-chain evidence auditors already ask for
(it ingests into OWASP Dependency-Track). https://cyclonedx.org/capabilities/mlbom/

    python examples/supply-chain/mlbom_emit.py        # writes provael.mlbom.json

This writes the JSON directly (no extra deps); `cdxgen` / cyclonedx libraries can consume or
extend it.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael import __version__
from provael.config import RunConfig
from provael.runner import run


def main() -> None:
    model_id = "lerobot/smolvla_base"
    report = run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=["instruction", "visual", "injection", "action"], episodes=10, seed=0,
        )
    )
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "components": [
            {
                "type": "machine-learning-model",
                "name": model_id,
                "modelCard": {
                    "quantitativeAnalysis": {
                        "performanceMetrics": [
                            {
                                "type": "attack-success-rate",
                                "value": round(report.asr, 4),
                                "slice": f"provael:{report.suite}",
                            }
                        ]
                    }
                },
                "properties": [
                    {"name": "provael:version", "value": __version__},
                    {"name": "provael:attempts", "value": str(report.attempts)},
                ],
            }
        ],
    }
    out = Path("provael.mlbom.json")
    out.write_text(json.dumps(bom, indent=2), encoding="utf-8")
    print(f"Wrote {out} (ASR={round(report.asr, 4)}). Ingest into OWASP Dependency-Track.")


if __name__ == "__main__":
    main()
