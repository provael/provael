# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The simulator and policy stack a run executed on, and how far it sits from the lock.

WHY THIS EXISTS. A LIBERO result is a measurement of the stack that ran, not only of the policy.
A comment on huggingface/lerobot#2354 (9 August 2026) reports that from mujoco 3.4.0 the stored
init states of libero_spatial task 5 no longer settle as they did, which would make one
``init_state`` index a different starting scene on two machines; provael has not measured that.
The GPU image installs whatever versions resolve on the day it is built, and until manifest
schema 4 no artifact said which versions ran.

So the execution manifest records :func:`installed_versions` for :data:`TRACKED_PACKAGES`, and
``provael attack`` and ``provael doctor`` print :func:`drift_warnings`: one line when a LIBERO run
uses mujoco 3.4.0 or newer, and one when an installed version differs from the ``[lerobot]``
resolution in ``uv.lock``. They are warnings, not refusals: a different stack is a different
measurement, and the reader of the manifest decides whether it is the one they wanted.

WHY A COPY OF THE LOCK. A wheel ships no ``uv.lock``, and the GPU container pip-installs a release,
so the resolution the warning compares against is copied into :data:`LOCKED_LEROBOT_RESOLUTION`.
``tests/test_runtime_versions.py`` parses ``uv.lock`` and fails when the two disagree, so the copy
cannot drift from the file it copies. Note that the lock itself resolves mujoco 3.8.1, past the
3.4.0 line, so a run on the locked stack gets the mujoco warning too.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

#: The packages whose versions change what a LIBERO run measures, in the order the manifest and
#: ``provael doctor`` list them.
TRACKED_PACKAGES: tuple[str, ...] = (
    "lerobot", "torch", "transformers", "mujoco", "robosuite", "hf-libero", "gymnasium", "numpy",
)

#: The ``[lerobot]`` extra's resolution in ``uv.lock`` for each tracked package (where a package
#: is locked at several versions, the one whose resolution markers name the ``lerobot`` extra).
#: A copy, kept equal to the lock by ``tests/test_runtime_versions.py``.
LOCKED_LEROBOT_RESOLUTION: dict[str, str] = {
    "gymnasium": "1.3.0",
    "hf-libero": "0.1.4",
    "lerobot": "0.5.1",
    "mujoco": "3.8.1",
    "numpy": "2.2.6",
    "robosuite": "1.4.0",
    "torch": "2.10.0",
    "transformers": "5.3.0",
}

#: The first mujoco release under which, per a comment on huggingface/lerobot#2354, the stored
#: libero_spatial task 5 init states no longer settle as before (reported there, not measured
#: here).
MUJOCO_SETTLING_CHANGE: tuple[int, int, int] = (3, 4, 0)

_RELEASE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def installed_versions(packages: Iterable[str] = TRACKED_PACKAGES) -> dict[str, str | None]:
    """Each package's installed version, read with ``importlib.metadata``; None if not installed."""
    from importlib import metadata

    out: dict[str, str | None] = {}
    for name in packages:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def release_of(version: str) -> tuple[int, int, int] | None:
    """The leading ``major.minor.micro`` of a version string (missing parts read as 0), or None."""
    match = _RELEASE.match(version.strip())
    if match is None:
        return None
    major, minor, micro = (int(part) if part is not None else 0 for part in match.groups())
    return major, minor, micro


def lock_drift(installed: Mapping[str, str | None]) -> dict[str, tuple[str, str]]:
    """``{package: (installed, locked)}`` for every installed tracked package off the lock.

    A package that is not installed is absent here rather than "drifted": the run either does not
    use it or fails to import it, and neither is a version difference.
    """
    out: dict[str, tuple[str, str]] = {}
    for name, locked in sorted(LOCKED_LEROBOT_RESOLUTION.items()):
        have = installed.get(name)
        if have is not None and have != locked:
            out[name] = (have, locked)
    return out


def drift_warnings(
    installed: Mapping[str, str | None], *, suite: str, uses_lerobot: bool
) -> list[str]:
    """The warning lines for a run on ``suite``: mujoco past the settling change on LIBERO, and
    versions off the ``[lerobot]`` lock when the run uses that stack (``uses_lerobot``)."""
    lines: list[str] = []
    mujoco = installed.get("mujoco")
    release = release_of(mujoco) if mujoco is not None else None
    if suite == "libero" and release is not None and release >= MUJOCO_SETTLING_CHANGE:
        lines.append(
            f"mujoco {mujoco} is installed. A comment on huggingface/lerobot#2354 reports that "
            "from mujoco 3.4.0 the stored libero_spatial task 5 init states no longer settle as "
            "they did (not measured here), so an init state index on this stack need not be the "
            "scene an older mujoco gave. The lock's [lerobot] resolution is mujoco "
            f"{LOCKED_LEROBOT_RESOLUTION['mujoco']}, past that line as well; "
            "execution-manifest.json records the versions that ran."
        )
    drift = lock_drift(installed) if uses_lerobot else {}
    if drift:
        listed = ", ".join(
            f"{name} {have} (lock {locked})" for name, (have, locked) in drift.items()
        )
        lines.append(
            f"installed versions differ from the [lerobot] resolution in uv.lock: {listed}. The "
            "run measures the stack that is installed; execution-manifest.json records it."
        )
    return lines


__all__ = [
    "LOCKED_LEROBOT_RESOLUTION",
    "MUJOCO_SETTLING_CHANGE",
    "TRACKED_PACKAGES",
    "drift_warnings",
    "installed_versions",
    "lock_drift",
    "release_of",
]
