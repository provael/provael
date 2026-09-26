# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every action a workflow runs is pinned to a commit, and every tool it fetches names a version.

WHY. ``.github/dependabot.yml`` states the rule: third-party actions are pinned to a full commit
SHA with a ``# vX.Y.Z`` comment, because an action's author re-points a bare ``@vN`` on every
release, and the code this repository runs would change with no diff here. By 26 September 2026
five refs had slipped back to bare tags anyway. Two were ``astral-sh/setup-uv@v5`` in the two
workflows that load the leaderboard signing key. OpenSSF Scorecard's Pinned-Dependencies check
flagged them. Nine ``uvx`` / ``pip install`` / ``uv run --with`` lines also resolved whatever PyPI
served when the job ran, one of them in the job that holds the Space's write token; Scorecard's
alerts named none of those. The fix is mechanical and the next new workflow undoes it, so it is a
test.

WHAT IS EXEMPT, AND WHY. Local actions (``./``) are this checkout, and so is a ``pip install`` of a
local path. ``readme-quickstart.yml`` installs ``provael`` unpinned on purpose: it runs the README's
own quickstart on a clean machine, and the README tells a reader to install the latest release, so
a pin would test a sentence the README does not say. ``action.yml`` is held to the action rule but
not the install rule, because what it installs is the adopter's pinned provael release, and why
that is a range is written beside it.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
ACTION = ROOT / "action.yml"

PINNED_ACTION = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
#: The raw line names the release the SHA was taken from; it is what Dependabot rewrites.
VERSION_COMMENT = re.compile(r"@[0-9a-f]{40}\s+#\s*v\d")
#: A shell line that opens a heredoc; its body is data, not commands.
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
#: Operators that start a new command on the same line.
SEPARATOR = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")

#: (workflow, requirement) pairs installed unpinned on purpose; see the module docstring.
UNPINNED_ON_PURPOSE = {
    ("readme-quickstart.yml", "provael"),
    ("readme-quickstart.yml", "provael[attest]"),
}
#: Options that consume the next token as their value.
PIP_VALUE_OPTIONS = {"-r", "--requirement", "-c", "--constraint", "-i", "--index-url",
                     "--extra-index-url"}
UV_VALUE_OPTIONS = {"--python", "-p", "--index-url", "--extra-index-url"}


def _load(path: Path) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), f"{path.name} did not parse to a mapping"
    return doc


def _steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    if "jobs" in doc:
        return [s for job in doc["jobs"].values() for s in job.get("steps", [])]
    return list(doc.get("runs", {}).get("steps", []))


def _uses(doc: dict[str, Any]) -> list[str]:
    refs = [s["uses"] for s in _steps(doc) if "uses" in s]
    refs += [job["uses"] for job in doc.get("jobs", {}).values() if "uses" in job]
    return refs


def _commands(doc: dict[str, Any]) -> list[str]:
    """Every shell command in the ``run:`` blocks: continuations joined, comments and heredoc
    bodies dropped, and ``a && b`` split into two."""
    out: list[str] = []
    for step in _steps(doc):
        script = step.get("run")
        if not isinstance(script, str):
            continue
        heredoc_end: str | None = None
        for raw in script.replace("\\\n", " ").splitlines():
            line = raw.strip()
            if heredoc_end is not None:
                heredoc_end = None if line == heredoc_end else heredoc_end
                continue
            if not line or line.startswith("#"):
                continue
            if opened := HEREDOC.search(line):
                heredoc_end = opened.group(1)
            out += [part for part in SEPARATOR.split(line) if part]
    return out


def _tokens(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:  # an unbalanced quote across a split; fall back rather than guess
        tokens = command.split()
    if tokens[:2] in (["python", "-m"], ["python3", "-m"]):
        tokens = tokens[2:]
    return tokens


def _pinned(spec: str) -> bool:
    return "==" in spec or re.search(r"@v?\d", spec) is not None


def _unpinned_pip(args: list[str]) -> list[str]:
    bad, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg in PIP_VALUE_OPTIONS:
            skip = True  # a requirements file is reviewed where it lives, not here
        elif arg.startswith("-") or arg.startswith((".", "/")):
            continue
        elif not _pinned(arg):
            bad.append(arg)
    return bad


def _unpinned_uv(args: list[str]) -> list[str]:
    """``uvx`` / ``uv tool run`` / ``uv run``: a ``--from`` or ``--with`` spec, or the tool itself."""
    bad, from_given, skip = [], False, False
    for i, arg in enumerate(args):
        if skip:
            skip = False
        elif arg in ("--from", "--with", "-w"):
            spec = args[i + 1] if i + 1 < len(args) else ""
            from_given = from_given or arg == "--from"
            if not _pinned(spec):
                bad.append(spec)
            skip = True
        elif arg in UV_VALUE_OPTIONS:
            skip = True
        elif arg.startswith("-"):
            continue
        else:
            if not from_given and not _pinned(arg):
                bad.append(arg)
            break
    return bad


def _unpinned_fetches(tokens: list[str]) -> list[str]:
    if tokens[:2] in (["pip", "install"], ["pip3", "install"]):
        return _unpinned_pip(tokens[2:])
    if tokens[:1] == ["uvx"]:
        return _unpinned_uv(tokens[1:])
    if tokens[:3] in (["uv", "tool", "run"], ["uv", "tool", "install"]):
        return _unpinned_uv(tokens[3:])
    if tokens[:2] == ["uv", "run"]:
        # Only what `--with` adds is fetched; the command after it is this project's environment.
        with_specs = [t for i, t in enumerate(tokens) if i and tokens[i - 1] in ("--with", "-w")]
        return [s for s in with_specs if not _pinned(s)]
    return []


@pytest.mark.parametrize("path", [*WORKFLOWS, ACTION], ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for ref in _uses(_load(path)):
        if ref.startswith("./"):
            continue
        assert PINNED_ACTION.match(ref), (
            f"{path.name}: `uses: {ref}` is a mutable ref. Pin the commit its tag points at today, "
            "with the release in a trailing `# vX.Y.Z` comment (see .github/dependabot.yml)"
        )
        line = next(line for line in text.splitlines() if ref in line)
        assert VERSION_COMMENT.search(line), (
            f"{path.name}: `{ref}` has no `# vX.Y.Z` comment, so neither a reviewer nor "
            "Dependabot can tell which release the SHA is"
        )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_fetched_tool_names_its_version(path: Path) -> None:
    unpinned = []
    for command in _commands(_load(path)):
        bad = [
            spec for spec in _unpinned_fetches(_tokens(command))
            if (path.name, spec) not in UNPINNED_ON_PURPOSE
        ]
        if bad:
            unpinned.append(f"`{command}` ({', '.join(bad)})")
    assert not unpinned, (
        f"{path.name} fetches at run time without naming a version, so the job runs whatever "
        f"PyPI serves that minute: {'; '.join(unpinned)}"
    )


def test_the_walk_is_not_vacuous() -> None:
    """A parser that silently found nothing would pass both tests above."""
    refs = [ref for path in [*WORKFLOWS, ACTION] for ref in _uses(_load(path))]
    assert len(refs) >= 40, f"found only {len(refs)} `uses:` refs; is the checkout complete?"
    fetched = {
        tokens[0] if tokens[0] != "uv" else "uv run"
        for path in WORKFLOWS
        for tokens in map(_tokens, _commands(_load(path)))
        if tokens and (tokens[:2] in (["pip", "install"], ["uv", "run"]) or tokens[0] == "uvx")
    }
    assert {"pip", "uvx", "uv run"} <= fetched, f"the command walker saw only {sorted(fetched)}"


@pytest.mark.parametrize(
    ("command", "unpinned"),
    [
        ("pip install pyyaml", ["pyyaml"]),
        ('pip install "modal==1.5.5"', []),
        ("pip install --quiet -e .", []),
        ("python -m pip install --no-cache-dir provael", ["provael"]),
        ("uvx twine check dist/*", ["twine"]),
        ("uvx twine==7.0.0 check dist/*", []),
        ("uvx --from cyclonedx-bom cyclonedx-py environment .venv", ["cyclonedx-bom"]),
        ("uvx --from cyclonedx-bom==7.4.0 cyclonedx-py environment .venv", []),
        ('uv run --no-project --with "huggingface_hub>=0.36" python -', ["huggingface_hub>=0.36"]),
        ("uv run --no-sync python scripts/check_issue_labels.py", []),
        ("expect 'pip install provael'", []),
    ],
)
def test_the_detector_reads_each_installer_form(command: str, unpinned: list[str]) -> None:
    assert _unpinned_fetches(_tokens(command)) == unpinned
