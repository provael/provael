"""A garak-style probe/detector pair that runs Provael's embodied scan.

garak (https://github.com/NVIDIA/garak) is *the* LLM vulnerability scanner — a plugin model of
probes (attacks) + detectors (scorers) + generators (targets). garak covers LLM/agent text I/O;
it has nothing for an action policy. This reference plugin shows the shape of a Provael probe that
brings the *action-space* dimension into a garak run.

STATUS: this is a **reference integration** written against garak's documented plugin shape
(`garak.probes.base.Probe` / `garak.detectors.base.Detector`). It is NOT validated against an
installed garak in this repo's CI — confirm the base-class hooks against your garak version before
relying on it. The Provael call itself (``run(...)`` -> ASR) is the same one the rest of Provael
unit-tests, so the embodied measurement is real even though the garak glue is unverified here.

Drop this on garak's plugin path and select it:

    garak --model_type test.Blank --probes provael_garak.ProvaelEmbodiedProbe
"""

from __future__ import annotations

from typing import Any

from provael.config import RunConfig
from provael.runner import run

try:  # garak is optional — import lazily so this file is importable without it.
    from garak.probes.base import Probe as _GarakProbe
except Exception:  # noqa: BLE001 - garak not installed; provide a stand-in base for reference use
    class _GarakProbe:  # type: ignore[no-redef]
        """Stand-in base used when garak is not installed (keeps this file importable)."""


class ProvaelEmbodiedProbe(_GarakProbe):
    """Runs Provael's four attack families against a (stub by default) VLA policy.

    In a real garak deployment the probe yields prompts and the paired detector scores responses;
    here the 'attack' is Provael's own simulation loop, so the probe runs the scan and surfaces the
    per-EAI ASR as the finding. Configure via the class attributes below.
    """

    bcp47 = "en"
    goal = "drive an embodied VLA policy into an unsafe action via templated attacks"
    policy = "stub"
    suite = "stub"
    attacks = ("instruction", "visual", "injection", "action")
    episodes = 10

    def run_scan(self) -> dict[str, Any]:
        """Run Provael and return the per-EAI ASR (the bridge point for a garak detector)."""
        report = run(
            RunConfig(
                policy=self.policy, suite=self.suite, attacks=list(self.attacks),
                episodes=self.episodes, seed=0,
            )
        )
        return {
            "asr": report.asr,
            "headline": report.headline(),
            "by_attack": {n: s.asr for n, s in report.by_attack.items()},
        }


if __name__ == "__main__":
    print(ProvaelEmbodiedProbe().run_scan()["headline"])
