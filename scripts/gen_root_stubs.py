# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Keep every pre-versioning docs URL alive after `mike` moved the site under `/latest/`.

WHY THIS EXISTS. `mike` publishes each build under a version path and leaves only a redirect at the
root, so wiring it moves `docs.provael.com/top10/` to `docs.provael.com/latest/top10/` and 404s the
old URL. `alias_type` chooses how an alias is *stored*, not whether content is namespaced, so no
configuration avoids it. Those URLs are published: cited from the marketing site, named in the Top
10's own BibTeX, and probed by name in the docs smoke job. This repo's rule is that an old URL stays
old forever — the uppercase→lowercase migration already paid for that lesson once, and
`mkdocs.yml`'s redirect map is the receipt.

So versioning is bought with stubs rather than with dead links. After `mike deploy`, this walks the
`latest/` tree and writes a meta-refresh page at the matching ROOT path for anything that does not
already exist there. Meta-refresh rather than a real 3xx because GitHub Pages cannot emit one for a
renamed path — the same mechanism, and the same limitation, as `mkdocs-redirects`.

Two properties are load-bearing:

* **Never touch what mike owns.** `index.html`, `versions.json`, `.nojekyll`, `CNAME` and the
  version directories at the root are left exactly as found. A stub that clobbered mike's root
  redirect would break the site's front door to save a deep link.
* **Idempotent.** Re-running after a later release rewrites nothing and adds only genuinely new
  paths, so this can run on every deploy without churning the branch.

WHAT IT DOES OVERWRITE, AND THE INCIDENT THAT DECIDED IT. Until 20 September 2026 this script also
refused to touch any root path that already had an `index.html` — which described the ENTIRE
pre-versioning tree. `gh-pages` still held every page from the last unversioned deploy (`top10/`,
`errata/`, `changelog/`, `compliance/`, the retired uppercase redirect stubs …), so not one cited
root URL ever became a stub: `docs.provael.com/errata/` served a corrections register frozen before
E-2026-10 to E-2026-14 existed, `/top10/` still said 88%, and every docs link on provael.com landed
on that frozen copy. The `smoke` job in docs.yml asserted the stubs and went red on every tag from
v0.42.0 on; a red that is always red reports nothing, and nobody read it. So: a root path that is
NOT already a stub into the alias — a pre-versioning full page, or an old `mkdocs-redirects` stub
pointing at a root sibling — is replaced by the stub. "An old URL stays old" means the URL keeps
resolving, not that it keeps serving the content of the day versioning began.

For an alias path that is itself a redirect stub (the retired uppercase URLs, written by
`mkdocs-redirects` into `latest/TOP10/`), the root stub points straight at the resolved lowercase
target (`/latest/top10/`) rather than hopping through `/latest/TOP10/`: one hop, and the target
string the smoke asserts is in the body.

    python scripts/gen_root_stubs.py --root <gh-pages worktree> [--alias latest] [--check]
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from pathlib import Path

#: Root entries `mike` owns. Never written, never treated as a stub target.
# `dev` is the unaliased version `main` publishes to since 20 September 2026 (docs.yml); it is a
# mike version directory whose name is not numeric, so it is named here rather than caught by the
# digit test in _mike_owns.
MIKE_OWNED = frozenset({"index.html", "versions.json", ".nojekyll", "CNAME", ".git", "dev"})

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Redirecting to {target}</title>
<link rel="canonical" href="{target}">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url={target}">
</head>
<body>
<p>This page moved to <a href="{target}">{target}</a>.</p>
</body>
</html>
"""


def published_paths(alias_dir: Path) -> list[str]:
    """Every directory-style URL the alias serves, as `a/b/` relative paths.

    Derived from the built tree rather than from `mkdocs.yml`'s nav, because the nav does not list
    the `mkdocs-redirects` stubs for the retired uppercase URLs — and those are exactly the paths
    that have already been broken once.
    """
    out: list[str] = []
    for index in sorted(alias_dir.rglob("index.html")):
        rel = index.parent.relative_to(alias_dir)
        if rel == Path("."):
            continue  # the alias's own landing page; the root redirect already covers it
        out.append(f"{rel.as_posix()}/")
    return out


_REDIRECT_TARGET = re.compile(
    r"""http-equiv=["']refresh["'][^>]*url=([^"'>\s]+)""", re.IGNORECASE
)


def stub_target(alias_dir: Path, alias: str, rel: str) -> str:
    """The absolute alias URL a root stub for ``rel`` should name.

    Normally ``/<alias>/<rel>``. When the alias page at ``rel`` is itself a meta-refresh redirect
    (an ``mkdocs-redirects`` stub for a retired URL), resolve its relative target so the root stub
    points at the final page in one hop.
    """
    page = alias_dir / rel / "index.html"
    text = page.read_text(encoding="utf-8", errors="replace") if page.is_file() else ""
    m = _REDIRECT_TARGET.search(text)
    if m and len(text) < 4096:  # a stub is tiny; a real page carrying a refresh tag is not one
        target = m.group(1)
        if target.startswith("/"):
            return target
        resolved = posixpath.normpath(posixpath.join(f"/{alias}/{rel}", target))
        return resolved if resolved.endswith("/") else resolved + "/"
    return f"/{alias}/{rel}"


def expected_stub(alias_dir: Path, alias: str, rel: str) -> str:
    return _TEMPLATE.format(target=stub_target(alias_dir, alias, rel))


def plan(root: Path, alias: str) -> list[str]:
    """Paths needing a root stub: published under the alias, and not already the right stub.

    "Not already the right stub" covers three states, all rewritten: no file at the root, a
    pre-versioning full page, and a stub naming a stale target. A byte-identical stub is left
    alone, which is what keeps a re-run from churning the branch.
    """
    alias_dir = root / alias
    if not alias_dir.is_dir():
        raise SystemExit(f"no alias directory at {alias_dir} — did `mike deploy ... {alias}` run?")
    todo: list[str] = []
    for rel in published_paths(alias_dir):
        if _mike_owns(rel.split("/", 1)[0], alias):
            continue
        current = root / rel / "index.html"
        if current.is_file() and current.read_text(encoding="utf-8", errors="replace") == (
            expected_stub(alias_dir, alias, rel)
        ):
            continue
        todo.append(rel)
    return todo


def _mike_owns(top: str, alias: str) -> bool:
    """Whether the first path segment belongs to mike rather than to us.

    A docs page whose top-level directory collides with the alias or with a version directory is
    left alone: overwriting `latest/` or `0.39.2/` to rescue a deep link would take the site down
    to save a bookmark.
    """
    if top in MIKE_OWNED or top == alias:
        return True
    return top.lstrip("v").split(".", 1)[0].isdigit()


def write_stubs(root: Path, alias: str, paths: list[str]) -> None:
    alias_dir = root / alias
    for rel in paths:
        dest = root / rel / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(expected_stub(alias_dir, alias, rel), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, type=Path, help="gh-pages worktree")
    ap.add_argument("--alias", default="latest", help="alias the stubs point at (default: latest)")
    ap.add_argument(
        "--check", action="store_true", help="exit 1 if any stub is missing; write nothing"
    )
    args = ap.parse_args(argv)

    todo = plan(args.root, args.alias)
    if args.check:
        if todo:
            print(
                f"{len(todo)} root URL(s) would 404 or serve a pre-versioning page: "
                f"{', '.join(todo[:10])}",
                file=sys.stderr,
            )
            return 1
        print("every published root URL is a stub into the alias")
        return 0

    write_stubs(args.root, args.alias, todo)
    print(f"wrote {len(todo)} root stub(s) -> /{args.alias}/…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
