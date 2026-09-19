# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `submit` command: package a run for the public leaderboard."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from provael import __version__
from provael.attest import (
    ATTESTATION_JSON,
    ATTESTATION_PUB,
    MissingAttestExtraError,
    to_bundle,
    write_bundle,
)
from provael.cli._shared import SUBMISSION_REPO, _err, _fail, _git_commit, _out, app
from provael.leaderboard import (
    find_reports,
    validate_report,
)
from provael.report import (
    load_report,
    write_report,
)


@app.command("submit")
def submit_cmd(
    run_dir: Annotated[
        Path,
        typer.Argument(
            help="A run directory containing report.json (from `provael attack --out`)."
        ),
    ],
    submitted_by: Annotated[
        str,
        typer.Option("--submitted-by", help="Your GitHub handle or org — attributed on every row."),
    ],
    key: Annotated[
        Path | None,
        typer.Option("--key", help="Ed25519 private-key PEM to sign with. Omit for ephemeral."),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Submission directory name (default: --submitted-by)."),
    ] = None,
    open_pr: Annotated[
        bool,
        typer.Option("--open-pr/--no-open-pr", help="Open the PR with `gh` (needs gh, authed)."),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Validate and sign and print the payload, touching no network and writing "
            "nothing. Works outside a clone.",
        ),
    ] = False,
) -> None:
    """Validate, sign and submit a run to the public leaderboard — the whole path, one command.

    Three steps that were three documents: validate the report against the submission schema,
    Ed25519-sign it so the numbers are tamper-evident in transit, and open the PR. The submission
    machinery has existed since the board did and has never been exercised by an outsider, which
    is the kind of thing a five-step README causes.

    Nothing here is privileged: it runs against a fork the same way it runs for the maintainer, and
    every step prints the command it ran so a submitter can do it by hand instead. If `gh` is
    missing or unauthenticated the command still validates and signs, then prints the exact
    remaining steps rather than failing at the end with the work thrown away.
    """
    # Checked first, before validating or signing: an outsider running this from any directory
    # that is not a clone got their files written into that directory and then a list of git
    # commands that could not work there. Failing here costs nothing; failing after the signature
    # wastes the one expensive step.
    in_repo = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607 - as above: fixed argv, read-only query
        capture_output=True, text=True, check=False,
    )
    if not dry_run and in_repo.returncode != 0:
        _fail(
            "not inside a git repository, so there is nowhere to stage a submission.\n"
            "  A submission is a pull request, so it needs a clone of your fork:\n"
            "    gh repo fork provael/provael --clone   (or fork on the web, then git clone it)\n"
            "    cd provael && provael submit <your-run-dir> --submitted-by <your-handle>\n"
            "  To see what you WOULD submit without any of that, add --dry-run."
        )
        return

    report_paths = find_reports([str(run_dir)])
    if not report_paths:
        _fail(f"no report.json under {run_dir} — run `provael attack --out {run_dir}` first")
        return
    if len(report_paths) > 1:
        _fail(
            f"{run_dir} holds {len(report_paths)} report.json files; submit one run at a time so "
            "a reviewer can attribute each number to its own protocol"
        )
        return

    try:
        report = load_report(report_paths[0].parent)
    except (FileNotFoundError, ValidationError) as exc:
        _fail(f"{report_paths[0]} is not a readable report.json: {exc}")
        return

    # 1. Validate — the same check the CI workflow runs on arrival, so a submitter sees the
    #    failure here rather than after opening a PR.
    problems = validate_report(report)
    if problems:
        _err.print("[red]submission is not valid:[/red]")
        for problem in problems:
            _err.print(f"  - {problem}")
        raise typer.Exit(2)
    _out.print(f"[green]✓[/green] report validates ({report.policy} × {report.suite})")

    # 2. Sign — tamper-evidence in transit. A reviewer verifies the bundle offline against the
    #    published public half before trusting a single number in the PR.
    issued_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = _git_commit() or f"v{__version__}"
    try:
        bundle, pub_pem = to_bundle(
            report, issued_at=issued_at, commit=stamp,
            private_key_pem=key.read_bytes() if key is not None else None, sign=True,
        )
    except MissingAttestExtraError:
        # NOT `exc`. The shared message ends "(or pass --no-sign for a digest-only bundle)",
        # which is correct advice for `attest` and impossible here: `submit` signs
        # unconditionally and defines no --no-sign, so echoing it sent a blocked user looking
        # for a flag that does not exist. A submission is a claim someone else will act on, so
        # the signature is the point of the command rather than an option on it.
        _fail(
            "Submitting needs the `attest` extra, because a leaderboard row must be "
            "tamper-evident: pip install 'provael[attest]'. There is no unsigned submission "
            "path — use `provael attest --no-sign` if you only want a digest-only bundle."
        )
        return

    slug = (name or submitted_by).strip().replace("/", "__")
    # Under --dry-run the artifacts go to a temp directory, never into results/: a preview that
    # leaves files in someone's tree is not a preview.
    dest = (
        Path(tempfile.mkdtemp(prefix="provael-submit-dry-")) / slug
        if dry_run
        else Path("results") / slug
    )
    dest.mkdir(parents=True, exist_ok=True)
    write_report(report, dest)
    bundle_path = write_bundle(bundle, dest / ATTESTATION_JSON)
    if pub_pem is not None and key is None:
        (dest / ATTESTATION_PUB).write_bytes(pub_pem)
        _err.print(
            "[yellow]note:[/yellow] signed with an ephemeral key (integrity, not identity). "
            "Pass --key to sign as yourself; the public half is published beside the bundle."
        )
    keyid = bundle.signatures[0].keyid if bundle.signatures else "unsigned"
    _out.print(f"[green]✓[/green] signed  keyid {keyid} → [cyan]{bundle_path}[/cyan]")

    # 3. Open the PR. Every step is printed so the manual path is always available.
    branch = f"leaderboard/{slug}"
    title = f"leaderboard: {report.policy} × {report.suite} from {submitted_by}"
    body = (
        f"Leaderboard submission from **{submitted_by}**.\n\n"
        f"- policy × suite: `{report.policy}` × `{report.suite}`\n"
        f"- measured with: `provael {report.tool_version}`\n"
        f"- attempts: {report.attempts} · successes: {report.successes}\n"
        f"- signed: ed25519 keyid `{keyid}`\n\n"
        f"Validated locally with `provael submit`. The Leaderboard submission workflow "
        f"re-validates on arrival; verify the bundle offline with `provael attest --verify "
        f"{dest / ATTESTATION_JSON}`.\n"
    )
    steps = [
        f"git checkout -b {branch}",
        f"git add {dest}",
        f"git commit -m {title!r}",
        f"git push -u origin {branch}",
        f"gh pr create --repo {SUBMISSION_REPO} --title {title!r} --body <the summary above>",
    ]
    if dry_run:
        _out.print("\n[bold]Dry run — nothing was written to this repository and no network "
                   "call was made.[/bold]")
        _out.print(f"Preview artifacts: [cyan]{dest}[/cyan]")
        _out.print("\n[dim]This is exactly what a real submission would contain:[/dim]\n")
        print(json.dumps(json.loads((dest / "report.json").read_text(encoding="utf-8")),
                         indent=2, sort_keys=True)[:1200] + "\n  … (full report at the path above)")
        _out.print("\n[dim]And the PR body it would open with:[/dim]\n")
        print(body)
        _out.print("\nRe-run without --dry-run, from a clone of your fork, to submit.")
        return

    if not open_pr:
        _out.print("\n[bold]Submission staged.[/bold] To open the PR:")
        for step in steps:
            _out.print(f"  {step}")
        return
    if shutil.which("gh") is None:
        _err.print(
            "\n[yellow]gh is not installed[/yellow] — the submission is validated, signed and "
            f"written to {dest}. Finish it with:"
        )
        for step in steps:
            _err.print(f"  {step}")
        # Print the body rather than referring to it. The previous wording said "<the summary
        # above>" on a path where no summary had been printed, so the one instruction a reader
        # could not follow was the last one.
        _err.print("\n[dim]PR body (copy from here):[/dim]\n")
        print(body)
        return
    _out.print(f"\nOpening the PR against {SUBMISSION_REPO}…")
    for cmd in (
        ["git", "checkout", "-b", branch],
        ["git", "add", str(dest)],
        ["git", "commit", "-m", title],
        ["git", "push", "-u", "origin", branch],
        ["gh", "pr", "create", "--repo", SUBMISSION_REPO, "--title", title, "--body", body],
    ):
        _out.print(f"  [dim]$ {' '.join(cmd)}[/dim]")
        # noqa: S603 - `cmd` is drawn from the fixed literal tuple immediately above, never from
        # user input. The interpolated values (branch, title, body) are passed as ARGV elements, not
        # through a shell, so they cannot inject an extra command however they are spelled.
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
        if completed.returncode != 0:
            _err.print(f"[red]step failed:[/red] {completed.stderr.strip() or completed.stdout}")
            _err.print(
                f"The submission is validated and signed in {dest} — finish the remaining steps "
                "by hand (listed above) rather than re-running, so the work is not repeated."
            )
            raise typer.Exit(1)
        if completed.stdout.strip():
            _out.print(f"  {completed.stdout.strip().splitlines()[-1]}")
    _out.print("\n[green]Submitted.[/green] The Leaderboard submission workflow validates it next.")
