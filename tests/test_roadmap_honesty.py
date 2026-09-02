"""Nothing under `## Planned` in the roadmap may already be shipped.

WHY. `docs/roadmap.md` listed "**Public leaderboard** with open submission" under **Planned** while
`provael submit` had been in every release since 0.32.0, `CONTRIBUTING-leaderboard.md` documented
the PR route, and `leaderboard-submission.yml` validated submissions on `results/**`. The file's own
Shipped section already said the board was Ed25519-signed, so it contradicted itself on the same
page.

Understating is the safer direction of error here and this project prefers it — but a roadmap that
calls a shipped feature "planned" is not modesty, it is a wrong answer to "can I do X with this
today?", which is the only question a roadmap gets asked.

WHAT THIS CAN AND CANNOT CATCH. It compares the Planned section against the CLI's own command list,
which is the strongest machine-readable statement of what the tool does. It cannot catch a planned
item that is shipped without a command — that is a judgement call, and the test says so rather than
pretending to cover it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import typer.main

from provael.cli import app

ROOT = Path(__file__).resolve().parent.parent
ROADMAP = ROOT / "docs" / "roadmap.md"

#: Capabilities that ship as CONFIG rather than as a CLI command, with the committed evidence
#: that each is wired. Keyword -> (human name, [(file, substring proving it is live)]).
#: Deliberately short and literal: the point is to cover the class the CLI check cannot see,
#: not to build a second roadmap parser.
CONFIG_WIRED: tuple[tuple[str, str, tuple[tuple[Path, str], ...]], ...] = (
    (
        "mike",
        "docs-site versioning",
        ((ROOT / "pyproject.toml", '"mike",'), (ROOT / "mkdocs.yml", "provider: mike")),
    ),
)

#: Command names too generic to search for — every roadmap mentions "run" and "report" in prose.
_TOO_GENERIC = frozenset({"run", "report", "list", "version", "doctor", "init", "show"})


def _planned_section() -> str:
    text = ROADMAP.read_text(encoding="utf-8")
    m = re.search(r"^##\s+Planned\b(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    assert m is not None, (
        "no '## Planned' heading in docs/roadmap.md. If the roadmap was restructured, update this "
        "test in the same commit — do not delete it."
    )
    return m.group(1)


def _cli_commands() -> set[str]:
    """Every registered command name, read from the app OBJECT rather than from its help text.

    The first version of this scraped `provael --help` for Typer's box-drawn table rows. That
    passed on one CI runner and returned the empty set on another, which failed the RELEASE gate
    at v0.38.0 — Rich decides borders, wrapping and glyphs from terminal width, TERM and colour
    support, so the same command list renders differently on two machines that are otherwise
    identical. Parsing a human-facing rendering for a structural fact is the bug; the Click group
    Typer builds has the names exactly, and cannot be reformatted out from under the test.
    """
    group = typer.main.get_command(app)
    names = set(getattr(group, "commands", {}))
    assert names, "the Typer app registered no commands at all"
    return names


def test_no_shipped_cli_command_is_listed_as_planned() -> None:
    offenders = []
    planned = _planned_section()
    for cmd in sorted(_cli_commands() - _TOO_GENERIC):
        # Word-boundary, and only when the roadmap is talking about the COMMAND (backticked or
        # followed by a flag), so prose using the same English word does not trip it.
        if re.search(rf"`{re.escape(cmd)}[ `]|`provael {re.escape(cmd)}`", planned):
            offenders.append(cmd)
    assert not offenders, (
        f"docs/roadmap.md lists these under '## Planned', but they ship in the CLI today: "
        f"{offenders}. Move them to Shipped and say when they landed. A roadmap that calls a "
        f"shipped feature planned answers 'can I do this today?' wrongly."
    )


def test_the_planned_section_does_not_claim_the_leaderboard_is_unshipped() -> None:
    """The specific regression, pinned.

    `provael submit` has no unique word the generic test above can key on beyond the command name,
    and 'open submission' is the phrasing that was actually wrong.
    """
    planned = _planned_section().lower()
    assert "open submission" not in planned, (
        "'open submission' is back under Planned. `provael submit` shipped in 0.32.0. What is "
        "genuinely still missing is EXTERNAL submissions arriving, which is adoption, not code."
    )


@pytest.mark.parametrize("phrase", ["ed25519-signed", "signed as of"])
def test_signing_claims_do_not_appear_in_planned(phrase: str) -> None:
    """The board's signing shipped in 0.27.0 and the Shipped section says so. If a signing claim
    ever appears under Planned too, the file is contradicting itself again — which is exactly the
    shape of the defect this module was written for."""
    assert phrase not in _planned_section().lower()


def test_no_config_wired_capability_is_listed_as_planned() -> None:
    """The class `test_no_shipped_cli_command_is_listed_as_planned` structurally cannot see.

    That test keys on CLI command names and its docstring is honest that a feature shipping without
    a command is invisible to it. Docs-site versioning is exactly that shape: `mike` registers no
    `provael` subcommand, so wiring it while the roadmap still discussed it under Planned would have
    left the repo contradicting itself with nothing failing — the same defect as the leaderboard
    one, in the only place the original check has no reach.

    Kept narrow on purpose. It fires only when the capability is demonstrably wired in committed
    config, so it cannot nag about something merely intended.
    """
    planned = _planned_section()
    offenders = []
    for keyword, name, evidence in CONFIG_WIRED:
        if not re.search(rf"\b{re.escape(keyword)}\b", planned):
            continue
        if all(marker in path.read_text(encoding="utf-8") for path, marker in evidence):
            offenders.append(f"{keyword} ({name})")
    assert not offenders, (
        f"docs/roadmap.md discusses these under '## Planned', but the committed config shows them "
        f"wired today: {offenders}. Move the entry and say when it landed — including when the "
        f"entry is a decision AGAINST the thing, which is worse than a stale plan: it tells a "
        f"reader the opposite of what the repo does."
    )
