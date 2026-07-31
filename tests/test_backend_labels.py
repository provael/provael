"""`list-policies` / `list-suites` must distinguish what has been *run* from what merely *imports*.

THE GAP THIS CLOSES. Eight policy backends are registered; exactly one (`smolvla`) has ever had a
real checkpoint driven through it with the result committed. Three (`groot`, `openvla`, `openpi`)
have never loaded a checkpoint at all. `list-policies` did mark those three as scaffolding in its
notes, but its only status-like column was **"ready here"** — an import check. Every non-stub
backend renders `no` on a CPU box, so the one measured backend and the three that are pure
scaffolding looked identical to anyone skimming the table for something to put after `--policy`.

That matters more here than it would in most tools, because the output of pointing `--policy` at a
scaffolding backend is not an error — it is a number. A number computed against an adapter that
has never seen a checkpoint, formatted exactly like one that has, and emitted into SARIF/OSCAL
evidence the same way. The cheapest defence is to never let the two look alike in the first place.

`list-suites` did not exist at all, so nothing surfaced the `stub`/`reach`/`humanoid` fixtures as
distinct from the `libero`/`metaworld` simulators — a distinction `evidence.classify_run` already
enforces internally when it refuses to call a fixture run `real-episode`.
"""

from __future__ import annotations

from typer.testing import CliRunner

from provael.cli import app
from provael.policies.registry import (
    MEASURED_POLICIES,
    SCAFFOLDING_POLICIES,
    STATUS_FIXTURE,
    STATUS_MEASURED,
    STATUS_SCAFFOLDING,
    STATUS_UNRUN,
    available_policies,
    policy_status,
)
from provael.suites import (
    FIXTURE_SUITES,
    KIND_FIXTURE,
    KIND_SIMULATOR,
    available_suites,
    suite_kind,
)

runner = CliRunner()


#: Rich's box-drawing characters. A long cell is wrapped across several table rows, so a phrase
#: like "never a real-episode measurement" arrives split by a run of `│` borders — stripping the
#: frame before collapsing whitespace is what makes a substring assertion mean what it looks like.
_BOX = str.maketrans(dict.fromkeys("┏┓┗┛┡┩┃│━─┳┻┳┫┣╇╈┬┴├┤┼", " "))


def _plain(output: str) -> str:
    """Flatten a Rich table to one line of words, so wrapped cells still match as phrases."""
    return " ".join(output.translate(_BOX).split())


# --------------------------------------------------------------------------- #
# the status derivation itself
# --------------------------------------------------------------------------- #


def test_every_registered_policy_gets_exactly_one_known_status() -> None:
    known = {STATUS_MEASURED, STATUS_FIXTURE, STATUS_SCAFFOLDING, STATUS_UNRUN}
    for name in available_policies():
        assert policy_status(name) in known, f"{name} has an unrecognised status"


def test_only_a_backend_with_committed_evidence_reads_measured() -> None:
    """`measured` is the strongest label on the table; it must require committed evidence."""
    measured = {n for n in available_policies() if policy_status(n) == STATUS_MEASURED}
    assert measured == set(MEASURED_POLICIES)
    # Today that is smolvla alone. Asserted explicitly: if a second backend earns the label, that
    # is a real event that should require editing this line, not something that happens silently.
    assert measured == {"smolvla"}


def test_scaffolding_backends_never_read_measured() -> None:
    """The failure that matters: a never-run backend labelled as having produced a number."""
    for name in SCAFFOLDING_POLICIES:
        assert policy_status(name) == STATUS_SCAFFOLDING, (
            f"{name} is declared scaffolding but reports status {policy_status(name)!r}"
        )
        assert name not in MEASURED_POLICIES, (
            f"{name} is in both SCAFFOLDING_POLICIES and MEASURED_POLICIES — it cannot be both"
        )


def test_the_provisioned_but_unrun_backends_are_neither_measured_nor_scaffolding() -> None:
    """`pi0`/`pi05`/`pi0fast` are a real third category and flattening them would be a lie.

    They are genuinely provisioned by `provael[lerobot]` (unlike `groot`), so calling them
    scaffolding understates them; no checkpoint has been run here, so calling them measured
    overstates them. The honest label is the boring one.
    """
    for name in ("pi0", "pi05", "pi0fast"):
        assert policy_status(name) == STATUS_UNRUN


def test_the_cpu_stub_is_labelled_a_fixture_not_a_measurement() -> None:
    # The stub runs constantly, so "has it been run" is trivially yes — and irrelevant. What a
    # reader needs is that its numbers are arithmetic, not evidence about a robot.
    assert policy_status("stub") == STATUS_FIXTURE


# --------------------------------------------------------------------------- #
# what the commands actually print
# --------------------------------------------------------------------------- #


def test_list_policies_prints_a_status_for_every_backend() -> None:
    result = runner.invoke(app, ["list-policies"])
    assert result.exit_code == 0
    out = _plain(result.output)
    for name in available_policies():
        assert name in out
    assert STATUS_MEASURED in out
    assert "scaffolding" in out
    # The distinction the table exists to draw must be spelled out, not left to the reader.
    assert "different questions" in out


def test_list_policies_marks_each_scaffolding_backend_inline() -> None:
    out = _plain(runner.invoke(app, ["list-policies"]).output)
    for name in SCAFFOLDING_POLICIES:
        # The row must carry the word next to the name, not only in a legend somewhere.
        row = out.split(name, 1)[1][:200]
        assert "scaffolding" in row, f"{name}'s row does not say scaffolding: {row!r}"


def test_list_suites_marks_fixtures_apart_from_simulators() -> None:
    result = runner.invoke(app, ["list-suites"])
    assert result.exit_code == 0
    out = _plain(result.output)
    for name in available_suites():
        assert name in out
    assert KIND_FIXTURE in out
    assert KIND_SIMULATOR in out
    assert "never a real-episode measurement" in out


def test_suite_kind_follows_what_the_suite_classes_declare() -> None:
    """Derived from `SuiteAdapter.is_fixture`, so a new fixture cannot default to 'real'."""
    assert {n for n in available_suites() if suite_kind(n) == KIND_FIXTURE} == set(FIXTURE_SUITES)
    assert set(FIXTURE_SUITES) == {"stub", "reach", "humanoid"}
