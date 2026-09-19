"""`evidence-manifest` and `attest`: the signed-evidence path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from provael import __version__
from provael.assurance import AssuranceProfile, build_assurance
from provael.attest import (
    ATTESTATION_JSON,
    ATTESTATION_PUB,
    EXIT_OK,
    RULESET_VERSION,
    MissingAttestExtraError,
    load_bundle,
    load_trust_store,
    to_bundle,
    verify_bundle,
    verify_exit_code,
    write_bundle,
)
from provael.calibration import (
    load_calibrations,
    wilson_ci,
)
from provael.cli._shared import (
    _decide,
    _decision_for,
    _err,
    _fail,
    _git_commit,
    _load_protocol,
    _out,
    _split_csv,
    app,
)
from provael.compliance import write_compliance_markdown
from provael.config import RunConfig
from provael.manifest import to_evidence_manifest_json
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from provael.report import (
    benign_control_text,
    load_report,
    render_summary,
    write_report,
)
from provael.runner import run


@app.command(name="evidence-manifest")
def evidence_manifest(
    in_dir: Annotated[
        Path, typer.Option("--in", "--report", help="Directory with a report.json to describe.")
    ],
    commit: Annotated[
        str,
        typer.Option("--commit", help="Pinned source commit (required — never a moving branch)."),
    ],
    repo: Annotated[
        str, typer.Option("--repo", help="Source repository URL.")
    ] = "https://github.com/provael/provael",
    out: Annotated[
        Path, typer.Option("--out", help="Output path for the manifest JSON.")
    ] = Path("artifacts/public-evidence-manifest.json"),
    protocol: Annotated[
        Path | None,
        typer.Option(
            "--protocol",
            help="Acceptance protocol (YAML/JSON) the manifest's release decision is made against. "
            "Without it the run's report.decision.json is used when present, else the manifest "
            "says the run was not assessed.",
        ),
    ] = None,
) -> None:
    """Build the deterministic public evidence manifest a website can consume.

    Restates the honest metric semantics (adversarial ASR vs the all-episode rate vs the benign
    control), per-attack results with Wilson intervals and applicability (N/A stays N/A), the
    evidence-ladder state, the release verdict, and the limitations. It pins its source commit and
    carries no wall-clock, so the same report + commit yields byte-identical output.
    """
    # A SHARDED run has no report.json of its own — a ten-task suite executed one task per
    # container writes ten of them, and there is deliberately no merged file (see provael.combine:
    # a file named report.json is treated as attestable everywhere in this project, and a combined
    # view has no single execution to attest). So detect the shape and record every shard's digest
    # rather than one.
    from provael.combine import (
        ShardMismatchError,
        combine_reports,
        is_sharded,
        load_shards,
        shard_digests,
    )

    source_reports: list[dict[str, str]] | None = None
    if is_sharded(in_dir):
        shards = load_shards(in_dir)
        try:
            report = combine_reports([r for _, r in shards])
        except ShardMismatchError as exc:
            _fail(str(exc))
            return
        source_reports = shard_digests(shards, root=in_dir)
        _out.print(
            f"[cyan]sharded run[/cyan]: combining {len(shards)} report(s) across "
            f"{len(report.tasks)} task(s); every shard digest is recorded"
        )
    else:
        try:
            report = load_report(in_dir)
        except (FileNotFoundError, ValidationError):
            _fail(f"{in_dir} contains neither a report.json nor */report.json shards")
            return
    decision = _decision_for(in_dir, report, protocol)
    try:
        text = to_evidence_manifest_json(
            report, repository=repo, commit=commit, regulatory_clock_version=RULESET_VERSION,
            source_reports=source_reports, decision=decision,
        )
    except ValueError as exc:
        _fail(str(exc))
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    _out.print(f"[green]wrote[/green] evidence manifest -> {out}")


@app.command()
def attest(
    in_dir: Annotated[
        Path | None,
        typer.Option(
            "--in", "--run",
            help="Directory with a prior report.json (RunReport) to attest. Omit to run one.",
        ),
    ] = None,
    profile: Annotated[
        AssuranceProfile | None,
        typer.Option(
            "--profile",
            help="Embed a standards-aligned assurance view: iso-10218-2 | iec-62443 | insurer.",
        ),
    ] = None,
    policy: Annotated[str, typer.Option(help="Policy to run (when --in is omitted).")] = "stub",
    suite: Annotated[str, typer.Option(help="Suite to run (when --in is omitted).")] = "stub",
    attacks: Annotated[
        str, typer.Option(help="Attacks to run when --in is omitted. Keep 'none' for the control.")
    ] = "none,instruction",
    episodes: Annotated[int, typer.Option(min=1, help="Episodes per (task, attack) pair.")] = 10,
    seed: Annotated[int, typer.Option(min=0, help="Base random seed.")] = 0,
    calib: Annotated[
        Path | None, typer.Option("--calib", help="Calibration dir (from `provael calibrate`).")
    ] = None,
    key: Annotated[
        Path | None,
        typer.Option("--key", help="Ed25519 private-key PEM to sign with. Omit for ephemeral."),
    ] = None,
    no_sign: Annotated[
        bool, typer.Option("--no-sign", help="Emit a digest-only bundle (no signature, no extra).")
    ] = False,
    verify: Annotated[
        Path | None,
        typer.Option("--verify", help="Verify an existing attestation.json instead of issuing."),
    ] = None,
    pubkey: Annotated[
        Path | None, typer.Option("--pubkey", help="Public-key PEM to verify a signed bundle with.")
    ] = None,
    trust_store: Annotated[
        Path | None,
        typer.Option(
            "--trust-store",
            help="Local trust store (JSON) of trusted signer keys. Strict --verify needs it: a "
            "valid signature from an unknown key is authentic but UNTRUSTED.",
        ),
    ] = None,
    subject_report: Annotated[
        Path | None,
        typer.Option(
            "--report",
            help="A report.json to independently recheck against the attested subject digest "
            "(--verify). Without it, the embedded digest is not independently confirmed.",
        ),
    ] = None,
    integrity_only: Annotated[
        bool,
        typer.Option(
            "--integrity-only",
            help="Grade only the digest layer (--verify): pass if the payload is intact, WITHOUT "
            "establishing signer identity or trust. Never reported as plain 'verified'.",
        ),
    ] = False,
    commit: Annotated[
        str | None, typer.Option("--commit", help="Override the source commit stamp.")
    ] = None,
    out: Annotated[
        Path, typer.Option(help="Output directory for the bundle.")
    ] = Path("runs/attest"),
    protocol: Annotated[
        Path | None,
        typer.Option(
            "--protocol",
            help="Acceptance protocol (YAML/JSON) the attested release decision is made against. "
            "Without it a prior run's report.decision.json is used when present, else the bundle "
            "states the run was not assessed.",
        ),
    ] = None,
) -> None:
    """Issue (or verify) a signed, dated, standards-crosswalked ASR evidence bundle.

    `attest` wraps the SAME compliance evidence as `report --format compliance` — the ASR with its
    95% Wilson CI, the benign-FPR control, the per-EAI breakdown, and the EU/ISO/NIST/IEC crosswalk
    — then binds it with a SHA-256 digest, stamps a UTC date + ruleset + commit, and signs a
    DSSE-style envelope (Ed25519). `--profile` embeds a standards-aligned assurance view
    (ISO 10218-2 -> IEC 62443 SL2, or an insurer summary) with the honest per-family transfer table
    and a third-party cert-readiness cross-reference. It is evidence, not certification.
    """
    # -- verification mode -------------------------------------------------------------------
    if verify is not None:
        try:
            bundle = load_bundle(verify)
        except (FileNotFoundError, ValidationError):
            _fail(f"{verify} is not a readable attestation bundle")
            return
        pub_bytes = pubkey.read_bytes() if pubkey is not None else None
        store = None
        if trust_store is not None:
            try:
                store = load_trust_store(trust_store)
            except (FileNotFoundError, ValidationError):
                _fail(f"{trust_store} is not a readable trust store")
                return
        subject = None
        if subject_report is not None:
            try:
                subject = load_report(subject_report)
            except (FileNotFoundError, ValidationError):
                _fail(f"{subject_report} does not contain a valid report.json")
                return
        try:
            result = verify_bundle(
                bundle,
                public_key_pem_bytes=pub_bytes,
                trust_store=store,
                subject_report=subject,
                now=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        except MissingAttestExtraError as exc:
            _fail(str(exc))
            return
        for reason in result.reasons:
            _out.print(f"  - {reason}")
        code = verify_exit_code(result, integrity_only=integrity_only)
        if code == EXIT_OK and integrity_only:
            _out.print(
                "[yellow]attestation INTEGRITY-ONLY OK[/yellow] — payload intact; signer identity "
                "and trust NOT established"
            )
        elif code == EXIT_OK:
            _out.print("[green]attestation STRICT OK[/green] — integrity + trusted signature")
        else:
            _fail(
                f"attestation verification FAILED [{'/'.join(result.codes) or 'not strict-OK'}]",
                code=code,
            )
        return

    # -- issuance mode -----------------------------------------------------------------------
    if in_dir is not None:
        try:
            report = load_report(in_dir)
        except FileNotFoundError as exc:
            _fail(str(exc))
            return
        except ValidationError:
            _fail(f"{in_dir} does not contain a valid Provael report.json")
            return
        decision = _decision_for(in_dir, report, protocol)
    else:
        acceptance = _load_protocol(protocol)
        calibrations = load_calibrations(calib, policy, suite) if calib is not None else None
        try:
            config = RunConfig(
                policy=policy, suite=suite, attacks=_split_csv(attacks) or ["none", "instruction"],
                episodes=episodes, seed=seed, out=out,
            )
            report = run(config, calibrations)
        except (MissingLeRobotError, IncompatiblePolicyError, NotImplementedError) as exc:
            _fail(str(exc))
            return
        except KeyError as exc:
            _fail(str(exc).strip('"'))
            return
        decision = _decide(report, acceptance)
        write_report(report, out, decision)

    issued_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = commit or _git_commit() or f"v{__version__}"
    private_key_pem = key.read_bytes() if key is not None else None
    assurance = (
        build_assurance(report, profile, issued_at=issued_at, commit=stamp)
        if profile is not None else None
    )

    try:
        bundle, pub_pem = to_bundle(
            report, issued_at=issued_at, commit=stamp,
            private_key_pem=private_key_pem, sign=not no_sign, assurance=assurance,
            decision=decision,
        )
    except MissingAttestExtraError as exc:
        _fail(str(exc))
        return

    bundle_path = write_bundle(bundle, out / ATTESTATION_JSON)
    # The human-readable evidence travels with the bundle, under the same decision.
    write_compliance_markdown(report, out / "report.compliance.md", decision)
    pub_path: Path | None = None
    if pub_pem is not None and key is None:
        # Ephemeral key: publish the public half so the bundle stays offline-verifiable.
        pub_path = out / ATTESTATION_PUB
        pub_path.write_bytes(pub_pem)

    render_summary(report, _out)
    # The signed payload's evidence is the ADVERSARIAL headline (`compliance._evidence` reads
    # `adversarial_headline`), so this line must read the same fields. Printing the all-episode
    # rate made the console block and the bundle it had just written disagree by the width of the
    # benign control — and the console figure is the one that gets pasted into tickets.
    rate, succ, att = report.adversarial_headline()
    fpr = benign_control_text(report)
    if att == 0:
        evidence = "adversarial ASR N/A (0 adversarial episodes)"
    else:
        lo, hi = wilson_ci(succ, att)
        evidence = (
            f"adversarial ASR {100.0 * rate:.1f}% ({succ}/{att}) "
            f"[{100.0 * lo:.0f}-{100.0 * hi:.0f}%]"
        )
    _out.print("\n[bold]Attestation[/bold]")
    _out.print(f"  subject   : {report.policy} x {report.suite}")
    _out.print(f"  evidence  : {evidence}, benign FPR {fpr}")
    _out.print(f"  issued_at : {issued_at}   commit: {stamp}")
    if bundle.signed:
        _out.print(f"  signature : ed25519  keyid {bundle.signatures[0].keyid}")
    else:
        _out.print("  signature : [yellow]digest-only (unsigned)[/yellow]")
    _out.print("  clock     : EU Machinery Reg 2023/1230 applies 2027-01-20")
    _out.print(f"\nWrote [cyan]{bundle_path}[/cyan]"
               + (f" and [cyan]{pub_path}[/cyan]" if pub_path is not None else ""))
    if bundle.signed and key is None:
        _err.print("[yellow]note:[/yellow] signed with an ephemeral key (integrity, not identity). "
                   "Pass --key <ed25519.pem> to sign with your organisation key.")
    if report.policy == "stub" or report.suite == "stub":
        _err.print("[yellow]note:[/yellow] stub numbers are properties of the deterministic "
                   "fixture, not a real VLA. Attest a real run for a transfer measurement.")
    verify_hint = f"provael attest --verify {bundle_path}"
    if pub_path is not None:
        verify_hint += f" --pubkey {pub_path}"
    _out.print(f"Verify offline: [bold]{verify_hint}[/bold]")
