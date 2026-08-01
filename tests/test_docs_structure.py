"""Structural guards for the MkDocs site: reachable section hubs, and no case-colliding URLs.

Two defect classes, both invisible to a normal build because MkDocs is happy to publish them.

**A section with no landing page.** ``docs/findings/``, ``docs/studies/`` and ``docs/standards/``
each held several pages and appeared in the nav as a section, but a section in MkDocs is a grouping
label, not a page. Every child resolved; the hub URL 404'd. A certifier clicking "Standards" — the
first thing that audience clicks — got nothing, while the pages they wanted sat one level down,
indexed and linked from elsewhere. ``mkdocs build --strict`` does not catch this: there is no
broken link, because nothing linked to the hub.

**A path that collides only on a case-sensitive filesystem.** ``docs/COMPLIANCE.md`` built to
``site/COMPLIANCE/index.html`` while ``docs/compliance/`` built to ``site/compliance/…``. On Linux —
CI, and the server — those are two separate URL namespaces. On macOS, where most of this is
authored, they are the *same directory*, so the collision was silently merged and a developer could
not see it locally. That asymmetry is the whole reason this is a test and not a code review item.
(Resolved by the lowercase migration, which folded the page in as ``compliance/index.md``.)

**Uppercase filenames.** The same root cause, one step earlier: a file named ``TOP10.md`` publishes
at ``/TOP10/``, so every lowercase guess 404s and any pipeline that normalises case breaks the link.
Filenames are held lowercase so the collision class cannot be reintroduced.

All checks read the source tree rather than ``site/``, so they run without a docs build.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"

#: Directories allowed to have no landing page. ``assets`` holds images, not pages — it is the only
#: entry, and the intent is that it stays that way. ``maintainers`` was listed here while its
#: runbooks were publicly served but absent from the nav; they are now in the nav with a hub, so the
#: exemption is gone rather than left behind quietly suppressing a real check.
_NO_HUB_REQUIRED = frozenset({"assets"})

#: Case collisions recorded rather than hidden. **Empty, and that is the goal.**
#:
#: This held ``compliance`` while ``docs/COMPLIANCE.md`` and ``docs/compliance/`` coexisted. The
#: lowercase migration folded the page in as ``compliance/index.md``, which closed the collision and
#: gave the directory its landing page in one move. Keep the constant: it is the mechanism for
#: recording a *new* collision honestly if one is ever introduced deliberately, and
#: ``test_known_case_collisions_still_exist`` guarantees an entry cannot outlive its cause.
_KNOWN_CASE_COLLISIONS: frozenset[str] = frozenset()

#: A directory counts as reachable if it carries either of these. MkDocs renders both as the
#: directory index; ``crosswalk/`` legitimately uses README.md.
_INDEX_NAMES = ("index.md", "README.md")


def _content_dirs() -> list[Path]:
    """Every docs subdirectory that actually holds Markdown pages."""
    return sorted(
        d for d in DOCS.iterdir() if d.is_dir() and any(d.glob("*.md"))
    )


def test_every_docs_section_has_a_landing_page() -> None:
    """A directory of pages must answer at its own URL, not only at its children's."""
    missing = [
        d.name
        for d in _content_dirs()
        if d.name not in _NO_HUB_REQUIRED
        and not any((d / n).is_file() for n in _INDEX_NAMES)
    ]
    assert not missing, (
        "docs section(s) with pages but no landing page (the hub URL will 404): "
        f"{missing}. Add an index.md, or add the directory to _NO_HUB_REQUIRED with a reason."
    )


def test_no_docs_path_collides_by_case_alone() -> None:
    """Two docs paths differing only by case become one URL on macOS and two on Linux.

    This is asserted over the source tree because the built ``site/`` cannot show it on a
    case-insensitive filesystem — the merge has already happened by the time you can look.
    """
    stems: dict[str, list[str]] = {}
    for p in DOCS.rglob("*"):
        if p.name.startswith("."):
            continue
        rel = p.relative_to(DOCS).as_posix()
        # A page foo.md and a directory foo/ both publish at /foo/.
        url = rel[:-3] if rel.endswith(".md") else rel
        stems.setdefault(url.lower(), []).append(rel)
    collisions = {
        k: sorted(set(v))
        for k, v in stems.items()
        if len(set(v)) > 1 and k not in _KNOWN_CASE_COLLISIONS
    }
    assert not collisions, (
        "docs paths that publish to the same URL on a case-insensitive filesystem but "
        f"different URLs on Linux: {collisions}"
    )


def test_known_case_collisions_still_exist() -> None:
    """The exemption list must not outlive the problem it exempts.

    If a listed collision has been resolved, this fails so the entry is deleted rather than left
    behind quietly suppressing a check that would otherwise be doing work.
    """
    for name in _KNOWN_CASE_COLLISIONS:
        page = DOCS / f"{name.upper()}.md"
        directory = DOCS / name
        assert page.is_file() and directory.is_dir(), (
            f"{name!r} is listed in _KNOWN_CASE_COLLISIONS but the collision is gone — "
            "remove the entry (and its _NO_HUB_REQUIRED counterpart)."
        )


def test_docs_filenames_are_lowercase() -> None:
    """An uppercase filename publishes an uppercase, case-sensitive URL.

    ``README.md`` is exempt: MkDocs renders it as the directory index, so it never becomes a URL
    segment of its own, and the name is a strong convention outside this project.
    """
    offenders = [
        p.relative_to(DOCS).as_posix()
        for p in DOCS.rglob("*.md")
        if p.name != "README.md" and p.stem != p.stem.lower()
    ]
    assert not offenders, (
        "docs filename(s) with uppercase characters — these publish case-sensitive URLs that "
        f"404 on any lowercase guess: {offenders}"
    )


def test_retired_uppercase_urls_still_redirect() -> None:
    """Every renamed page keeps a 301 from its old URL. An old URL stays old forever.

    Without this the rename simply moves the breakage: the uppercase URLs are the ones already
    published, cited in the Top 10's own BibTeX entry, and linked from the marketing site.
    """
    cfg = (REPO / "mkdocs.yml").read_text(encoding="utf-8")
    for old, new in (
        ("TOP10.md", "top10.md"),
        ("TOP10_RFC.md", "top10-rfc.md"),
        ("DEFENSES.md", "defenses.md"),
        ("COMPLIANCE.md", "compliance/index.md"),
        ("ATTESTATION.md", "attestation.md"),
        ("SIM_PREDICTS_REAL.md", "sim-predicts-real.md"),
        ("ADOPTERS.md", "adopters.md"),
        ("COMMUNITY.md", "community.md"),
        ("MEASURE-2-7.md", "measure-2-7.md"),
        ("maintainers/HOSTED_PRODUCTION_REQUIREMENTS.md", "maintainers/hosted-production-requirements.md"),
        ("maintainers/GITHUB_SECURITY_SETTINGS.md", "maintainers/github-security-settings.md"),
    ):
        assert f"'{old}': '{new}'" in cfg, f"no redirect from the retired URL {old} -> {new}"
        assert (DOCS / new).is_file(), f"redirect target {new} does not exist"


def test_no_code_references_a_retired_uppercase_docs_filename() -> None:
    """Catches the rename bug that macOS structurally cannot show you.

    The lowercase migration replaced the literal string ``docs/TOP10.md`` everywhere it appeared -
    but several tests build the path from separate components, ``REPO / "docs" / "TOP10.md"``, which
    that search never matched. On macOS the stale references kept working, because the filesystem is
    case-insensitive and ``TOP10.md`` still resolves to ``top10.md``. On Linux CI they were a
    FileNotFoundError, and six tests failed.

    The deeper error was in the verification, not the fix: the grep used to confirm the migration was
    the SAME pattern as the sed used to perform it, so it could only ever report success. A check
    that shares its blind spot with the change it verifies is not a check.

    This searches for the retired BASENAME in any quoted form, so a split path cannot hide. The
    redirect map in this file legitimately names the old paths and is exempt by construction: it is
    matched by filename, not by content.
    """
    retired = (
        "TOP10.md", "TOP10_RFC.md", "DEFENSES.md", "COMPLIANCE.md", "ATTESTATION.md",
        "ADOPTERS.md", "COMMUNITY.md", "SIM_PREDICTS_REAL.md", "MEASURE-2-7.md",
    )
    offenders: list[str] = []
    for path in REPO.rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith((".venv/", "site/")) or path.name == "test_docs_structure.py":
            continue
        body = path.read_text(encoding="utf-8")
        for name in retired:
            if f'"{name}"' in body or f"'{name}'" in body:
                offenders.append(f"{rel} -> {name}")
    assert not offenders, (
        "code references a docs filename retired by the lowercase migration. These resolve on a "
        f"case-insensitive filesystem and raise FileNotFoundError on Linux: {offenders}"
    )


def test_the_docs_reach_the_commercial_offer() -> None:
    """The docs had zero routes to the operated work — a dead end for a convinced reader.

    Of ~50 docs files, none linked to /assessment, /pricing or the sample pack. A reader who got
    through the technical corpus, decided the tooling was right and wanted someone to run it had
    nowhere to go. This asserts at least one route exists; it deliberately does not demand many,
    because the docs are documentation and a link farm would be worse than the dead end.
    """
    routes = ("provael.com/pricing", "provael.com/assessment", "provael.com/sample-evidence-pack")
    linking = [
        p.relative_to(DOCS).as_posix()
        for p in DOCS.rglob("*.md")
        if any(r in p.read_text(encoding="utf-8") for r in routes)
    ]
    assert linking, (
        "no docs page links to the commercial offer — a reader convinced by the docs has no route "
        f"to the operated work. Expected at least one of {routes}."
    )


def test_the_scan_actually_finds_sections() -> None:
    """Guard the guard: an empty scan passes both assertions above."""
    dirs = _content_dirs()
    assert len(dirs) >= 4, f"only {len(dirs)} content dirs found — the scan is not working"
    assert {"findings", "studies", "standards"} <= {d.name for d in dirs}


def test_every_nav_target_exists() -> None:
    """A nav entry naming a file that does not exist renders as a dead section."""
    cfg = (REPO / "mkdocs.yml").read_text(encoding="utf-8")

    class _Loose(yaml.SafeLoader):
        pass

    _Loose.add_multi_constructor("tag:yaml.org,2002:python/name:", lambda *_: None)
    nav = yaml.load(cfg, Loader=_Loose).get("nav") or []

    targets: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            targets.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(nav)
    missing = [t for t in targets if t.endswith(".md") and not (DOCS / t).is_file()]
    assert not missing, f"nav names file(s) that do not exist: {missing}"
