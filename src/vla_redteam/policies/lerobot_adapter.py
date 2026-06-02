"""Adapter for real VLA policies loaded through LeRobot (e.g. SmolVLA).

DESIGN: this module imports **no** optional dependency at module scope, so the core
package stays importable on a plain CPU with the ``[lerobot]`` extra absent. All
contact with ``lerobot`` / ``torch`` happens inside :meth:`LeRobotAdapter.load`,
which raises a clear, actionable error when the extra is missing.

The model-loading and action-selection internals (:meth:`_build` and the body of
:meth:`act`) are filled in during milestone M5 **after** introspecting the actually
installed ``lerobot`` package — we do not guess its API. Until verified on a machine
where ``lerobot`` is installed, those paths raise an explicit error pointing at the
verification command. On this CPU build the dependency guard fires first, so the
unverified paths are never reached.

Enable the real path on a GPU box::

    pip install 'vla-redteam[lerobot]'
    ROBOPWN_INTEGRATION=1 pytest tests/test_lerobot_adapter.py -q
"""

from __future__ import annotations

import importlib.util

from vla_redteam.policies.base import PolicyAdapter
from vla_redteam.types import Action, Observation

_INSTALL_HINT = (
    "The '{name}' policy requires the optional LeRobot dependency, which is not "
    "installed.\n"
    "  1. Install the extra:  pip install 'vla-redteam[lerobot]'\n"
    "     (LeRobot needs Python >=3.12 and is intended for a GPU machine.)\n"
    "  2. For the LIBERO env, follow LeRobot's official LIBERO install "
    "(its '[libero]' extra and the documented numpy pin).\n"
    "  3. Enable the gated integration path:  ROBOPWN_INTEGRATION=1\n"
    "Run on CPU with '--policy stub' to exercise the full pipeline with no model."
)


class MissingLeRobotError(RuntimeError):
    """Raised when a LeRobot-backed policy is used without the ``[lerobot]`` extra."""


class LeRobotAdapter(PolicyAdapter):
    """Loads a LeRobot policy (default: ``lerobot/smolvla_base``) and runs it.

    On construction nothing heavy happens. :meth:`load` performs the guarded import
    and (on a properly provisioned machine) builds the policy + processors.
    """

    def __init__(
        self,
        model_id: str = "lerobot/smolvla_base",
        name: str = "smolvla",
        device: str = "cuda",
    ) -> None:
        self.model_id = model_id
        self.name = name
        self.device = device
        self._policy: object | None = None
        self._preprocessor: object | None = None
        self._postprocessor: object | None = None
        self._loaded = False

    # -- availability -------------------------------------------------------

    @staticmethod
    def lerobot_available() -> bool:
        """True if ``lerobot`` is importable without importing it."""
        return importlib.util.find_spec("lerobot") is not None

    # -- lifecycle ----------------------------------------------------------

    def load(self) -> None:
        """Import lerobot (guarded) and build the policy.

        Raises:
            MissingLeRobotError: if the ``[lerobot]`` extra is not installed.
        """
        if not self.lerobot_available():
            raise MissingLeRobotError(_INSTALL_HINT.format(name=self.name))
        self._build()
        self._loaded = True

    def _build(self) -> None:
        """Construct the policy and pre/post processors from verified lerobot symbols.

        Implemented in milestone M5 against the *introspected* lerobot API (see the
        module docstring). Kept as an explicit failure until then so no fabricated
        API call can slip through untested.
        """
        raise NotImplementedError(
            "LeRobotAdapter._build is finalised in milestone M5 against the verified "
            "lerobot API. Run the introspection/verification commands in the README "
            "'GPU / SmolVLA path' section, then enable with ROBOPWN_INTEGRATION=1."
        )

    def act(self, observation: Observation, instruction: str) -> Action:
        """Select an action from the loaded policy. Finalised in M5 (verified API)."""
        if not self._loaded:
            raise RuntimeError("LeRobotAdapter.act called before load(); call load() first.")
        raise NotImplementedError(
            "LeRobotAdapter.act is finalised in milestone M5 against the verified "
            "lerobot select_action API."
        )


__all__ = ["LeRobotAdapter", "MissingLeRobotError"]
