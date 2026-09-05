"""`docs/python-api.md` and `provael.__all__` must describe the same public surface.

THE GAP THIS CLOSES. `docs/python-api.md` is the published Python API and nothing enforced it.
`src/provael/__init__.py` defined no `__all__` at all, so there was no declared export list for a
rename to disagree with: a symbol could move or be renamed, every gate stays green, and the docs go
on describing an import that no longer resolves. The failure is silent in both directions -- a name
documented but not exported, and a name exported but never documented.

WHAT IS ASSERTED. Exactly three things:

  1. The documented names and `__all__` are the same set. Either direction fails.
  2. Every name in `__all__` actually resolves through the lazy `__getattr__`.
  3. Importing `provael` stays cheap.

(3) is not padding. Every documented name lives in a submodule, and re-exporting them eagerly costs
~1.14 s and pulls numpy in, against ~1.1 ms for the bare package -- a ~1000x regression paid by
every `import provael` and by CLI startup. `__init__.py` therefore resolves them lazily (PEP 562),
and the cheap way to undo that is someone adding a convenience `from provael.runner import run` at
the top of the file. This test notices.

HOW A NAME COUNTS AS DOCUMENTED. Two forms, because the doc uses both:

  * an import statement in a code fence -- `from provael.config import RunConfig`;
  * a backticked symbol linked into `src/provael/` -- ``[`SuiteAdapter`](.../suites/base.py)``,
    which is how the doc introduces the suite ABC without a runnable snippet.

Links into `examples/` are documentation of files, not of exported symbols, and are ignored.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

import provael

DOC = Path(__file__).resolve().parents[1] / "docs" / "python-api.md"

#: `from provael.<module> import <Name>` inside a fenced block.
_IMPORT_RE = re.compile(r"^from\s+(provael[\w.]*)\s+import\s+([A-Za-z_][\w]*)\s*$", re.MULTILINE)

#: ``[`Name`](<url containing src/provael/>)`` -- a symbol the doc links to its definition.
_LINKED_SYMBOL_RE = re.compile(r"\[`([A-Za-z_][\w]*)`\]\(([^)]*src/provael/[^)]*)\)")


def documented_names() -> set[str]:
    """Every exported symbol `docs/python-api.md` names, by either documented form."""
    text = DOC.read_text(encoding="utf-8")
    names = {m.group(2) for m in _IMPORT_RE.finditer(text)}
    names |= {m.group(1) for m in _LINKED_SYMBOL_RE.finditer(text)}
    return names


def exported_names() -> set[str]:
    """`__all__` minus the dunder, which is metadata rather than a documented export."""
    return {name for name in provael.__all__ if not name.startswith("__")}


def test_docs_and_all_describe_the_same_surface() -> None:
    """Neither direction may drift: documented-but-unexported, or exported-but-undocumented."""
    documented = documented_names()
    exported = exported_names()
    assert documented, f"parsed no symbols out of {DOC} -- the parser, not the API, is broken"
    undocumented = exported - documented
    unexported = documented - exported
    assert not unexported, (
        f"{sorted(unexported)} documented in docs/python-api.md but missing from "
        "provael.__all__ -- either export it or stop documenting it"
    )
    assert not undocumented, (
        f"{sorted(undocumented)} exported in provael.__all__ but absent from "
        "docs/python-api.md -- an undocumented public name is a support burden nobody agreed to"
    )


@pytest.mark.parametrize("name", sorted(exported_names()))
def test_every_exported_name_resolves(name: str) -> None:
    """`__all__` promising a name that `__getattr__` cannot produce is worse than no `__all__`."""
    assert getattr(provael, name) is not None


def test_unknown_attribute_still_raises_attribute_error() -> None:
    """A module `__getattr__` that swallows misses would break `hasattr` and autocomplete."""
    with pytest.raises(AttributeError):
        provael.definitely_not_exported  # noqa: B018


def test_dir_lists_the_exports() -> None:
    """The lazy names must stay discoverable, or `dir()` reports a smaller API than exists."""
    assert exported_names() <= set(dir(provael))


def test_importing_provael_stays_lazy() -> None:
    """`import provael` must not drag in the submodules -- that is the whole point of PEP 562.

    Run in a subprocess: this test session has already imported half the package, so an in-process
    check of `sys.modules` would pass no matter what `__init__.py` did.
    """
    probe = (
        "import sys, provael;"
        "eager=[m for m in ('numpy','provael.runner','provael.scorecard','provael.oscal',"
        "'provael.avid','provael.policies.registry') if m in sys.modules];"
        "print(','.join(eager))"
    )
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    eager = [m for m in out.stdout.strip().split(",") if m]
    assert not eager, (
        f"`import provael` eagerly imported {eager}. The documented names are lazy on purpose: "
        "importing them here costs ~1.14 s against ~1.1 ms, on every import and every CLI "
        "invocation. Resolve them in __getattr__, not at module top level."
    )
