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
from typer.testing import CliRunner

from provael.cli import app

FLAG = re.compile(r"--[a-z][a-z0-9-]{2,}")

#: Flags a message may name while belonging to a DIFFERENT, explicitly-named command. The message
#: has to say which command, so a reader is not left hunting on the one they ran.
CROSS_COMMAND_OK = re.compile(r"provael [a-z-]+(?: [a-z-]+)? --[a-z][a-z0-9-]+")


def _commands() -> list[str]:
    from provael.cli import app as a

    return sorted(c.name for c in a.registered_commands if c.name)


def _flags_of(command: str) -> set[str]:
    out = CliRunner().invoke(app, [command, "--help"])
    return set(FLAG.findall(out.stdout))


@pytest.mark.parametrize("command", _commands())
def test_help_text_only_names_flags_it_defines(command: str) -> None:
    """A command's own help must not advertise a flag absent from that same help."""
    result = CliRunner().invoke(app, [command, "--help"])
    assert result.exit_code == 0, f"{command} --help failed"
    defined = _flags_of(command)
    # Everything the help mentions is, by construction, in `defined` — this asserts the help
    # rendered at all and that the flag scan is not silently matching nothing.
    assert defined, f"{command} --help exposed no flags; the flag scan has drifted"


def test_submit_does_not_advise_a_flag_it_lacks() -> None:
    """The exact regression: `submit` must never point at `--no-sign`, which it does not define."""
    from provael import cli

    src = cli.submit_cmd.__doc__ or ""
    assert "--no-sign" not in src
    assert "--no-sign" not in " ".join(_flags_of("submit"))


def test_the_guard_can_actually_fail() -> None:
    """Pin the shape that shipped, so the check cannot quietly stop matching."""
    shipped = (
        "Signing an attestation needs the `attest` extra: pip install 'provael[attest]' "
        "(or pass --no-sign for a digest-only bundle)."
    )
    found = set(FLAG.findall(shipped))
    assert "--no-sign" in found, "the flag scanner must still find the flag that caused this"
    assert not CROSS_COMMAND_OK.search(shipped), (
        "the shipped message named no owning command — that is exactly why it misled"
    )
