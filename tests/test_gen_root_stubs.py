"""`scripts/gen_root_stubs.py` is what stops docs versioning from 404ing published URLs.

WHY THIS EXISTS. `mike` namespaces every page under a version path, so wiring it moves
`docs.provael.com/top10/` to `/latest/top10/` and the old URL dies. Those URLs are cited from the
marketing site and named in the Top 10's own BibTeX, and this repo's rule is that an old URL stays
old forever. The stub generator is the whole of that promise, so it gets a test rather than a
manual check — a generator that silently writes nothing looks identical to one with no work to do.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gen_root_stubs.py"


def _module() -> Any:
    """Load the script by path — scripts/ is deliberately not an importable package."""
    spec = importlib.util.spec_from_file_location("gen_root_stubs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan = _module().plan
write_stubs = _module().write_stubs


def _tree(root: Path, files: list[str]) -> None:
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")


def _pages(root: Path) -> Path:
    """A gh-pages layout as mike leaves it: a version dir, a copied alias, and its root files."""
    _tree(root, [
        ".nojekyll", "index.html", "versions.json",
        "0.39.1/index.html", "0.39.1/top10/index.html",
        "latest/index.html", "latest/top10/index.html",
        "latest/compliance/index.html", "latest/crosswalk/halos-integrator/index.html",
    ])
    return root


def test_every_published_page_gets_a_root_stub(tmp_path: Path) -> None:
    root = _pages(tmp_path)
    todo = plan(root, "latest")
    assert set(todo) == {"top10/", "compliance/", "crosswalk/halos-integrator/"}
    write_stubs(root, "latest", todo)
    assert "/latest/top10/" in (root / "top10" / "index.html").read_text()
    assert "/latest/crosswalk/halos-integrator/" in (
        root / "crosswalk" / "halos-integrator" / "index.html"
    ).read_text()


def test_the_alias_landing_page_is_not_stubbed_over_mikes_root(tmp_path: Path) -> None:
    """mike owns `/index.html`; a stub there would break the front door to save a deep link."""
    root = _pages(tmp_path)
    before = (root / "index.html").read_text()
    write_stubs(root, "latest", plan(root, "latest"))
    assert (root / "index.html").read_text() == before


def test_mike_owned_paths_are_never_targets(tmp_path: Path) -> None:
    root = _pages(tmp_path)
    _tree(root, ["latest/0.39.1/index.html", "latest/latest/index.html", "latest/versions.json"])
    assert not [p for p in plan(root, "latest") if p.split("/")[0] in {"0.39.1", "latest", "versions.json"}]


def test_it_is_idempotent(tmp_path: Path) -> None:
    root = _pages(tmp_path)
    write_stubs(root, "latest", plan(root, "latest"))
    assert plan(root, "latest") == [], "a second deploy would rewrite stubs and churn the branch"


def test_an_existing_root_page_is_never_overwritten(tmp_path: Path) -> None:
    root = _pages(tmp_path)
    _tree(root, ["top10/index.html"])
    (root / "top10" / "index.html").write_text("HAND WRITTEN", encoding="utf-8")
    write_stubs(root, "latest", plan(root, "latest"))
    assert (root / "top10" / "index.html").read_text() == "HAND WRITTEN"


def test_a_missing_alias_is_an_error_not_a_silent_no_op(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        plan(tmp_path, "latest")


def _case_sensitive() -> bool:
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a").write_text("")
        return not (Path(d) / "A").exists()


@pytest.mark.skipif(
    not _case_sensitive(),
    reason=(
        "filesystem is case-insensitive (macOS default), so TOP10/ and top10/ cannot coexist here. "
        "This asserts the retired UPPERCASE URLs still get their own stub, which is the whole point "
        "of the redirect map in mkdocs.yml — it runs on Linux CI. Reported skipped, never passed."
    ),
)
def test_retired_uppercase_urls_get_their_own_stub(tmp_path: Path) -> None:
    root = _pages(tmp_path)
    _tree(root, ["latest/TOP10/index.html"])
    todo = plan(root, "latest")
    assert "TOP10/" in todo and "top10/" in todo
    write_stubs(root, "latest", todo)
    assert (root / "TOP10" / "index.html").exists()
    assert (root / "top10" / "index.html").exists()
