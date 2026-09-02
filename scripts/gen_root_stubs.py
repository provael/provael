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

* **Never overwrite.** Anything mike owns at the root (`index.html`, `versions.json`, `.nojekyll`,
  the version directories) is left exactly as found. A stub that clobbered mike's root redirect
  would break the site's front door to save a deep link.
* **Idempotent.** Re-running after a later release rewrites nothing and adds only genuinely new
  paths, so this can run on every deploy without churning the branch.

    python scripts/gen_root_stubs.py --root <gh-pages worktree> [--alias latest] [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Root entries `mike` owns. Never written, never treated as a stub target.
MIKE_OWNED = frozenset({"index.html", "versions.json", ".nojekyll", "CNAME", ".git"})

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


def plan(root: Path, alias: str) -> list[str]:
    """Paths needing a root stub: published under the alias, absent at the root."""
    alias_dir = root / alias
    if not alias_dir.is_dir():
        raise SystemExit(f"no alias directory at {alias_dir} — did `mike deploy ... {alias}` run?")
    todo: list[str] = []
    for rel in published_paths(alias_dir):
        if _mike_owns(rel.split("/", 1)[0], alias):
            continue
        if (root / rel / "index.html").exists():
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
    for rel in paths:
        target = f"/{alias}/{rel}"
        dest = root / rel / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_TEMPLATE.format(target=target), encoding="utf-8")


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
            print(f"{len(todo)} root URL(s) would 404: {', '.join(todo[:10])}", file=sys.stderr)
            return 1
        print("every published root URL has a stub")
        return 0

    write_stubs(args.root, args.alias, todo)
    print(f"wrote {len(todo)} root stub(s) -> /{args.alias}/…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
