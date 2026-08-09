"""The badge's reader and the run's writer must agree on ONE filename, in ONE place.

WHAT WENT WRONG, and it is worth stating because the code was not the bug. `provael attack` writes
`execution-manifest.json` beside `report.json` (cli.py `_emit_execution_manifest`), and
:func:`provael.watch.measurements_from_results` reads exactly that name. Both halves were correct.

The suite result was committed with the reports and WITHOUT the manifests, because the artifacts
were copied out of a remote volume by hand and the copy only took `report.json`. The badge then did
the only honest thing available: it reported the single manifest still in the tree, an old one whose
`ended_at` is exact midnight UTC — a typed date, not an observed one — and rendered red saying so.

So the failure was not a wrong date, and not a silent guess either: the badge said
"(date reconstructed)" and set `isError`. The failure was a result directory that LOOKS complete —
report, numbers, statistics — while carrying no provenance. Nothing failed and nothing warned, so
the badge aged for two months with a same-day measurement sitting in the repo.

WHY STUB RESULTS ARE EXEMPT. A stub run is a fixture, not a measurement: it is a pure function of
its config, byte-identical on every machine, and dating it answers nothing. Only a real-policy
result is a measurement whose age means something, so only those are required to carry provenance.
The exemption is an explicit list rather than a `policy == "stub"` rule alone, so that adding a
fourth undated directory is a deliberate act with a diff, not an accident.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from provael.watch import EXECUTION_MANIFEST, REPORT, RESULTS_DIR, measurements_from_results

#: Committed stub/CPU fixtures that predate this guard and legitimately carry no provenance. They
#: cannot be retro-stamped: inventing an `ended_at` for them would fabricate the exact thing the
#: freshness badge exists to report honestly. Adding to this list should require a reason.
UNDATED_STUB_FIXTURES = {
    "results/cross_arch_transfer/stub",
    "results/eai04_action_space_transfer/reach",
    "results/optimized_targeted_hijack_stub",
}


def _result_dirs() -> list[Path]:
    """Every committed directory holding a report — i.e. every published run."""
    if not RESULTS_DIR.is_dir():
        return []
    return sorted(p.parent for p in RESULTS_DIR.rglob(REPORT))


def _rel(path: Path) -> str:
    return path.relative_to(RESULTS_DIR.parent).as_posix()


def _is_real_policy(result_dir: Path) -> bool:
    """True when the report claims a real policy, which is what makes its age worth reporting."""
    try:
        report = json.loads((result_dir / REPORT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return str(report.get("policy", "")) != "stub"


def test_there_are_committed_results_to_check() -> None:
    """Guard the guard: an empty sweep makes every assertion below vacuously true."""
    assert _result_dirs(), f"no {REPORT} found under {RESULTS_DIR}"


@pytest.mark.parametrize(
    "result_dir", [d for d in _result_dirs() if _is_real_policy(d)], ids=_rel
)
def test_every_real_policy_result_ships_its_execution_manifest(result_dir: Path) -> None:
    """A real measurement without provenance cannot date itself, so the badge cannot see it.

    This is the exact omission that left the badge red for two months while a same-day measurement
    sat in the repo: ten report.json files committed, zero manifests.
    """
    manifest = result_dir / EXECUTION_MANIFEST
    assert manifest.is_file(), (
        f"{_rel(result_dir)} has {REPORT} for a real policy but no {EXECUTION_MANIFEST}. The "
        f"report is deterministic and deliberately carries no timestamp, so without the manifest "
        f"this measurement is invisible to the freshness badge and cannot be dated by anything."
    )


@pytest.mark.parametrize(
    "result_dir", [d for d in _result_dirs() if _is_real_policy(d)], ids=_rel
)
def test_real_policy_manifests_carry_a_usable_end_time(result_dir: Path) -> None:
    """`ended_at` is the field the badge reads. A manifest without it dates nothing."""
    manifest = result_dir / EXECUTION_MANIFEST
    if not manifest.is_file():
        pytest.skip("covered by test_every_real_policy_result_ships_its_execution_manifest")
    ended = json.loads(manifest.read_text(encoding="utf-8")).get("ended_at")
    assert isinstance(ended, str) and ended, f"{_rel(manifest)} has no usable ended_at"


def test_the_undated_exemptions_are_exactly_the_ones_declared() -> None:
    """Both directions, so the list cannot rot.

    A NEW undated directory must fail rather than be tolerated. A directory that has since GAINED
    its manifest must be removed from the list rather than left claiming an exemption it no longer
    needs — otherwise the list slowly becomes a place where real gaps hide.
    """
    undated = {_rel(d) for d in _result_dirs() if not (d / EXECUTION_MANIFEST).is_file()}
    assert undated == UNDATED_STUB_FIXTURES, (
        f"undated result dirs changed.\n  now undated: {sorted(undated)}\n"
        f"  declared   : {sorted(UNDATED_STUB_FIXTURES)}"
    )


def test_the_reader_sees_every_dated_result() -> None:
    """Reader and writer must not diverge in COUNT, not just in filename.

    Agreeing on a name is not enough — both halves can agree and still disagree about which
    directories carry it, which is precisely what happened. This compares what the badge can
    actually see against what is on disk.
    """
    dated = [d for d in _result_dirs() if (d / EXECUTION_MANIFEST).is_file()]
    seen = len(measurements_from_results())
    assert seen == len(dated), (
        f"the badge reads {seen} measurement(s) but {len(dated)} dated result director"
        f"{'y' if len(dated) == 1 else 'ies'} are committed. A result the reader cannot see is a "
        f"measurement that does not exist as far as the badge is concerned."
    )
