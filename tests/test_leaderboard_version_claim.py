"""The published board must state which tool version measured it, and that claim is checked.

THE GAP THIS CLOSES. `leaderboard.json` carries `measured_with`, and nothing verified it against
the tool that actually exists. The board has read ["0.32.0"] against a 0.34.0 and now 0.35.0 tool,
which is *correct* — the shards genuinely carry tool_version 0.32.0 and were measured 2026-08-09 —
but "correct" and "unchecked" looked identical from outside, and a stale claim would too.

TWO WAYS TO PASS, AND ONLY TWO. Either the board was measured with the current version, or the
repo carries a dated entry in leaderboard/method-equivalence.json arguing why the gap does not
move these rows. The second is deliberately not a waiver flag: an entry has to name what changed
and why it cannot affect the published numbers, so the escape hatch costs more than a re-run would
if a re-run were possible.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael import __version__
from provael.leaderboard import _inputs_digest, find_reports, load_leaderboard
from provael.report import load_report
from provael.types import RunReport

_ROOT = Path(__file__).resolve().parent.parent
_BOARD = _ROOT / "leaderboard" / "results" / "leaderboard.json"
_EQUIVALENCE = _ROOT / "leaderboard" / "method-equivalence.json"
_SUITE = _ROOT / "results" / "smolvla_libero_object_suite"


def _entries() -> list[dict[str, object]]:
    if not _EQUIVALENCE.exists():
        return []
    return list(json.loads(_EQUIVALENCE.read_text(encoding="utf-8"))["entries"])


def test_the_board_states_a_measurement_version_at_all() -> None:
    """A board with no `measured_with` makes no checkable claim, which is the worst of the three."""
    board = load_leaderboard(_BOARD)
    assert board.measured_with, "leaderboard.json carries no measured_with"


def test_measured_with_is_current_or_an_equivalence_entry_covers_the_gap() -> None:
    board = load_leaderboard(_BOARD)
    if __version__ in board.measured_with:
        return

    covered = {str(e.get("measured_with")) for e in _entries()}
    missing = [v for v in board.measured_with if v not in covered]
    assert not missing, (
        f"the board says it was measured with {board.measured_with} but the tool is at "
        f"{__version__}, and leaderboard/method-equivalence.json has no entry for {missing}. "
        "Either re-measure at the current version, or add a dated entry naming what changed and "
        "why it cannot move these rows."
    )


def test_every_equivalence_entry_is_dated_and_argued() -> None:
    """An undated or unargued entry is a waiver wearing the word 'equivalence'."""
    for entry in _entries():
        label = entry.get("measured_with")
        assert entry.get("dated"), f"equivalence entry {label} carries no date"
        assert entry.get("what_changed"), f"equivalence entry {label} does not say what changed"
        assert entry.get("why_it_cannot_move_these_rows"), (
            f"equivalence entry {label} asserts equivalence without arguing it"
        )
        assert entry.get("what_this_is_not"), (
            f"equivalence entry {label} does not state its own limits — a code-inspection argument "
            "must not read as a re-measurement"
        )


def test_measured_with_matches_the_artifacts_it_claims_to_aggregate() -> None:
    """The board's version claim must equal what the SHARDS say, not merely be plausible.

    This is the assertion that would have caught a genuinely wrong `measured_with`: the earlier
    board read ["0.1.0"] for numbers 0.32.0 produced, and nothing compared the two.
    """
    if not _SUITE.exists():  # pragma: no cover - the committed suite is present in-repo
        return
    shard_versions = {
        RunReport.model_validate_json(p.read_text(encoding="utf-8")).tool_version
        for p in find_reports([str(_SUITE)])
    }
    board = load_leaderboard(_BOARD)
    assert set(board.measured_with) == shard_versions, (
        f"board claims measured_with {sorted(board.measured_with)} but the aggregated shards "
        f"carry {sorted(shard_versions)}"
    )


def test_the_committed_board_still_rebuilds_to_its_committed_digest() -> None:
    """A published board must rebuild to the SAME inputs_digest under a later tool.

    THE REGRESSION THIS PINS, which shipped twice before anyone noticed. `_inputs_digest` used
    `r.model_dump_json()`, re-serialising every input report through whatever `RunReport` the
    RUNNING version defines. Adding an optional field rewrote the bytes of reports that predate it,
    so the digest of an unchanged committed artifact moved with the tool version: 0.33.2 and 0.34.0
    gave `69396ef8…`, 0.35.0 gave `46008680…` once `trajectory` landed, and 0.36.0 gave
    `5d63664f…` once `weight_corruption` did.

    /verification tells strangers to rebuild the board and expect a match, so this turned the
    project's own reproduction instructions into a failing check on every schema addition.

    THE ASSERTION IS AGAINST THE REAL COMMITTED ARTIFACTS, deliberately. The first version of this
    test compared two synthetic projections and passed under the broken code as well as the fixed
    code — it asserted two digests differed, which they did either way, and proved nothing. The only
    assertion that separates them is the one the docs actually promise: rebuild the committed board
    from the committed reports and get the committed digest back.
    """
    board = json.loads(_BOARD.read_text(encoding="utf-8"))
    committed = board.get("inputs_digest")
    assert committed, "the committed board carries no inputs_digest to check against"

    suite = _ROOT / "results" / "smolvla_libero_object_suite"
    assert suite.is_dir(), f"{suite} is missing; the board's input run is not in this checkout"

    reports = [load_report(path) for path in find_reports([str(suite)])]
    assert reports, f"no run reports found under {suite}"

    assert _inputs_digest(reports) == committed, (
        "the committed board no longer rebuilds to its own inputs_digest. A schema addition has "
        "changed the bytes of reports that predate it — _inputs_digest must project each report to "
        "its DECLARED schema_version (attest.report_projection), not re-serialise it through the "
        "model the running version happens to define."
    )
