"""Every label an issue FORM declares must exist on the repository.

THE INCIDENT. Six intake forms declared five labels — `attack-family`, `assessment`,
`evidence-integrity`, `leaderboard`, `top10` — and not one of them existed on the repo. GitHub does
not error on an unknown label in an issue form; it drops it silently. So every issue filed through
a form arrived unlabelled, including through `evidence-defect.yml`, which is the channel for
reporting that a published number might be wrong. Nothing surfaced this for as long as the forms
had existed.

This reads the forms, asks `gh` what labels exist, and fails on any gap. It deliberately does NOT
create the missing label: creating it silently is how the next person never learns the form was
wrong, and the fix is one `gh label create`.

Usage:  python scripts/check_issue_labels.py [--repo owner/name]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

TEMPLATES = Path(__file__).resolve().parent.parent / ".github" / "ISSUE_TEMPLATE"


def declared_labels() -> dict[str, list[str]]:
    """Map label -> the forms that declare it, so the error names the file to fix."""
    out: dict[str, list[str]] = {}
    for path in sorted(TEMPLATES.glob("*.yml")):
        if path.name == "config.yml":  # the chooser, not a form
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for label in doc.get("labels") or []:
            out.setdefault(str(label).strip(), []).append(path.name)
    return out


def existing_labels(repo: str | None) -> set[str]:
    cmd = ["gh", "label", "list", "--limit", "200", "--json", "name"]
    if repo:
        cmd += ["--repo", repo]
    raw = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return {row["name"] for row in json.loads(raw)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None, help="owner/name; defaults to the current checkout")
    args = ap.parse_args()

    declared = declared_labels()
    if not declared:
        print("no issue forms declare any labels — nothing to check", file=sys.stderr)
        return 1  # the forms exist; parsing none of their labels means this script is broken

    existing = existing_labels(args.repo)
    missing = {name: forms for name, forms in declared.items() if name not in existing}

    if missing:
        print("Issue-form labels that do NOT exist on the repository:\n", file=sys.stderr)
        for name, forms in sorted(missing.items()):
            print(f"  {name}  — declared by {', '.join(forms)}", file=sys.stderr)
        print(
            "\nGitHub DROPS an unknown label silently, so every issue filed through those forms\n"
            "arrives unlabelled. Create each one:\n\n"
            "  gh label create '<name>' --color RRGGBB --description '...'\n",
            file=sys.stderr,
        )
        return 1

    print(f"All {len(declared)} labels declared by issue forms exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
