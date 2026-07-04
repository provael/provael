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
from provael.attest import canonical_json, sha256_hex, sign_bytes, verify_bytes
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
    transfer_status: str = Field(
        STUB_SCAFFOLDING, description="'real-transfer' or 'stub-scaffolding' (see transfer_status)."
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

    schema_version: int = 2
    is_demo: bool = Field(..., description="True when every aggregated run used the stub policy.")
    rows: list[LeaderboardRow] = Field(default_factory=list)
    examples: list[AttackExample] = Field(default_factory=list)
    inputs_digest: str | None = Field(
        None, description="SHA-256 of the canonical aggregated input reports (deterministic)."
    )
    generated_at: str | None = Field(None, description="UTC ISO-8601 build time (…Z), if stamped.")
    commit: str | None = Field(
        None, description="Source commit the board was built from, if stamped."
    )
    signature: LeaderboardSignature | None = None


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
    """
    base_obs = StubSuite().reset("reach", 0)
    examples: list[AttackExample] = []
    for name in attack_names:
        attack = make_attack(name)
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

    Reuses the digest approach from :mod:`provael.attest` so the board and an attestation speak the
    same integrity language.
    """
    canon = sorted(canonical_json(json.loads(r.model_dump_json())) for r in reports)
    return sha256_hex(b"\n".join(canon))


def aggregate(reports: list[RunReport]) -> Leaderboard:
    """Aggregate run reports into a ranked :class:`Leaderboard` (pure, deterministic)."""
    buckets: dict[tuple[str, str, str], list[int]] = {}
    attack_names: set[str] = set()
    for report in reports:
        for result in report.results:
            attack_names.add(result.attack)
            if not result.applicable:  # excluded from the ASR denominator
                continue
            key = (report.policy, report.suite, result.family)
            tally = buckets.setdefault(key, [0, 0])
            tally[0] += 1
            tally[1] += int(result.success)

    # The benign control per (policy, suite): the baseline ('none') family's rate.
    baseline_fpr: dict[tuple[str, str], float] = {}
    for (policy, suite, family), (attempts, successes) in buckets.items():
        if family == "baseline" and attempts:
            baseline_fpr[(policy, suite)] = successes / attempts

    rows = [
        LeaderboardRow(
            policy=policy,
            suite=suite,
            family=family,
            attempts=attempts,
            successes=successes,
            asr=(successes / attempts if attempts else 0.0),
            ci95=wilson_ci(successes, attempts) if attempts else None,
            benign_fpr=baseline_fpr.get((policy, suite)),
            transfer_status=transfer_status(policy, suite),
        )
        for (policy, suite, family), (attempts, successes) in buckets.items()
    ]
    # Rank by ASR (desc), then by keys for a stable, deterministic order.
    rows.sort(key=lambda r: (-r.asr, r.policy, r.suite, r.family))

    is_demo = all(report.policy == "stub" for report in reports) if reports else True
    return Leaderboard(
        is_demo=is_demo,
        rows=rows,
        examples=attack_examples(sorted(attack_names)),
        inputs_digest=_inputs_digest(reports) if reports else None,
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


def _signing_payload(board: Leaderboard) -> bytes:
    """Canonical bytes signed/verified: the whole board minus the ``signature`` field."""
    data = json.loads(board.model_dump_json())
    data.pop("signature", None)
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
    board = aggregate(reports)
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
