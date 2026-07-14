"""Emit a CycloneDX ML-BOM for a red-teamed policy (audit evidence for the AI Act file).

A CycloneDX ML-BOM (https://cyclonedx.org/capabilities/mlbom/) is the standard machine-readable
record of a model — its identity, what it was evaluated on, and its metrics. This uses the core
``provael.mlbom`` exporter, which attaches the ASR (with its Wilson CI, the benign-FPR control, and
the honest transfer-status label) as model-card metrics and maps them onto EU AI Act Art. 11 —
tying the red-team result into the same supply-chain evidence auditors already ingest (OWASP
Dependency-Track). Equivalent to ``provael attack --format mlbom``.

    python examples/supply-chain/mlbom_emit.py        # writes provael.mlbom.json
"""

from __future__ import annotations

from pathlib import Path

from provael.config import RunConfig
from provael.mlbom import write_ml_bom
from provael.runner import run


def main() -> None:
    report = run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=["instruction", "visual", "injection", "action"], episodes=10, seed=0,
        )
    )
    out = write_ml_bom(report, Path("provael.mlbom.json"))
    print(f"Wrote {out} (ASR={round(report.asr, 4)}). Ingest into OWASP Dependency-Track.")


if __name__ == "__main__":
    main()
