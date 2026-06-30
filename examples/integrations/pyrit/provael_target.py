"""A PyRIT-style target that runs Provael's embodied scan (reference integration).

Microsoft PyRIT (https://github.com/Azure/PyRIT) — "Metasploit for LLMs" — orchestrates attacks
against *targets*. This reference target lets a PyRIT pipeline include Provael's embodied VLA scan,
extending PyRIT from text targets to an action policy.

STATUS: reference integration. The Provael measurement (`run(...)` → ASR) is the same code Provael
unit-tests; the PyRIT base-class glue is written against PyRIT's documented `PromptTarget` shape
and is NOT validated against an installed PyRIT in this repo's CI. This file is importable with or
without PyRIT installed.
"""

from __future__ import annotations

from provael.config import RunConfig
from provael.runner import run


def scan(policy: str = "stub", suite: str = "stub", episodes: int = 10) -> str:
    """Run Provael and return the headline ASR — the value a PyRIT target would surface."""
    report = run(
        RunConfig(
            policy=policy, suite=suite,
            attacks=["instruction", "visual", "injection", "action"], episodes=episodes, seed=0,
        )
    )
    return report.headline()


try:  # PyRIT is optional — only define the real target when it's installed.
    from pyrit.models import PromptRequestResponse, construct_response_from_request
    from pyrit.prompt_target import PromptTarget

    class ProvaelTarget(PromptTarget):  # pragma: no cover - requires PyRIT installed
        """A PyRIT PromptTarget whose 'response' is a Provael embodied-scan headline."""

        def __init__(self, policy: str = "stub", suite: str = "stub") -> None:
            super().__init__()
            self._policy = policy
            self._suite = suite

        async def send_prompt_async(
            self, *, prompt_request: PromptRequestResponse
        ) -> PromptRequestResponse:
            request = prompt_request.request_pieces[0]
            text = scan(self._policy, self._suite)
            return construct_response_from_request(request=request, response_text_pieces=[text])

        def _validate_request(self, *, prompt_request: PromptRequestResponse) -> None:
            return None

except Exception:  # noqa: BLE001 - PyRIT not installed; the `scan` helper still works
    pass


if __name__ == "__main__":
    print(scan())
