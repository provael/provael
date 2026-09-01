"""Guard that the Modal examples expose what ``modal run`` actually looks for.

WHY THIS EXISTS. ``examples/gpu-ci/modal_provael_gpu.py`` built its app inside ``build_app()`` so
the module would import without modal installed. ``modal run`` scans a module's GLOBAL scope for
an app and an entrypoint, found neither, and printed "has no functions or local entrypoints". The
scheduled workflow piped that into ``tee``, took tee's exit status, and reported success. The lane
was green and measuring nothing for 22 days; only the freshness badge ageing to 22 days showed it.

This parses the files rather than importing them, so it runs on the CPU lane where modal is absent
— the same lane that has to keep the expensive lane honest.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

EXAMPLES = sorted((pathlib.Path(__file__).parent.parent / "examples" / "gpu-ci").glob("modal_*.py"))


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_declares_a_module_level_app(path: pathlib.Path) -> None:
    """``modal run`` resolves the app from global scope; a nested one is invisible to it."""
    assigned = {
        target.id
        for node in _tree(path).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "app" in assigned, (
        f"{path.name} defines no module-level `app`. If it is built inside a function, "
        "`modal run` reports 'has no functions or local entrypoints' and exits."
    )


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_declares_a_module_level_entrypoint(path: pathlib.Path) -> None:
    """At least one global-scope function must carry ``@app.local_entrypoint()``."""
    decorated = [
        node
        for node in _tree(path).body
        if isinstance(node, ast.FunctionDef)
        for dec in node.decorator_list
        if "local_entrypoint" in ast.dump(dec)
    ]
    assert decorated, f"{path.name} has no module-level @app.local_entrypoint()."


def test_the_guard_can_actually_fail() -> None:
    """Pin the regression against the exact shape that shipped, so it cannot stop matching."""
    shipped = ast.parse(
        "def build_app():\n"
        "    import modal\n"
        "    app = modal.App('x')\n"
        "    @app.local_entrypoint()\n"
        "    def main() -> None: ...\n"
        "    return app\n"
    )
    names = {
        t.id
        for n in shipped.body
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    assert "app" not in names, "the nested-app shape must still be detectable as broken"
