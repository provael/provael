"""Aggregate run reports into a ranked ASR leaderboard.

Reads any number of ``report.json`` files, buckets every episode by
``(policy, suite, family)``, and produces a ranked table plus a representative
example payload per attack. Output is deterministic (sorted rows/keys, no wall-clock,
no source paths) so the committed leaderboard JSON is byte-stable.

A leaderboard is flagged ``is_demo`` when every aggregated run used the ``stub``
policy — i.e. there is no real-model number yet. The Gradio Space renders a clear
"demo data" banner in that case.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from pydantic import BaseModel, Field

from provael.attacks.registry import make_attack
from provael.attest import (
    canonical_json,
    report_projection,
    sha256_hex,
    sign_bytes,
    verify_bytes,
)
from provael.calibration import wilson_ci
from provael.policies.stub import ATTACKABLE_OBS_FIELDS
from provael.report import REPORT_JSON, load_report
from provael.scoring.action import ACTION_DIRECTIVE_KEY
from provael.suites.stub import BASE_INSTRUCTION, StubSuite
from provael.types import RunReport

#: Observation channels the example builder inspects for an attack's injected payload
#: (the attackable danger channels plus the EAI04 action-directive channel).
_EXAMPLE_OBS_FIELDS: tuple[str, ...] = (*ATTACKABLE_OBS_FIELDS, ACTION_DIRECTIVE_KEY)

LEADERBOARD_JSON = "leaderboard.json"

#: DSSE payload type for a signed leaderboard.
LEADERBOARD_PAYLOAD_TYPE = "application/vnd.provael.leaderboard+json"

#: Row transfer-status labels (a row is a real transfer only on a real policy AND a real suite).
REAL_TRANSFER = "real-transfer"
STUB_SCAFFOLDING = "stub-scaffolding"

# ── Row provenance: who produced the number, which is a different question from how strong it is ──
# `transfer_status` answers "is this a real-model measurement?"; these answer "whose measurement is
# it?". A board whose every row is the maintainer's own single run is a different artifact from one
# carrying five independent submitters, and until now the JSON could not tell those apart — so the
# rendered board could not either, and neither could a reader deciding how much independence the
# number carries.
#: The maintainer's own run, submitted from this repo.
MAINTAINER_RUN = "maintainer-run"
#: An outside submission, validated and signed through `provael submit`.
THIRD_PARTY_SUBMISSION = "third-party-submission"
#: Provenance was never recorded — every row predating this field. NOT a synonym for maintainer-run:
#: claiming attribution these rows never carried would be inventing provenance, so they stay
#: honestly unattributed until someone re-stamps them with a real one.
UNATTRIBUTED = "unattributed"


def transfer_status(policy: str, suite: str) -> str:
    """Honest label for a row: real-model transfer vs deterministic-stub scaffolding.

    A number only *transfers* when a real policy runs in a real simulator; a real policy on the
    stub suite (or the stub policy anywhere) is scaffolding, not a transfer measurement.
    """
    return REAL_TRANSFER if policy != "stub" and suite != "stub" else STUB_SCAFFOLDING


class LeaderboardRow(BaseModel):
    """One ranked row: ASR for a ``(policy, suite, family)`` slice, with its honesty context."""

    policy: str
    suite: str
    family: str
    attempts: int
    successes: int
    asr: float
    ci95: tuple[float, float] | None = Field(None, description="95% Wilson CI on this row's ASR.")
    benign_fpr: float | None = Field(
        None, description="The benign control: the baseline ('none') ASR for this policy x suite."
    )
    benign_attempts: int | None = Field(
        None,
        description="Benign control episodes behind `benign_fpr`. A board row carries its ASR "
        "with a denominator and an interval and carried the floor it is measured against as a "
        "bare rate; 0/5 and 0/500 both serialise as 0.0, and the difference decides whether the "
        "row says anything. None when no baseline family reached this policy x suite.",
    )
    benign_successes: int | None = Field(
        None, description="Benign control episodes that fired the predicate. None when no "
        "baseline family reached this policy x suite.",
    )
    benign_ci95: tuple[float, float] | None = Field(
        None,
        description="95% Wilson CI on `benign_fpr`, on the same footing as `ci95` is to `asr`. "
        "An ASR is a difference against this floor, so publishing an interval on one term and a "
        "point on the other invites a comparison the data does not support.",
    )
    transfer_status: str = Field(
        STUB_SCAFFOLDING, description="'real-transfer' or 'stub-scaffolding' (see transfer_status)."
    )
    submitted_by: str | None = Field(
        None,
        description="Who submitted this row (a GitHub handle or org), or None when unattributed.",
    )
    provenance: str = Field(
        UNATTRIBUTED,
        description="How this row reached the board: maintainer-run, third-party-submission, or "
        "unattributed (see the module constants).",
    )
    # ── Qualifiers. A rate without these is an overclaim, and the board is the one surface where a
    # number travels furthest from its own report. Every one is DERIVED from the aggregated reports
    # (never passed in), for the same reason `measured_with` is: a qualifier a caller can assert is
    # a qualifier a caller can get wrong.
    calibrated: bool | None = Field(
        None,
        description="True only when EVERY report behind this row ran a calibrated predicate. "
        "False when any did not - an uncalibrated keep-out zone measures divergence out of a "
        "default box, not a hazard rate. None when no report recorded it.",
    )
    stochastic: bool | None = Field(
        None,
        description="True when ANY report behind this row was stochastic, i.e. not reproducible "
        "run-to-run. Deliberately pessimistic: one unseeded sampler makes the row one draw, and a "
        "board that averaged this away would advertise a determinism it does not have.",
    )
    checkpoint: str | None = Field(
        None,
        description="The model/checkpoint measured, when exactly one produced this row. None when "
        "several did - naming one of them would attribute the rate to a checkpoint that did not "
        "wholly earn it.",
    )


class AttackExample(BaseModel):
    """A representative adversarial artifact produced by one attack."""

    attack: str
    family: str
    example: str


class LeaderboardSignature(BaseModel):
    """Ed25519 signature over the board's canonical bytes (signature field excluded)."""

    keyid: str
    alg: str = "ed25519"
    sig: str


class Leaderboard(BaseModel):
    """A ranked, deterministic ASR leaderboard built from run reports.

    The rows/examples/``inputs_digest`` are a pure function of the input reports (byte-stable). The
    provenance envelope (``generated_at``, ``commit``, ``signature``) is stamped only on the signed
    real-run build path, so a plain ``build_leaderboard`` stays deterministic.
    """

    #: 2 -> 3: added ``measured_with``. 3 -> 4: added per-row ``submitted_by`` / ``provenance``,
    #: so independence is legible in the artifact and not only in a maintainer's head. 4 -> 5: added
    #: per-row ``calibrated`` / ``stochastic`` / ``checkpoint`` and board-level ``not_applicable``,
    #: so a row carries the qualifiers its own report always had - the board was the one place they
    #: were dropped, which is precisely where a number is read furthest from its source. 5 -> 6:
    #: added per-row ``benign_successes`` / ``benign_attempts`` / ``benign_ci95``, so the control
    #: arm is published to the same standard as the rate it qualifies. Every bump is additive with
    #: defaults, so an older board still loads - and every added field is registered in
    #: ``_FIELDS_ADDED_IN`` / ``_ROW_FIELDS_ADDED_IN`` or it silently invalidates every signature
    #: ever issued.
    schema_version: int = 6
    is_demo: bool = Field(..., description="True when every aggregated run used the stub policy.")
    rows: list[LeaderboardRow] = Field(default_factory=list)
    examples: list[AttackExample] = Field(default_factory=list)
    inputs_digest: str | None = Field(
        None, description="SHA-256 of the canonical aggregated input reports (deterministic)."
    )
    generated_at: str | None = Field(
        None,
        description="UTC ISO-8601 time the BOARD was assembled (…Z), if stamped. This is not when "
        "the underlying runs were measured — see `measured_with`.",
    )
    commit: str | None = Field(
        None, description="Source commit the board was built from, if stamped."
    )
    measured_with: list[str] = Field(
        default_factory=list,
        description="Sorted, de-duplicated `tool_version` values of the aggregated run reports — "
        "the versions the NUMBERS were actually measured with.",
    )
    not_applicable: list[str] = Field(
        default_factory=list,
        description="Attacks that produced episode records but zero APPLICABLE episodes, sorted. "
        "Not-measured and measured-zero are different claims: scoring excludes these from every "
        "denominator, so without this list they vanish from the board entirely and a reader counts "
        "one fewer null than was actually attempted.",
    )
    signature: LeaderboardSignature | None = None

    def is_restamp(self) -> bool:
        """Whether the board was assembled by a tool version that measured none of its own rows.

        A board is rebuilt from committed ``report.json`` files, so re-running the generator moves
        ``generated_at`` and ``commit`` to today while every row still carries the measurement it
        always did. Without this distinction a freshly-stamped board reads as a fresh measurement,
        which is the one thing a dated, signed record must not do. Returns True when the board's
        own build commit is newer than every version that produced its rows.
        """
        from provael import __version__

        return bool(self.measured_with) and __version__ not in self.measured_with

    def submitters(self) -> list[str]:
        """Distinct attributed submitters, sorted. Empty when every row is unattributed.

        The one-number answer to "how independent is this board?". A board of four rows from one
        run and a board of four rows from four labs look identical in every other field.
        """
        return sorted({r.submitted_by for r in self.rows if r.submitted_by})

    def independent_submitters(self) -> list[str]:
        """Submitters whose rows arrived as third-party submissions (excludes maintainer runs).

        Kept separate from :meth:`submitters` because the maintainer submitting their own run is
        attribution, not independence, and conflating the two would let the board advertise
        external validation it does not have.
        """
        return sorted(
            {
                r.submitted_by
                for r in self.rows
                if r.submitted_by and r.provenance == THIRD_PARTY_SUBMISSION
            }
        )


def find_reports(paths: list[str]) -> list[Path]:
    """Resolve a list of paths/globs into a sorted, de-duplicated list of report.json files.

    Each entry may be a directory (searched recursively for ``report.json``), a glob
    pattern, or a direct path to a ``report.json``.
    """
    found: set[Path] = set()
    for entry in paths:
        if any(char in entry for char in "*?["):
            matches = [Path(m) for m in sorted(glob.glob(entry))]
        else:
            matches = [Path(entry)]
        for match in matches:
            if match.is_dir():
                found.update(match.rglob(REPORT_JSON))
            elif match.name == REPORT_JSON and match.exists():
                found.add(match)
    return sorted(found)


def attack_examples(attack_names: list[str]) -> list[AttackExample]:
    """Build a representative example artifact for each attack (deterministic).

    Re-runs each attack's ``perturb`` on a canonical stub observation and reports the
    changed instruction (instruction family) or the injected observation channel
    (visual / injection families). Policy-agnostic — it describes what the attack does.

    An attack name this build does not register is rendered as an unavailable row rather than
    raised: ``validate_report`` only requires a non-empty attack name, so a submission produced by
    a fork or by a newer Provael than the one rebuilding the board carries names the registry
    cannot resolve. Failing there would take down the whole board over one unknown row.
    """
    base_obs = StubSuite().reset("reach", 0)
    examples: list[AttackExample] = []
    for name in attack_names:
        try:
            attack = make_attack(name)
        except KeyError:
            examples.append(AttackExample(
                attack=name,
                family="unknown",
                example="unavailable: attack not registered in this build",
            ))
            continue
        adv_instruction, adv_obs = attack.perturb(BASE_INSTRUCTION, base_obs)
        if adv_instruction != BASE_INSTRUCTION:
            artifact = adv_instruction
        else:
            changed = [
                f"{key}={adv_obs.get(key)!r}"
                for key in _EXAMPLE_OBS_FIELDS
                if adv_obs.get(key) != base_obs.get(key)
            ]
            artifact = "; ".join(changed)
        examples.append(AttackExample(attack=name, family=attack.family, example=artifact))
    return sorted(examples, key=lambda e: (e.family, e.attack))


def _inputs_digest(reports: list[RunReport]) -> str:
    """SHA-256 over the canonical, order-independent set of input reports (deterministic).

    Reuses the digest approach from :mod:`provael.attest` — including, since 0.36.1, its
    SCHEMA-AWARE projection, which this docstring claimed and the body did not do.

    THE BUG THIS FIXES, because it is subtle and shipped twice. The old body re-serialised every
    input report through whatever ``RunReport`` the RUNNING version defines, so adding an optional
    field rewrote the bytes of reports that predate it: a schema-2 report loaded by a schema-4 tool
    dumps ``"trajectory": null, "weight_corruption": null`` on every result. The digest of an
    unchanged, committed artifact therefore moved with the tool version.

    Measured against the board committed at 983c829: 0.33.2 and 0.34.0 reproduce ``69396ef8…``;
    0.35.0 (which added ``trajectory``) yields ``46008680…``; 0.36.0 (which added
    ``weight_corruption``) yields ``5d63664f…``. Three answers for one unchanged input — and
    /verification tells strangers to rebuild the board and expect a match.

    :func:`provael.attest.report_projection` already solves this for attestations by stripping
    fields added after a report's DECLARED ``schema_version``. Using it here is what the docstring
    always promised, and it is why an old board verifies again rather than being re-signed to match
    a newer tool.
    """
    canon = sorted(canonical_json(report_projection(r)) for r in reports)
    return sha256_hex(b"\n".join(canon))


def aggregate(
    reports: list[RunReport],
    *,
    submitted_by: str | None = None,
    provenance: str = UNATTRIBUTED,
) -> Leaderboard:
    """Aggregate run reports into a ranked :class:`Leaderboard` (pure, deterministic).

    ``submitted_by`` / ``provenance`` attribute every produced row. They are properties of the
    SUBMISSION, not of the run — a report records what was measured, never who forwarded it — so
    they are passed in by the caller (``provael submit`` sets them; a bare ``build_leaderboard``
    leaves rows honestly unattributed) rather than read out of the report, which would be
    inventing provenance the artifact never carried.
    """
    buckets: dict[tuple[str, str, str], list[int]] = {}
    attack_names: set[str] = set()
    #: Attacks with at least one applicable episode anywhere. Anything in `attack_names` but not
    #: here was attempted and never measured — see `Leaderboard.not_applicable`.
    applicable_attacks: set[str] = set()
    #: Qualifiers, collected per (policy, suite) because that is the granularity a row's rate is
    #: measured at. Values accumulate rather than overwrite: the reduction happens once, below.
    qualifiers: dict[tuple[str, str], dict[str, set[object]]] = {}
    for report in reports:
        run = qualifiers.setdefault(
            (report.policy, report.suite),
            {"calibrated": set(), "stochastic": set(), "model": set()},
        )
        run["calibrated"].add(report.calibrated)
        run["stochastic"].add(report.stochastic)
        if report.model:
            run["model"].add(report.model)
        for result in report.results:
            attack_names.add(result.attack)
            if not result.applicable:  # excluded from the ASR denominator
                continue
            applicable_attacks.add(result.attack)
            key = (report.policy, report.suite, result.family)
            tally = buckets.setdefault(key, [0, 0])
            tally[0] += 1
            tally[1] += int(result.success)

    # The benign control per (policy, suite): the baseline ('none') family's counts AND rate.
    # Counts, not just the rate — they are what lets the row carry an interval, and they come
    # from the same bucket the rate does so the two cannot disagree.
    baseline_arm: dict[tuple[str, str], tuple[int, int]] = {}
    for (policy, suite, family), (attempts, successes) in buckets.items():
        if family == "baseline" and attempts:
            baseline_arm[(policy, suite)] = (successes, attempts)

    def _qualifiers(policy: str, suite: str) -> tuple[bool | None, bool | None, str | None]:
        """Reduce a (policy, suite) bucket's collected qualifiers, each in its honest direction.

        ``calibrated`` is an ALL (one uncalibrated run makes the row uncalibrated), ``stochastic``
        is an ANY (one unseeded sampler makes the row one draw), and ``checkpoint`` resolves only
        when the bucket is unanimous. Every one of those collapses toward the weaker claim on
        purpose: the reduction is the place an aggregate is most tempted to launder a qualifier.
        """
        run = qualifiers.get((policy, suite))
        if run is None:  # pragma: no cover - a bucket always has its report
            return None, None, None
        calib = {c for c in run["calibrated"] if c is not None}
        stoch = {s for s in run["stochastic"] if s is not None}
        models = run["model"]
        return (
            all(bool(c) for c in calib) if calib else None,
            any(bool(s) for s in stoch) if stoch else None,
            str(next(iter(models))) if len(models) == 1 else None,
        )

    rows = []
    for (policy, suite, family), (attempts, successes) in buckets.items():
        calibrated, stochastic, checkpoint = _qualifiers(policy, suite)
        b_succ, b_att = baseline_arm.get((policy, suite), (0, 0))
        has_benign = (policy, suite) in baseline_arm
        rows.append(
            LeaderboardRow(
                policy=policy,
                suite=suite,
                family=family,
                attempts=attempts,
                successes=successes,
                asr=(successes / attempts if attempts else 0.0),
                ci95=wilson_ci(successes, attempts) if attempts else None,
                benign_fpr=(b_succ / b_att) if has_benign else None,
                benign_successes=b_succ if has_benign else None,
                benign_attempts=b_att if has_benign else None,
                benign_ci95=wilson_ci(b_succ, b_att) if has_benign else None,
                transfer_status=transfer_status(policy, suite),
                submitted_by=submitted_by,
                provenance=provenance,
                calibrated=calibrated,
                stochastic=stochastic,
                checkpoint=checkpoint,
            )
        )
    # Rank by ASR (desc), then by keys for a stable, deterministic order.
    rows.sort(key=lambda r: (-r.asr, r.policy, r.suite, r.family))

    is_demo = all(report.policy == "stub" for report in reports) if reports else True
    return Leaderboard(
        is_demo=is_demo,
        rows=rows,
        examples=attack_examples(sorted(attack_names)),
        inputs_digest=_inputs_digest(reports) if reports else None,
        # The versions the NUMBERS came from, not the version assembling the board.
        measured_with=sorted({r.tool_version for r in reports}),
        not_applicable=sorted(attack_names - applicable_attacks),
    )


def validate_report(report: RunReport) -> list[str]:
    """Return a list of problems with a submitted run report (empty list == valid).

    Used by ``scripts/validate_submission.py`` (and CI) to gate leaderboard submissions:
    checks required fields, that the aggregate ASR/success counts are internally consistent
    with the per-episode results, and that the not-applicable accounting matches.
    """
    errors: list[str] = []
    if not report.policy:
        errors.append("missing 'policy'")
    if not report.suite:
        errors.append("missing 'suite'")
    if not report.results:
        errors.append("'results' is empty — nothing to score")
        return errors  # nothing else is meaningful without results
    if not 0.0 <= report.asr <= 1.0:
        errors.append(f"asr {report.asr} is outside [0, 1]")
    if not 0 <= report.successes <= report.attempts:
        errors.append(f"successes {report.successes} not in [0, attempts={report.attempts}]")
    applicable = sum(1 for r in report.results if r.applicable)
    if report.attempts != applicable:
        errors.append(f"attempts ({report.attempts}) != applicable results ({applicable})")
    applicable_successes = sum(1 for r in report.results if r.applicable and r.success)
    if report.successes != applicable_successes:
        errors.append(
            f"successes ({report.successes}) != applicable successes in results "
            f"({applicable_successes})"
        )
    for i, r in enumerate(report.results):
        if not r.attack:
            errors.append(f"results[{i}] missing 'attack'")
        if not r.family:
            errors.append(f"results[{i}] missing 'family'")
    return errors


def to_json(leaderboard: Leaderboard) -> str:
    """Serialise a leaderboard to a stable, indented JSON string (sorted keys)."""
    data = json.loads(leaderboard.model_dump_json())
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def load_leaderboard(path: Path) -> Leaderboard:
    """Load a :class:`Leaderboard` from a JSON file."""
    return Leaderboard.model_validate_json(path.read_text(encoding="utf-8"))


#: Fields introduced by each schema version, so a board is signed over the bytes IT declares rather
#: than over whatever the current model happens to emit. Without this, adding any field with a
#: default silently invalidates every signature ever issued: `model_dump_json` would emit the new
#: key with its default, the canonical bytes would change, and a correctly-signed older board would
#: verify as INVALID — indistinguishable, to the person checking it, from a tampered one. That is
#: the worst possible failure for a signed artifact, and it is a one-line mistake to make.
_FIELDS_ADDED_IN: dict[int, tuple[str, ...]] = {
    5: ("not_applicable",),
}
_ROW_FIELDS_ADDED_IN: dict[int, tuple[str, ...]] = {
    5: ("calibrated", "stochastic", "checkpoint"),
    6: ("benign_successes", "benign_attempts", "benign_ci95"),
}


def _signing_payload(board: Leaderboard) -> bytes:
    """Canonical bytes signed/verified: the board at its OWN schema version, minus ``signature``.

    Fields added after ``board.schema_version`` are stripped before canonicalisation, so a v4 board
    keeps verifying against a v4 signature under a v5 model. Newer boards carry the new fields and
    sign over them.
    """
    data = json.loads(board.model_dump_json())
    data.pop("signature", None)
    for version, names in _FIELDS_ADDED_IN.items():
        if board.schema_version < version:
            for name in names:
                data.pop(name, None)
    for version, names in _ROW_FIELDS_ADDED_IN.items():
        if board.schema_version < version:
            for row in data.get("rows", []):
                for name in names:
                    row.pop(name, None)
    return canonical_json(data)


def stamp_provenance(board: Leaderboard, *, generated_at: str, commit: str) -> Leaderboard:
    """Return a copy stamped with a UTC build time and source commit (injected by the caller)."""
    return board.model_copy(update={"generated_at": generated_at, "commit": commit})


def sign_leaderboard(board: Leaderboard, private_key_pem: bytes) -> Leaderboard:
    """Return a copy signed with Ed25519 (needs the ``attest`` extra). Sign after stamping."""
    keyid, sig = sign_bytes(private_key_pem, LEADERBOARD_PAYLOAD_TYPE, _signing_payload(board))
    return board.model_copy(update={"signature": LeaderboardSignature(keyid=keyid, sig=sig)})


def verify_leaderboard(board: Leaderboard, public_key_pem_bytes: bytes) -> bool:
    """Verify a signed board offline. False when unsigned or the signature does not check out."""
    if board.signature is None:
        return False
    return verify_bytes(
        public_key_pem_bytes, LEADERBOARD_PAYLOAD_TYPE, _signing_payload(board), board.signature.sig
    )


def build_leaderboard(
    run_paths: list[str],
    out_dir: Path,
    *,
    generated_at: str | None = None,
    commit: str | None = None,
    sign_key: bytes | None = None,
    require_real: bool = False,
    submitted_by: str | None = None,
    provenance: str = UNATTRIBUTED,
) -> tuple[Path, Leaderboard]:
    """Find reports under ``run_paths``, aggregate, and write ``<out_dir>/leaderboard.json``.

    With no keyword args the board is the deterministic (demo-or-real) aggregation. Pass
    ``generated_at`` + ``commit`` to stamp provenance and ``sign_key`` to Ed25519-sign it;
    ``require_real=True`` rejects a stub-only input (for the public real board).

    Raises:
        FileNotFoundError: if no ``report.json`` files are found.
        ValueError: if ``require_real`` and every input run used the stub policy.
    """
    report_paths = find_reports(run_paths)
    if not report_paths:
        raise FileNotFoundError(f"no {REPORT_JSON} files found under: {', '.join(run_paths)}")
    reports = [load_report(p) for p in report_paths]
    board = aggregate(reports, submitted_by=submitted_by, provenance=provenance)
    if require_real and board.is_demo:
        raise ValueError(
            "no real (non-stub) runs found — the public board needs a real-model run; "
            "use the plain build for the stub demo"
        )
    if generated_at is not None and commit is not None:
        board = stamp_provenance(board, generated_at=generated_at, commit=commit)
    if sign_key is not None:
        board = sign_leaderboard(board, sign_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / LEADERBOARD_JSON
    out_path.write_text(to_json(board), encoding="utf-8")
    return out_path, board


__all__ = [
    "LEADERBOARD_JSON",
    "LEADERBOARD_PAYLOAD_TYPE",
    "REAL_TRANSFER",
    "STUB_SCAFFOLDING",
    "MAINTAINER_RUN",
    "THIRD_PARTY_SUBMISSION",
    "UNATTRIBUTED",
    "transfer_status",
    "LeaderboardRow",
    "AttackExample",
    "LeaderboardSignature",
    "Leaderboard",
    "find_reports",
    "attack_examples",
    "aggregate",
    "to_json",
    "load_leaderboard",
    "stamp_provenance",
    "sign_leaderboard",
    "verify_leaderboard",
    "build_leaderboard",
    "validate_report",
]
