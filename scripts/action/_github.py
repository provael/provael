"""The three ways a GitHub Action step talks to the job around it, in one place.

WHY A HELPER RATHER THAN os.environ AT EACH SITE. All three channels fail the same way — the
environment variable is absent when the script runs outside Actions — and each of the five action
scripts had its own answer. :func:`emit` used to be a bare ``print`` captured by a shell
redirection in one step and a direct ``GITHUB_OUTPUT`` append in another; the two disagreed about
what happens when the variable is missing, which is exactly the case every local test hits.

Absent means "not running under Actions", which is not an error: the value still goes to stdout so
a human or a test can read it. That is what makes these scripts runnable outside CI at all.
"""

from __future__ import annotations

import os
from pathlib import Path


def emit(**values: object) -> None:
    """Publish step outputs as ``key=value``, both to the log and to ``$GITHUB_OUTPUT``.

    ``None`` is written as the EMPTY STRING, deliberately and load-bearingly. Downstream gates read
    an empty output as "nothing was measured" and fail closed; writing the literal ``"None"`` would
    be a non-empty string that ``float()`` then dies on, turning a fail-closed gate into a crash.
    """
    lines = [f"{k}={'' if v is None else v}" for k, v in values.items()]
    for line in lines:
        print(line)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("".join(f"{line}\n" for line in lines))


def summary(markdown: str) -> None:
    """Append to the job summary, or do nothing when not running under Actions."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown)


def error(message: str) -> None:
    """A GitHub error annotation — surfaces on the PR at the step, not just in the log."""
    print(f"::error::{message}")


def notice(message: str) -> None:
    print(f"::notice::{message}")


def load(path: str | Path) -> dict:  # type: ignore[type-arg]
    """Read a JSON artifact, failing with the PATH in the message rather than a bare traceback."""
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"::error::expected artifact not found: {p}")
    import json

    return json.loads(p.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
