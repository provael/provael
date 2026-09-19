# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `provael` command line, split by subject.

WHY A PACKAGE. `cli.py` reached 3,057 lines and 27 top-level commands (issue #193). It was the
file every contributor touched and where every merge conflict landed, and it already carried the
answer: two sub-apps, `leaderboard` and `study`, had been factored out and then the pattern
stopped.

HOW THE SPLIT PRESERVES `provael --help`. Typer renders top-level commands in REGISTRATION order,
and registration happens as each `@app.command(...)` decorator executes — so the order is the
order these modules are imported below, then definition order within each. That makes this import
list load-bearing rather than housekeeping: reordering it reorders `provael --help`, which adopters
read. `tests/test_cli_surface.py` fails on any such move, and the groups were moved out of
`_shared` front-to-back precisely so that every intermediate commit kept the order intact.

`_shared` holds the Typer apps, the two consoles and the helpers used across groups, and is
imported first because every command module imports from it. It is also where anything not yet
moved still lives, so it stays last in the import list until it holds no commands at all.
"""

from __future__ import annotations

from provael.cli._shared import app

# Imported for the REGISTRATION SIDE EFFECT, in this exact order.
#
# `isort: off` is load-bearing, not a style opt-out. ruff's isort sorts these alphabetically, and
# alphabetical order is not registration order — so letting it sort silently reorders
# `provael --help`. `noqa: F401` for the same reason in the other direction: ruff is right that
# the name is unused and wrong that the import is, because deleting one removes its commands from
# the CLI entirely. `tests/test_cli_surface.py` is what actually catches either mistake; these
# two directives just stop the tooling from making it on its own.
#
# isort: off
from provael.cli import core  # noqa: F401
from provael.cli import crosswalk  # noqa: F401
from provael.cli import listings  # noqa: F401
from provael.cli import run  # noqa: F401
from provael.cli import reporting  # noqa: F401
from provael.cli import certify  # noqa: F401
from provael.cli import serve  # noqa: F401
from provael.cli import evidence  # noqa: F401
from provael.cli import calibrate  # noqa: F401
from provael.cli import bounds  # noqa: F401
from provael.cli import status  # noqa: F401
from provael.cli import offline  # noqa: F401
from provael.cli import submit  # noqa: F401
from provael.cli import integrity  # noqa: F401
from provael.cli import defenses  # noqa: F401
from provael.cli import doctor  # noqa: F401

# The two sub-app groups. Their position here does not affect the TOP-LEVEL order — Typer keeps
# `registered_commands` and `registered_groups` in separate lists and renders every command before
# every group — but the order WITHIN each group is still this file's business.
from provael.cli import leaderboard  # noqa: F401
from provael.cli import studies  # noqa: F401

# isort: on

__all__ = ["app"]
