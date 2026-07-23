"""provael (Provael) — red-team open Vision-Language-Action robot policies.

A model-agnostic harness that perturbs the instructions/observations fed to a VLA
policy inside a simulator and measures how often those perturbations drive the
policy into an *unsafe* state. The headline metric is the Attack Success Rate (ASR).

The core (abstractions, attacks, scoring, runner, report, CLI) runs on a plain CPU
with no GPU and no model/dataset download, using a deterministic StubPolicy and
StubSuite. Real VLA policies (e.g. SmolVLA via LeRobot) live behind the optional
``provael[lerobot]`` extra and are gated behind ``PROVAEL_INTEGRATION=1``.
"""

__version__ = "0.22.0"
