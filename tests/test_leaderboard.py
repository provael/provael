"""Leaderboard aggregation: correctness, determinism, demo flag, real-run, provenance, CLI."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.attest import generate_private_key_pem, public_key_pem
from provael.cli import app
from provael.config import RunConfig
from provael.leaderboard import (
    REAL_TRANSFER,
    STUB_SCAFFOLDING,
    aggregate,
    attack_examples,
    build_leaderboard,
    find_reports,
    load_leaderboard,
    sign_leaderboard,
    stamp_provenance,
    to_json,
    verify_leaderboard,
)
from provael.report import write_report
from provael.runner import run
from provael.types import RunReport

runner = CliRunner()

_HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
_needs_crypto = pytest.mark.skipif(not _HAS_CRYPTO, reason="requires the `attest` extra")


def _real_report() -> RunReport:
    """A deterministic run (with the `none` baseline) relabelled as a real smolvla x libero run."""
    report = run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=["none", "instruction", "visual", "injection"], episodes=10, seed=0,
        )
    )
    return report.model_copy(update={"policy": "smolvla", "suite": "libero"})


def _stub_report():
    return run(
        RunConfig(
            policy="stub",
            suite="stub",
            attacks=["instruction", "visual", "injection"],
            episodes=10,
            seed=0,
        )
    )


def test_aggregate_rows_and_asr() -> None:
    board = aggregate([_stub_report()])
    by_family = {r.family: r for r in board.rows}
    assert (by_family["instruction"].successes, by_family["instruction"].attempts) == (21, 30)
    assert (by_family["visual"].successes, by_family["visual"].attempts) == (14, 20)
    assert (by_family["injection"].successes, by_family["injection"].attempts) == (12, 20)
    # Ranked by ASR descending.
    assert [r.asr for r in board.rows] == sorted((r.asr for r in board.rows), reverse=True)
    assert board.is_demo is True


def test_is_demo_false_with_a_real_policy() -> None:
    stub = _stub_report()
    pretend_real = stub.model_copy(update={"policy": "smolvla"})
    board = aggregate([stub, pretend_real])
    assert board.is_demo is False
    policies = {r.policy for r in board.rows}
    assert policies == {"stub", "smolvla"}


def test_attack_examples_cover_every_attack() -> None:
    names = ["roleplay", "patch", "scene_text", "mcp_tool_desc", "decoy_object"]
    examples = {e.attack: e for e in attack_examples(names)}
    assert set(examples) == set(names)
    # Instruction-family example is the rewritten instruction; obs families show a channel.
    assert "knife" in examples["roleplay"].example.lower()
    assert "visual_tokens" in examples["patch"].example
    assert "scene_text" in examples["scene_text"].example


def test_find_reports_directory_and_glob(tmp_path: Path) -> None:
    write_report(_stub_report(), tmp_path / "a")
    write_report(_stub_report(), tmp_path / "b")
    via_dir = find_reports([str(tmp_path)])
    assert len(via_dir) == 2
    via_glob = find_reports([str(tmp_path / "*")])
    assert sorted(via_glob) == sorted(via_dir)


def test_build_leaderboard_is_deterministic(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_report(_stub_report(), runs / "one")
    out1, board1 = build_leaderboard([str(runs)], tmp_path / "out1")
    out2, _ = build_leaderboard([str(runs)], tmp_path / "out2")
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
    # Round-trips.
    assert to_json(load_leaderboard(out1)) == to_json(board1)


def test_cli_leaderboard_build(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    assert runner.invoke(
        app, ["attack", "--episodes", "5", "--attacks", "instruction,visual", "--out", str(runs)]
    ).exit_code == 0
    result = runner.invoke(
        app, ["leaderboard", "build", "--runs", str(runs), "--out", str(tmp_path / "lb")]
    )
    assert result.exit_code == 0
    assert (tmp_path / "lb" / "leaderboard.json").exists()
    assert "ASR leaderboard" in result.output
    assert "demo data" in result.output  # stub-only -> demo banner


def test_cli_leaderboard_build_no_reports(tmp_path: Path) -> None:
    result = runner.invoke(app, ["leaderboard", "build", "--runs", str(tmp_path / "empty")])
    assert result.exit_code == 2


# --------------------------------------------------------------------------------------------
# real-run aggregation: is_demo flips, rows carry transfer-status + CI + benign control
# --------------------------------------------------------------------------------------------

def test_real_run_flips_is_demo_and_labels_rows() -> None:
    board = aggregate([_real_report()])
    assert board.is_demo is False
    for row in board.rows:
        assert row.transfer_status == REAL_TRANSFER
        assert row.ci95 is not None  # every real row carries its 95% Wilson CI
    # the benign control (baseline family rate) is attached to every row
    assert all(r.benign_fpr is not None for r in board.rows if r.attempts)


def test_stub_only_keeps_is_demo_and_stub_label() -> None:
    board = aggregate([_stub_report()])
    assert board.is_demo is True
    assert all(r.transfer_status == STUB_SCAFFOLDING for r in board.rows)


def test_never_silently_mixes_stub_and_real() -> None:
    board = aggregate([_stub_report(), _real_report()])
    assert board.is_demo is False
    labels = {(r.policy, r.transfer_status) for r in board.rows}
    assert ("stub", STUB_SCAFFOLDING) in labels
    assert ("smolvla", REAL_TRANSFER) in labels  # each row explicitly labelled, not blended


# --------------------------------------------------------------------------------------------
# provenance digest: deterministic and input-sensitive
# --------------------------------------------------------------------------------------------

def test_inputs_digest_is_stable_and_sensitive() -> None:
    a = aggregate([_real_report()]).inputs_digest
    b = aggregate([_real_report()]).inputs_digest
    assert a is not None and a == b  # same inputs -> same digest
    changed = _real_report().model_copy(update={"successes": 999})
    assert aggregate([changed]).inputs_digest != a


def test_build_leaderboard_stays_deterministic_with_digest(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_report(_stub_report(), runs / "one")
    out1, board1 = build_leaderboard([str(runs)], tmp_path / "o1")
    out2, _ = build_leaderboard([str(runs)], tmp_path / "o2")
    assert out1.read_text() == out2.read_text()  # digest deterministic, no date stamped
    assert board1.generated_at is None and board1.signature is None


def test_require_real_rejects_stub_only(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_report(_stub_report(), runs / "one")
    with pytest.raises(ValueError, match="no real"):
        build_leaderboard([str(runs)], tmp_path / "o", require_real=True)


# --------------------------------------------------------------------------------------------
# signing (gated on the crypto extra; present in the dev group -> runs in CI)
# --------------------------------------------------------------------------------------------

@_needs_crypto
def test_sign_and_verify_roundtrip() -> None:
    board = stamp_provenance(aggregate([_real_report()]), generated_at="2026-07-04T00:00:00Z",
                             commit="abc1234")
    priv = generate_private_key_pem()
    signed = sign_leaderboard(board, priv)
    assert signed.signature is not None and signed.signature.alg == "ed25519"
    assert verify_leaderboard(signed, public_key_pem(priv)) is True
    # a different key does not verify
    assert verify_leaderboard(signed, public_key_pem(generate_private_key_pem())) is False
    # tampering with a row breaks verification
    tampered = signed.model_copy(deep=True)
    tampered.rows[0].successes += 1
    assert verify_leaderboard(tampered, public_key_pem(priv)) is False


@_needs_crypto
def test_unsigned_board_does_not_verify() -> None:
    board = aggregate([_real_report()])
    assert board.signature is None
    assert verify_leaderboard(board, public_key_pem(generate_private_key_pem())) is False


# --------------------------------------------------------------------------------------------
# CLI --real path
# --------------------------------------------------------------------------------------------

def test_cli_leaderboard_build_real(tmp_path: Path) -> None:
    real = tmp_path / "real"
    write_report(_real_report(), real / "smolvla")
    result = runner.invoke(
        app, ["leaderboard", "build", "--real", str(real), "--out", str(tmp_path / "lb")]
    )
    assert result.exit_code == 0, result.output
    board = load_leaderboard(tmp_path / "lb" / "leaderboard.json")
    assert board.is_demo is False
    assert board.inputs_digest is not None
    assert board.generated_at is not None and board.commit is not None


def test_cli_leaderboard_build_real_rejects_stub(tmp_path: Path) -> None:
    stub = tmp_path / "stub"
    write_report(_stub_report(), stub / "one")
    result = runner.invoke(app, ["leaderboard", "build", "--real", str(stub)])
    assert result.exit_code == 2  # _fail on ValueError (no real runs)


# --------------------------------------------------------------------------- #
# The committed public artifact: freshness + signature
#
# The product's commercial claim is "a dated, signed record, not a screenshot". The committed
# board spent 22 releases at generated_at 2026-07-04 with signature: null, which makes that claim
# false in the one place a buyer checks. These two guards are what stop it drifting again.
# --------------------------------------------------------------------------- #

#: How far, in DAYS, the committed board's stamp may lag the newest released tag before CI fails.
#:
#: THE DECISION (2026-08-03), because this guard was one release from failing and the tempting
#: fix was to raise a constant. This IS a real freshness policy — but for the provenance
#: envelope, not the measurement. Measurement staleness is carried honestly by `measured_with`
#: and `is_restamp()` (guarded below) and cannot be fixed by any re-stamp; what THIS guard
#: protects is the envelope: a reader who installs the newest release should find a board whose
#: stamp was maintained recently enough to show somebody is still tending it.
#:
#: The previous constant, MAX_RELEASES_BEHIND = 3, measured that in released tags. A release
#: count stopped being a unit of time when the cadence went daily: v0.29.1, v0.30.0 and v0.31.0
#: landed on consecutive days, so "three releases behind" silently became "three days behind",
#: and the board sat at `behind == 3` — passing by zero margin — days after a fresh re-stamp.
#: A policy whose strictness is an accident of release tempo is not a policy.
#:
#: So the limit is re-derived from time, computed from two COMMITTED facts — the newest tag's
#: creation date and the board's own `generated_at` — never from the wall clock, so the guard
#: stays deterministic given repo state and can only go red when a new tag appears, not while
#: the repo sleeps. Fourteen days, because: (a) the one real incident (a board stamped 4 July,
#: found 30 July) would have been caught by 18 July, earlier than any plausible count-based
#: limit; (b) a re-stamp is a GPU-free one-command operation, so a fortnightly ceiling costs
#: minutes; (c) at any cadence — daily or monthly — the guarantee reads the same: the stamp on
#: the public artifact is never more than two weeks older than the release line it ships with.
MAX_STAMP_LAG_DAYS = 14

_BOARD = Path(__file__).resolve().parent.parent / "leaderboard" / "results" / "leaderboard.json"

#: A FROZEN COPY of the published board, for the tests that need a board that never moves.
#:
#: WHY IT EXISTS. Two guards here wanted opposite things from the same file. The stamp-envelope
#: test fails a release whose board is more than MAX_STAMP_LAG_DAYS behind the newest tag — it
#: wants the live board RE-STAMPED. The v5-mechanism tests pin `schema_version == 5` and
#: `tool_version == "0.33.2"` — they want it FROZEN. A re-stamp necessarily moves schema_version to
#: whatever the current code emits, so satisfying one broke the other, and no CLI flag can
#: reconcile them. Discovered when a re-stamp for the 0.39.0 release turned three of these red.
#:
#: The split: tests about the v5 SERIALISATION MECHANISM read this frozen artifact; tests about
#: THE PUBLISHED BOARD (its signature verifies, its staleness is declared, it names a submitter,
#: its stamp is inside the envelope) keep reading the live one, because those are properties the
#: live board must keep having. Never re-generate this file — a fixture that moves with the code
#: cannot prove the code once emitted something different.
_V5_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "leaderboard-v5-signed.json"
_V5_FIXTURE_PUB = Path(__file__).resolve().parent / "fixtures" / "leaderboard-v5-signed.pub"
_BOARD_PUB = _BOARD.with_suffix(".pub")


def _tags_newest_first() -> list[str]:
    proc = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-v:refname"],
        cwd=_BOARD.parent.parent.parent, capture_output=True, text=True, check=False,
    )
    return [t for t in proc.stdout.splitlines() if t.strip()] if proc.returncode == 0 else []


def test_committed_leaderboard_is_signed() -> None:
    """`signature: null` on the public artifact contradicts the product's own claim."""
    board = load_leaderboard(_BOARD)
    assert board.signature is not None, (
        "the committed leaderboard is UNSIGNED. Rebuild and sign it:\n"
        "  provael leaderboard build --real results/smolvla_libero_object_suite "
        "--sign --key <PROVAEL_SIGNING_KEY> --out leaderboard/results"
    )
    assert board.signature.alg == "ed25519"
    assert _BOARD_PUB.is_file(), "the public key must be published beside the board"


def test_committed_leaderboard_signature_actually_verifies() -> None:
    """A signature that does not check out against the PUBLISHED key is worse than none.

    Guards the case where the board is re-signed with a key nobody published, which would leave a
    buyer following our own documented verification steps and getting INVALID.
    """
    board = load_leaderboard(_BOARD)
    assert board.signature is not None
    assert verify_leaderboard(board, _BOARD_PUB.read_bytes()), (
        "the committed board does not verify against the committed public key"
    )


def test_committed_leaderboard_stamp_is_not_too_far_behind_the_release_line() -> None:
    """Fail when the board's stamp lags the newest released tag by more than MAX_STAMP_LAG_DAYS.

    Both operands are committed facts (the tag's creation date, the board's `generated_at`), so
    this is deterministic for a given repo state: it can only turn red when a new tag is created,
    never by the passage of wall-clock time alone.
    """
    tags = _tags_newest_first()
    if not tags:
        # Same posture as the version guard: never pass quietly where it matters.
        assert not os.environ.get("CI"), (
            "no git tags available in CI — the checkout must fetch tags or this guard silently "
            "passes"
        )
        pytest.skip("no git tags available (shallow clone or no git); cannot verify")

    board = load_leaderboard(_BOARD)
    assert board.commit, "the committed board carries no source commit"
    assert board.generated_at, "the committed board carries no stamp"

    repo = _BOARD.parent.parent.parent
    tag_date = subprocess.run(
        ["git", "for-each-ref", "--format=%(creatordate:iso8601-strict)", f"refs/tags/{tags[0]}"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    newest_release = datetime.fromisoformat(tag_date)
    stamped = datetime.fromisoformat(board.generated_at.replace("Z", "+00:00"))

    lag = newest_release - stamped
    assert lag <= timedelta(days=MAX_STAMP_LAG_DAYS), (
        f"the committed leaderboard was stamped {board.generated_at} (commit {board.commit}), "
        f"{lag.days} days before the newest release {tags[0]} ({tag_date}) — over the "
        f"{MAX_STAMP_LAG_DAYS}-day envelope policy. Rebuild and re-sign it: a GPU-free "
        f"re-stamp from the committed run reports, `provael leaderboard build --real "
        f"results/smolvla_libero_object_suite --sign --key <PROVAEL_SIGNING_KEY> --out "
        f"leaderboard/results`."
    )


def test_board_records_what_measured_it_not_just_when_it_was_stamped() -> None:
    """`generated_at` moves on every re-stamp; the NUMBERS do not. Both must be legible.

    Rebuilding stamps today's date onto rows measured long ago, so a board carrying only
    `generated_at` reads as a fresh measurement. `measured_with` is the correction, and
    `is_restamp()` is how a consumer asks the question directly.
    """
    board = load_leaderboard(_BOARD)
    assert board.measured_with, "the board does not record which tool versions measured its rows"
    assert board.schema_version >= 3
    # This board's rows were measured long before the version assembling it — say so.
    assert board.is_restamp() is True


# --------------------------------------------------------------------------------------------- #
# Submitter attribution: independence made legible in the artifact
#
# `transfer_status` answers "is this a real measurement?"; it cannot answer "whose?". A board of
# four rows from one maintainer run and a board of four rows from four labs were byte-identical in
# every field, so the rendered board could not distinguish them and neither could a reader deciding
# how much independence a number carries. These pin the distinction, including the part that is
# easy to get wrong: the maintainer submitting their own run is attribution, NOT independence.
# --------------------------------------------------------------------------------------------- #

from provael.leaderboard import (  # noqa: E402
    MAINTAINER_RUN,
    THIRD_PARTY_SUBMISSION,
    UNATTRIBUTED,
)


def test_rows_are_unattributed_unless_a_submitter_is_given() -> None:
    """Default stays honest: a plain build invents no provenance."""
    board = aggregate([_real_report()])
    assert all(r.submitted_by is None for r in board.rows)
    assert all(r.provenance == UNATTRIBUTED for r in board.rows)
    assert board.submitters() == [] and board.independent_submitters() == []


def test_maintainer_run_is_attributed_but_not_independent() -> None:
    board = aggregate([_real_report()], submitted_by="provael", provenance=MAINTAINER_RUN)
    assert board.submitters() == ["provael"]
    assert board.independent_submitters() == []  # the point: attribution != independence


def test_third_party_submission_counts_as_independent() -> None:
    board = aggregate([_real_report()], submitted_by="acme-robotics",
                      provenance=THIRD_PARTY_SUBMISSION)
    assert board.independent_submitters() == ["acme-robotics"]


@_needs_crypto
def test_attribution_is_covered_by_the_signature() -> None:
    """Provenance must be INSIDE the signed payload, or a row's attribution could be forged.

    Editing `submitted_by` on a signed board has to break verification exactly the way editing a
    success count does — otherwise the board's own signature would vouch for numbers while leaving
    "who produced them" freely rewritable, which is the more attractive lie of the two.
    """
    board = stamp_provenance(
        aggregate([_real_report()], submitted_by="acme", provenance=THIRD_PARTY_SUBMISSION),
        generated_at="2026-08-04T00:00:00Z", commit="abc1234",
    )
    priv = generate_private_key_pem()
    signed = sign_leaderboard(board, priv)
    assert verify_leaderboard(signed, public_key_pem(priv)) is True

    forged = signed.model_copy(deep=True)
    forged.rows[0].submitted_by = "someone-else"
    assert verify_leaderboard(forged, public_key_pem(priv)) is False


def test_the_committed_board_states_its_own_independence() -> None:
    """The published board must not imply external validation it does not have."""
    board = load_leaderboard(_BOARD)
    assert board.schema_version >= 4
    assert board.submitters(), "the committed board records no submitter at all"
    # Zero independent submitters is the TRUE state today. When a real third-party row lands this
    # assertion is what forces the claim on the website/docs to be revisited in the same change.
    assert board.independent_submitters() == []


# ---------------------------------------------------------------------------------------------
# Signature stability under additive schema evolution.
#
# Incident: adding `benign_successes` / `benign_attempts` / `benign_ci95` to `LeaderboardRow`
# without registering them in `_ROW_FIELDS_ADDED_IN` changed the canonical bytes of the COMMITTED
# v5 board, and its Ed25519 signature stopped verifying. To anyone checking that signature, a
# correctly-signed board is then indistinguishable from a tampered one.
#
# `test_committed_leaderboard_signature_actually_verifies` caught it, but only because a v5 board
# happens to be committed. These two make the requirement structural rather than incidental: a new
# field fails here immediately, naming itself, whatever boards happen to be in the repo.
# ---------------------------------------------------------------------------------------------

#: Fields that predate the `_FIELDS_ADDED_IN` registry (i.e. schema_version <= 4). Frozen: this
#: list must never grow. Anything new belongs in the registry, keyed by the version that adds it.
_BOARD_FIELDS_AT_FLOOR = frozenset({
    "commit", "examples", "generated_at", "inputs_digest", "is_demo", "measured_with", "rows",
    "schema_version", "signature",
})
_ROW_FIELDS_AT_FLOOR = frozenset({
    "asr", "attempts", "benign_fpr", "ci95", "family", "policy", "provenance", "submitted_by",
    "successes", "suite", "transfer_status",
})


def test_every_board_field_is_either_at_the_floor_or_registered_to_a_version() -> None:
    from provael.leaderboard import _FIELDS_ADDED_IN, Leaderboard

    registered = {name for names in _FIELDS_ADDED_IN.values() for name in names}
    unaccounted = set(Leaderboard.model_fields) - _BOARD_FIELDS_AT_FLOOR - registered
    assert not unaccounted, (
        f"Leaderboard field(s) {sorted(unaccounted)} are not registered in _FIELDS_ADDED_IN. "
        "Add them under the schema_version that introduces them, or every previously-signed "
        "board silently fails to verify."
    )


def test_every_row_field_is_either_at_the_floor_or_registered_to_a_version() -> None:
    from provael.leaderboard import _ROW_FIELDS_ADDED_IN, LeaderboardRow

    registered = {name for names in _ROW_FIELDS_ADDED_IN.values() for name in names}
    unaccounted = set(LeaderboardRow.model_fields) - _ROW_FIELDS_AT_FLOOR - registered
    assert not unaccounted, (
        f"LeaderboardRow field(s) {sorted(unaccounted)} are not registered in "
        "_ROW_FIELDS_ADDED_IN. Add them under the schema_version that introduces them, or every "
        "previously-signed board silently fails to verify."
    )


def test_registered_fields_are_stripped_below_their_own_version() -> None:
    """The mechanism itself: a v5 board's signing payload carries no v6 field."""
    import json as _json

    from provael.leaderboard import _ROW_FIELDS_ADDED_IN, _signing_payload

    # The FROZEN fixture, not the live board: this asserts what a v5 board's signed bytes
    # contain, and the live board is re-stamped by whatever version assembles it.
    board = load_leaderboard(_V5_FIXTURE)
    assert board.schema_version == 5, "the v5 fixture is no longer v5 — do not regenerate it"
    payload = _json.loads(_signing_payload(board))
    for row in payload["rows"]:
        for name in _ROW_FIELDS_ADDED_IN[6]:
            assert name not in row, f"{name} leaked into a v5 board's signed bytes"


# ---------------------------------------------------------------------------------------------
# Staleness: machine-readable, monotone, and outside the signature.
#
# The published board carried four rows measured with 0.32.0 and said so only in prose the Space
# renders. Prose does not stop a consumer: anything reading the JSON got four rates, a signature,
# and no way to tell that the signature vouches for a measurement rather than for its currency.
# ---------------------------------------------------------------------------------------------


def test_minor_lag_ignores_the_patch_and_refuses_to_subtract_across_a_major() -> None:
    from provael.leaderboard import minor_lag

    assert minor_lag("0.37.0", "0.38.0") == 1
    assert minor_lag("0.32.0", "0.38.0") == 6
    assert minor_lag("0.38.0", "0.38.7") == 0, "a patch changes no measured behaviour"
    assert minor_lag("main", "0.38.0") is None, "an unparseable version is not fresh"
    # 0.40 -> 1.0 is one release, not minus thirty-nine. Two incomparable series must not be
    # subtracted; the honest answer is "too far", never a negative number that reads as fresh.
    assert (minor_lag("0.40.0", "1.0.0") or 0) > 1


def test_staleness_answers_none_rather_than_fresh_when_it_cannot_tell() -> None:
    from provael.leaderboard import staleness

    for measured, against in (([], "0.38.0"), (["0.32.0"], None), (["main"], "0.38.0")):
        stale, reason = staleness(measured, against)
        assert stale is None, f"{measured} vs {against} must be undetermined, not fresh"
        assert reason, "an undetermined verdict still has to say why"


def test_staleness_is_decided_by_the_oldest_row() -> None:
    """A consumer accepts or refuses a board whole, so its worst row is the honest summary."""
    from provael.leaderboard import staleness

    stale, reason = staleness(["0.32.0", "0.38.0"], "0.38.0")
    assert stale is True
    assert "0.32.0" in reason


def test_the_published_board_declares_its_own_staleness() -> None:
    """The board's rows are older than the tool; that must be a FIELD, not a banner.

    Asserts the live board, and deliberately says nothing about which version assembled it —
    that moves with every re-stamp. What must never move is that the staleness is declared in
    machine-readable form, because a consumer reading JSON cannot see a banner.
    """
    import json as _json

    board = _json.loads(_BOARD.read_text(encoding="utf-8"))
    assert board["stale"] is True
    assert "0.32.0" in board["stale_reason"], "the reason must name the version that measured it"
    assert board["measured_with"] == ["0.32.0"], (
        "a re-stamp must never change what measured the rows — only when it was assembled"
    )


def test_the_v5_fixture_records_the_assembling_version_it_was_built_by() -> None:
    """The frozen artifact keeps its own provenance, so the pair (assembled-by, measured-with)
    stays checkable against a real historical board rather than against today's code."""
    import json as _json

    board = _json.loads(_V5_FIXTURE.read_text(encoding="utf-8"))
    assert board["tool_version"] == "0.33.2", "assembled by 0.33.2 at commit 8cd8d99"
    assert board["measured_with"] == ["0.32.0"], "rows measured by 0.32.0 — six minors behind"
    assert board["commit"] == "8cd8d99"


def test_the_staleness_fields_are_outside_the_signed_subject() -> None:
    """Staleness is a function of today; the signature must not be.

    Reads the FROZEN v5 fixture: this asserts what a v5 board's signed bytes exclude, and the
    live board is v6 the moment it is re-stamped (tool_version joined the signed subject in v6).

    A board that was current when signed becomes stale without a byte changing. If the flag were
    inside the signed subject, annotating it would break the signature — which is exactly why the
    published v5 board can carry `stale: true` and still verify.
    """
    import json as _json

    from provael.leaderboard import _FIELDS_ADDED_IN, _signing_payload

    board = load_leaderboard(_V5_FIXTURE)
    payload = _json.loads(_signing_payload(board))
    for name in _FIELDS_ADDED_IN[6]:
        assert name not in payload, f"{name} is inside the signed bytes of a v5 board"
    assert verify_leaderboard(board, _V5_FIXTURE_PUB.read_bytes())


def test_the_staleness_gate_fails_on_undeclared_staleness_only() -> None:
    """Disclosed staleness is the honest state; silent staleness is the bug.

    A gate that failed on staleness itself would be red until a GPU re-run nobody has scheduled,
    and a permanently-red detector reports nothing.
    """
    import importlib.util
    import json as _json

    script = Path(__file__).resolve().parent.parent / "scripts" / "check_leaderboard_staleness.py"
    spec = importlib.util.spec_from_file_location("check_leaderboard_staleness", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    board = _json.loads(_BOARD.read_text(encoding="utf-8"))
    assert gate.check(_BOARD, fix=False) == [], "the committed board declares its staleness"

    undeclared = _BOARD.parent / "_undeclared.json"
    board["stale"] = None
    undeclared.write_text(_json.dumps(board, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        problems = gate.check(undeclared, fix=False)
        assert problems and "stale=None" in problems[0]
    finally:
        undeclared.unlink()
