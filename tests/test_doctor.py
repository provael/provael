"""`provael doctor` — the command whose entire job is to tell the truth about this install.

WHY THIS FILE EXISTS. `doctor` shipped with zero tests, and the first defect found in it was that
it printed the OPPOSITE of true. The scaffolding note for `groot` reads:

    needs lerobot[groot], which provael[lerobot] does not install

Rich parses `[groot]` and `[lerobot]` as style tags and deletes them, so the rendered line was:

    needs lerobot, which provael does not install

`provael[lerobot]` exists and installs fine. A reader was told the opposite of the fact the
disclosure was written to convey, by the command whose only purpose is honest disclosure.

`list-policies` renders the same string correctly because it escapes. The difference between the
two was one function call and no test.
"""

from __future__ import annotations

import re

from typer.testing import CliRunner

from provael.cli import app
from provael.policies.registry import SCAFFOLDING_POLICIES

runner = CliRunner()


def _doctor(*args: str) -> str:
    """Run doctor and return its output with line-wrapping undone.

    Rich hard-wraps to the terminal width, so a phrase can be split across lines and a naive
    `in` check fails on text that rendered perfectly. Collapsing whitespace tests what a reader
    SEES rather than how it happened to be laid out.
    """
    result = runner.invoke(app, ["doctor", "--offline", *args])
    assert result.exit_code == 0, result.output
    return re.sub(r"\s+", " ", result.output)


def test_scaffolding_notes_survive_rendering_intact() -> None:
    """Every bracketed extra in every scaffolding note reaches the screen.

    This is the regression test for the inversion above, and it is written against the REGISTRY
    rather than against the one string that was wrong — a test that only checked `lerobot[groot]`
    would pass the day someone adds a fifth backend whose note names a different extra.
    """
    out = _doctor()
    for name, note in SCAFFOLDING_POLICIES.items():
        for extra in re.findall(r"\w+\[[\w-]+\]", note):
            assert extra in out, (
                f"doctor dropped {extra!r} from the {name} scaffolding note.\n"
                f"  registry says: {note}\n"
                f"  Rich ate the bracketed extra as a style tag. Wrap the interpolation in "
                f"rich.markup.escape() — list-policies already does."
            )


def test_doctor_does_not_claim_provael_lerobot_is_uninstallable() -> None:
    """The specific false sentence, pinned by its meaning rather than its punctuation.

    `provael[lerobot]` is a real extra. Any rendering that says plain "provael does not install"
    has lost the qualifier and inverted the claim.
    """
    out = _doctor()
    assert "which provael does not install" not in out, (
        "doctor rendered 'which provael does not install' — the bracketed extras were stripped "
        "and the sentence now says the opposite of what the registry says."
    )
    if any("lerobot[groot]" in n for n in SCAFFOLDING_POLICIES.values()):
        assert "provael[lerobot] does not install" in out


def test_every_scaffolding_backend_is_listed_as_scaffolding() -> None:
    """A backend that is registered but has never loaded a checkpoint must say so here.

    doctor is where someone checks whether their install can do the thing they are about to
    claim it did. Silently promoting scaffolding to `ready` is the failure that matters.
    """
    out = _doctor()
    for name in SCAFFOLDING_POLICIES:
        assert re.search(rf"scaffolding\s+{re.escape(name)}\b", out), (
            f"{name} is in SCAFFOLDING_POLICIES but doctor did not mark it as scaffolding"
        )


def test_ready_carries_its_disclaimer() -> None:
    """`ready` means constructible, NOT that a checkpoint is present — and the word `ready` on
    its own reads as the stronger claim, so the qualifier travels with it."""
    out = _doctor()
    assert "NOT that a checkpoint is present" in out


def test_offline_does_not_reach_pypi() -> None:
    """`--offline` exists so this command works on a machine with no network.

    If it ever starts making a request, doctor becomes slow and flaky in exactly the situation a
    user runs it — something is already wrong.
    """
    import provael.cli as cli_mod

    called: list[str] = []
    original = getattr(cli_mod, "urlopen", None)
    if original is not None:
        cli_mod.urlopen = lambda *a, **k: called.append("network") or original(*a, **k)  # type: ignore[assignment]
        try:
            _doctor()
        finally:
            cli_mod.urlopen = original  # type: ignore[assignment]
    assert not called, "doctor --offline made a network call"
