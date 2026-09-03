"""No command may advise a flag it does not define.

WHY THIS EXISTS. ``provael submit`` signs unconditionally and defines no ``--no-sign``, but the
shared ``MissingAttestExtraError`` it echoed ends "(or pass --no-sign for a digest-only bundle)" —
correct advice for ``attest``, impossible for ``submit``. A user without the ``attest`` extra was
told to reach for a flag that does not exist, on the one command whose failure blocks a
contribution. The message was right about the extra and wrong about the escape hatch, which is the
worse half to get wrong: the extra is discoverable, the missing flag sends you reading ``--help``
for something that was never there.

This walks the real Typer app rather than grepping source, so a command that gains an error string
mentioning a flag it lacks fails here even if the string is built at runtime.
"""

from __future__ import annotations

import re

import pytest
import typer.main

from provael.cli import app

FLAG = re.compile(r"--[a-z][a-z0-9-]{2,}")

#: Flags a message may name while belonging to a DIFFERENT, explicitly-named command. The message
#: has to say which command, so a reader is not left hunting on the one they ran.
CROSS_COMMAND_OK = re.compile(r"(?:provael\s+)?([a-z][a-z0-9-]*)\s+(--[a-z][a-z0-9-]+)")

#: Click appends `--help` when it resolves a command rather than storing it on the object, so it
#: never appears in `.params`. Materialising it would mean building a Context out of typer's
#: VENDORED `typer._click` — a private module that moves between typer releases. Naming the one
#: implicit option is the smaller commitment, and `test_every_command_resolves` below fails if the
#: introspection this file depends on ever stops working.
IMPLICIT_FLAGS = frozenset({"--help"})


def _commands() -> list[str]:
    from provael.cli import app as a

    return sorted(c.name for c in a.registered_commands if c.name)


def _click_command(command: str) -> object:
    group = typer.main.get_command(app)
    cmd = getattr(group, "commands", {}).get(command)
    assert cmd is not None, f"{command} is registered on the Typer app but absent from the Click group"
    return cmd


def _defined_flags(command: str) -> set[str]:
    """Long options the command actually defines, read from the Click objects Typer builds.

    NOT scraped from rendered ``--help``. That is what this test used to do, and it is why
    SIXTEEN of these — every parametrised case — failed on Linux CI while passing on macOS: the
    scrape returned the empty set and the canary below fired. Rich decides borders, wrapping and
    glyphs from terminal width, TERM and colour support, so the same command renders differently
    on two machines that are otherwise identical. `tests/test_roadmap_honesty.py` records the same
    lesson after it failed the RELEASE gate at v0.38.0, in one line worth repeating: parsing a
    human-facing rendering for a structural fact is the bug.

    Nobody saw the sixteen because the pytest step piped into `tee` without `pipefail`, so the job
    reported success anyway (#183).
    """
    flags: set[str] = set(IMPLICIT_FLAGS)
    for param in _click_command(command).params:  # type: ignore[attr-defined]
        for opt in list(param.opts) + list(param.secondary_opts):
            if opt.startswith("--"):
                flags.add(opt)
    return flags


def _flags_attributed_elsewhere(text: str) -> set[str]:
    """Flags the text may name because it says which command owns them.

    The word before the flag has to be a REAL registered command, not merely any word. `provael`
    itself is optional: `list-recipes` describes presets for "`attack --recipe`", which names the
    owner perfectly well, and demanding the binary name would have failed that on a technicality
    while `... or pass --no-sign ...` — where the preceding word is "pass" — still fails, which is
    the message this module was written for.
    """
    # Every command the CLI actually exposes, not just `app.registered_commands`: `attack` is
    # reachable as `provael attack` but is not in that list, and it owns both the flags legitimately
    # named from other commands' help.
    known = set(getattr(typer.main.get_command(app), "commands", {}))
    return {
        flag for owner, flag in CROSS_COMMAND_OK.findall(text) if owner in known
    }


def _declared_help(command: str) -> str:
    """Every help string the command DECLARES, unrendered — the text a maintainer wrote.

    The regression this module exists for was a runtime error string, not a rendered table, so the
    declared strings are both the right place to look and the only place that reads identically on
    every machine.
    """
    cmd = _click_command(command)
    parts = [getattr(cmd, "help", "") or "", getattr(cmd, "short_help", "") or ""]
    parts += [getattr(p, "help", "") or "" for p in cmd.params]  # type: ignore[attr-defined]
    return "\n".join(parts)


@pytest.mark.parametrize("command", _commands())
def test_help_text_only_names_flags_it_defines(command: str) -> None:
    """A command's own help must not advertise a flag absent from that same command."""
    defined = _defined_flags(command)
    text = _declared_help(command)
    # A flag belonging to another command is fine, but only where the text names the command that
    # owns it — that is the whole difference between useful advice and sending someone hunting.
    stray = {f for f in FLAG.findall(text) if f not in defined} - _flags_attributed_elsewhere(text)
    assert not stray, (
        f"{command} help names {sorted(stray)}, which it does not define. Either define the flag, "
        f"name the command that owns it (`provael <cmd> {sorted(stray)[0]}`), or drop the advice."
    )


def test_submit_does_not_advise_a_flag_it_lacks() -> None:
    """The exact regression: `submit` must never point at `--no-sign`, which it does not define."""
    from provael import cli

    src = cli.submit_cmd.__doc__ or ""
    assert "--no-sign" not in src
    assert "--no-sign" not in _defined_flags("submit")


def test_the_guard_can_actually_fail() -> None:
    """Pin the shape that shipped, so the check cannot quietly stop matching."""
    shipped = (
        "Signing an attestation needs the `attest` extra: pip install 'provael[attest]' "
        "(or pass --no-sign for a digest-only bundle)."
    )
    found = set(FLAG.findall(shipped))
    assert "--no-sign" in found, "the flag scanner must still find the flag that caused this"
    assert not _flags_attributed_elsewhere(shipped), (
        "the shipped message named no owning command — that is exactly why it misled"
    )


def test_every_command_resolves_to_a_click_command() -> None:
    """The canary, structural this time.

    The assertion it replaces read `--help` output and checked the scrape was not empty. That is
    the check that failed sixteen times on Linux CI while passing on macOS, because it was reading
    a rendering. This reads the object graph instead, so it fails when the introspection genuinely
    breaks and not when Rich picks different glyphs.
    """
    commands = _commands()
    assert commands, "the Typer app registered no commands at all"
    for command in commands:
        assert _defined_flags(command), f"{command} resolved but exposed no flags, not even --help"
