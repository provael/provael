# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every Modal GPU image must install a provael release this checkout can account for.

WHY THIS EXISTS. Both GPU lanes were wrong, in opposite directions, and both looked healthy:

* `examples/gpu-ci/modal_libero_suite.py` pinned a commit — `5d34472`, v0.32.0, 9 August 2026 —
  and carried a comment telling the maintainer to "bump this deliberately when a stage needs newer
  code". Five releases went by. On 6 September 2026 the ~$5 `calibrate` arm fitted all ten
  `libero_object` keep-out zones on that build, wrote `tool_version: 0.32.0` truthfully, and
  succeeded. Nothing warned, because a stale pin and a fresh pin are the same shape.
* `examples/gpu-ci/modal_provael_gpu.py` pinned nothing at all, so the scheduled canary installed
  whatever PyPI served that morning. It resolved 0.39.1 the same week.

So the two lanes were measuring builds five releases apart while both reported success, and the
only way to see it was to read a SHA and resolve it by hand.

WHAT IS ASSERTED, and why each line is a separate way this rots:

1. Every lane declares `PROVAEL_PIN`. A lane that quietly drops the constant would pass a test
   that only checked the lanes it knows about.
2. The pin names a version this checkout can account for. It used to have to EQUAL
   `provael.__version__`, and that was the right rule for a canary and the wrong rule for a
   campaign: the scheduled lane builds one body of measurement at one version until that body
   supersedes the published measurement (see `provael.watch.displacement`), and bumping the pin
   on every release reset the body before it could — the arithmetic that kept the published
   measurement frozen at 0.32.0. So since 18 September 2026 a pin may be the current version, OR
   the version of the re-measurement in progress (the artifact's `challenger`), OR the published
   measurement's version while it is still inside the release window. Anything else fails, with
   the reason and the number it was accumulating toward. `test_lanes_pin_the_same_version` holds
   the property the old rule was really protecting: no two lanes on different builds.
3. The pin is an exact version, never a range or a URL. `>=` in a GPU image is the unpinned bug
   with extra characters.
4. No lane still installs `provael` unconstrained or from git. This is the mutation guard: the
   assertions above all read `PROVAEL_PIN`, so a file that declares a correct pin and then
   installs something else entirely would satisfy every one of them.

PARSED WITH `ast`, NOT IMPORTED. `modal` is not a test dependency and never should be — these
files import it at module scope, so importing them here would either fail or drag a cloud client
into the CPU test environment.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from provael import __version__
from provael.watch import STALE_AFTER_RELEASES, displacement, releases_behind

REPO = Path(__file__).resolve().parents[1]
GPU_CI = REPO / "examples" / "gpu-ci"

#: Every Modal entry point that builds an image. Discovered rather than listed, so a new lane is
#: covered the day it lands instead of the day someone remembers to add it here.
LANES = sorted(p for p in GPU_CI.glob("modal_*.py"))

_EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def _module_constants(path: Path) -> dict[str, str]:
    """Top-level `NAME = "literal"` assignments, by name. Non-literals are skipped."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                found[target.id] = node.value.value
    return found


def test_there_are_lanes_to_check() -> None:
    """A discovery bug that found nothing would make every test below vacuously pass."""
    assert LANES, f"no modal_*.py under {GPU_CI} — the discovery glob is wrong, not the lanes"


@pytest.mark.parametrize("lane", LANES, ids=lambda p: p.name)
def test_lane_declares_a_pin(lane: Path) -> None:
    assert "PROVAEL_PIN" in _module_constants(lane), (
        f"{lane.name} builds a Modal image without declaring PROVAEL_PIN, so nothing can check "
        "which provael it installs"
    )


@pytest.mark.parametrize("lane", LANES, ids=lambda p: p.name)
def test_pin_is_an_exact_version(lane: Path) -> None:
    pin = _module_constants(lane)["PROVAEL_PIN"]
    assert _EXACT_VERSION.match(pin), (
        f"{lane.name} pins {pin!r}, which is not an exact version. A range or a URL in a GPU image "
        "is the unpinned bug with extra characters."
    )


def allowed_pins() -> dict[str, str]:
    """The versions a lane may pin right now, each with the reason it is allowed.

    Derived from the committed ledger, never from a list: the current version is always allowed;
    the challenger's version is allowed because a campaign is accumulating there and a bump would
    abandon it; the published measurement's version is allowed only while it is inside the
    release window, which is the grace a completed campaign gets before the pin has to move on.
    """
    allowed = {__version__: "this checkout's version"}
    standing = displacement()
    if standing is None:
        return allowed
    if standing.challenger is not None:
        body = standing.challenger
        allowed.setdefault(
            body.tool_version,
            f"the re-measurement in progress: {body.attempts} of {standing.published.attempts} "
            f"attempts over {len(body.tasks or ())} of {len(standing.published.tasks or ())} "
            "tasks, and a bump would abandon it",
        )
    gap = releases_behind(standing.published.tool_version, __version__)
    if gap is not None and gap <= STALE_AFTER_RELEASES:
        allowed.setdefault(
            standing.published.tool_version,
            f"the published measurement, {gap} release(s) behind and inside the "
            f"{STALE_AFTER_RELEASES}-release window",
        )
    return allowed


@pytest.mark.parametrize("lane", LANES, ids=lambda p: p.name)
def test_pin_is_a_version_this_checkout_can_account_for(lane: Path) -> None:
    """The release-blocking assertion, with the campaign exception written in.

    A pin at the current version is always right. A pin at the challenger's version is a campaign
    in progress and must NOT be bumped by a release PR — the body it is building resets to nothing.
    A pin at the published measurement's version is a campaign that just finished; it may stay
    until the window closes, then it has to advance so the next campaign starts on current code.
    """
    pin = _module_constants(lane)["PROVAEL_PIN"]
    allowed = allowed_pins()
    assert pin in allowed, (
        f"{lane.name} pins provael {pin}, and this checkout can account for none of that: it is "
        f"{__version__}, and the committed ledger allows "
        + "; ".join(f"{v} ({why})" for v, why in allowed.items())
        + f". A GPU arm run now would measure {pin} and its artifacts would say so, while "
        f"everything around it claims {__version__}. Bump PROVAEL_PIN in {lane.name} to "
        f"{__version__} — the pinned version has to exist on PyPI before the image can build, so "
        "release first — unless a campaign is accumulating at the pin, in which case the ledger "
        "would have listed it above."
    )


def test_lanes_pin_the_same_version() -> None:
    """Two lanes on two builds is the original incident, whatever each pin is allowed to be.

    On 6 September 2026 the canary resolved 0.39.1 while the measurement arm fitted zones on
    0.32.0, and both looked healthy. The campaign rule above lets a pin lag the release; it must
    never let the lanes lag EACH OTHER, or a manual arm run against the campaign pin would land in
    a different body from the slices it was meant to add to.
    """
    pins = {lane.name: _module_constants(lane)["PROVAEL_PIN"] for lane in LANES}
    assert len(set(pins.values())) == 1, (
        f"the GPU lanes pin different provael releases: {pins}. Every lane installs the same "
        "build, so a manual arm and the scheduled slices measure one body, not two."
    )


def test_the_campaign_exception_is_not_a_blanket_one() -> None:
    """Guard the guard: `allowed_pins` must be a short, derived list, never every version."""
    allowed = allowed_pins()
    assert __version__ in allowed
    assert len(allowed) <= 3, f"allowed_pins() returned {allowed}; it should name at most three"
    assert "0.0.0" not in allowed and "0.1.0" not in allowed


def _pip_install_args(path: Path) -> list[tuple[int, ast.expr]]:
    """Every argument passed to a `.pip_install(...)` call, with its line number.

    Scoped to the install site on purpose. An earlier version of this guard grepped the whole file
    for the literal `"provael"` and failed on `["provael", "attack", ...]` — the argv the container
    runs, which has nothing to do with what the image installs. A guard that cries wolf on the
    correct line is a guard that gets deleted.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    args: list[tuple[int, ast.expr]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "pip_install"
        ):
            args.extend((arg.lineno, arg) for arg in node.args)
    return args


@pytest.mark.parametrize("lane", LANES, ids=lambda p: p.name)
def test_provael_is_installed_only_through_the_pin(lane: Path) -> None:
    """The mutation guard: a correct PROVAEL_PIN beside a wrong install is still unpinned.

    Every assertion above reads the constant. A lane that declares the right pin and then calls
    `.pip_install("provael[lerobot]")` — the exact line this change removed from the canary —
    satisfies all of them and installs whatever PyPI serves. So check the install site itself:
    within `pip_install`, provael may only be named by an expression built from `PROVAEL_PIN`,
    never by a bare string literal.
    """
    offenders: list[str] = []
    for lineno, arg in _pip_install_args(lane):
        if (
            isinstance(arg, ast.Constant)
            and isinstance(arg.value, str)
            and "provael" in arg.value.lower()
        ):
            offenders.append(f"{lane.name}:{lineno} installs the literal {arg.value!r}")
    assert not offenders, (
        "\n".join(offenders)
        + "\n\nA literal provael spec inside pip_install is unpinned, or pinned to a commit that "
        "nothing can check against __version__. Build the spec from PROVAEL_PIN instead."
    )


@pytest.mark.parametrize("lane", LANES, ids=lambda p: p.name)
def test_the_pin_actually_reaches_pip_install(lane: Path) -> None:
    """...and the converse: declaring PROVAEL_PIN is worthless if nothing installs from it.

    Without this, deleting the `.pip_install(PROVAEL, ...)` argument entirely leaves a file that
    declares a perfectly current pin, installs no provael at all, and passes every other test here.
    """
    names: set[str] = set()
    for _, arg in _pip_install_args(lane):
        names.update(n.id for n in ast.walk(arg) if isinstance(n, ast.Name))
    assert "PROVAEL" in names or "PROVAEL_PIN" in names, (
        f"{lane.name} declares PROVAEL_PIN but no pip_install argument derives from it, so the "
        "pin describes an install that is not happening"
    )
