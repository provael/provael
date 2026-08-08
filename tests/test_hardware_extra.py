"""The `[hardware]` extra must be installable today, and must not leak into the sim path.

The extra exists so that the day an SO-101 arrives, `pip install 'provael[hardware]'` resolves
against the same pinned lerobot as the policy — rather than someone resolving a second environment
under time pressure with a robot on the bench. An extra that is declared but does not resolve buys
none of that, and the failure is invisible until the worst possible moment, so it is asserted here.

The separation is the other half. `feetech-servo-sdk` is a motor-bus driver. Someone installing
provael to red-team a policy in simulation should not end up with a package that can address a motor
bus, so `[hardware]` is its own extra and `[lerobot]` must never acquire the driver by drift.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: LeRobot's own extra for the STS3215 servo bus the SO-101 uses.
FEETECH = "feetech"
#: The distribution that extra pulls in, as resolved into uv.lock.
FEETECH_DIST = "feetech-servo-sdk"


def _pyproject() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _extras() -> dict[str, list[str]]:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    extras = project["optional-dependencies"]
    assert isinstance(extras, dict)
    return extras


def test_the_hardware_extra_is_declared_and_pins_the_servo_driver() -> None:
    extras = _extras()
    assert "hardware" in extras, (
        "the [hardware] extra is gone. The SO-101 path is then not installable, and "
        "results/hardware/README.md says it is."
    )
    spec = " ".join(extras["hardware"])
    assert FEETECH in spec, f"[hardware] no longer requests lerobot[{FEETECH}]: {spec!r}"


def test_the_sim_extra_never_acquires_a_motor_driver() -> None:
    """`[lerobot]` is the simulation path. A servo driver arriving here is the drift to catch."""
    spec = " ".join(_extras()["lerobot"])
    assert FEETECH not in spec, (
        f"[lerobot] now pulls lerobot[{FEETECH}] — a motor-bus driver on the simulation install "
        "path. Keep hardware deps in [hardware]; see results/hardware/README.md."
    )


def test_the_two_extras_pin_the_same_lerobot_version() -> None:
    """A hardware env resolving a different lerobot than the measured policy is a debugging trap.

    The 0.5.1 pin is load-bearing: lerobot_adapter.py's rollout was read off lerobot's evaluator for
    exactly that version. If the hardware extra drifts to another release, the arm and the published
    simulation number stop sharing an interpreter's worth of assumptions.
    """
    extras = _extras()

    def version(spec: str) -> str:
        return spec.split("==", 1)[1] if "==" in spec else ""

    lerobot = version(" ".join(extras["lerobot"]))
    hardware = version(" ".join(extras["hardware"]))
    assert lerobot and lerobot == hardware, (
        f"[lerobot] pins lerobot=={lerobot!r} but [hardware] pins {hardware!r}. "
        "The hardware study runs the policy behind the published simulation result; "
        "they must share the pin."
    )


def test_the_hardware_extra_actually_resolves() -> None:
    """Declared is not resolvable. `uv.lock` is the proof, and it is committed.

    Read from the lock rather than by installing: the driver's transitive tree is a GPU/ML stack and
    CPU CI must never pull it. If the lock is stale, `uv lock` regenerates it.
    """
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert f'name = "{FEETECH_DIST}"' in lock, (
        f"{FEETECH_DIST} is not in uv.lock, so `pip install 'provael[hardware]'` has never been "
        "shown to resolve. Run `uv lock` and commit the result."
    )


def test_the_hardware_extra_declares_its_conflict_with_openpi() -> None:
    """It inherits lerobot's numpy>=2.0 pin, so it collides with openpi-client's numpy<2.0.

    Without the declaration `uv lock` fails outright on the universal resolve — which is a loud
    failure, but one that reads as "the lockfile is broken" rather than "these two extras cannot
    share an environment, upstream".
    """
    uv = _pyproject()["tool"]
    assert isinstance(uv, dict)
    tool_uv = uv["uv"]
    assert isinstance(tool_uv, dict)
    pairs = [{e["extra"] for e in group} for group in tool_uv["conflicts"]]
    assert {"hardware", "openpi"} in pairs, (
        "[hardware] and [openpi] are no longer declared as conflicting; the universal lock will "
        "fail on numpy."
    )
