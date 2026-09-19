# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The version command."""

from __future__ import annotations

from provael import __version__
from provael.cli._shared import _out, app


@app.command()
def version() -> None:
    """Print the Provael / provael version."""
    _out.print(f"provael (provael) {__version__}")
