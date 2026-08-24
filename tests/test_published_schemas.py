"""Every committed artifact validates against the published JSON Schema for its format.

WHY THESE SCHEMAS EXIST. A third party submitting a run had no machine-checkable contract for
`report.json` or `leaderboard.json`. The whole 475-file tree carried three `$schema` keys and none
of them described the two artifacts the project asks outsiders to produce. "Open submission queue"
with zero external rows and no schema is not an open queue; it is an invitation to guess.

WHY THEY ARE GENERATED FROM THE MODELS, NOT WRITTEN FROM THE ARTIFACTS. A schema inferred from
today's files describes today's files. Generated from `RunReport` / `Leaderboard` it describes the
contract, and this test is what keeps the two honest in both directions: the schema must accept
every artifact already committed, and — because it is generated — it cannot describe fields the
models do not have.

REGENERATE with `scripts/gen_schemas.py` after any model change; this test fails until you do.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from provael.leaderboard import Leaderboard
from provael.types import RunReport

_ROOT = Path(__file__).resolve().parent.parent
_SCHEMAS = _ROOT / "schemas"
_REPORT_SCHEMA = _SCHEMAS / "report.v5.schema.json"
_BOARD_SCHEMA = _SCHEMAS / "leaderboard.v6.schema.json"

#: Schemas that a NEWER version has superseded. They stay committed and stay frozen: `$id` is a
#: raw.githubusercontent URL on `main`, so deleting one 404s every consumer that pinned it, and
#: regenerating one would rewrite a contract already published under that name. They are not
#: compared against the current models — describing an older model is what makes them a version —
#: but they must still honour the promise their own `schema_version` bound makes.
#: (superseded schema, the current schema that replaced it, how to find its artifacts).
_SUPERSEDED_SCHEMAS = (
    (_SCHEMAS / "leaderboard.v5.schema.json", "_BOARD_SCHEMA"),
    (_SCHEMAS / "report.v4.schema.json", "_REPORT_SCHEMA"),
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _committed_reports() -> list[Path]:
    return sorted((_ROOT / "results").rglob("report.json"))


def _committed_boards() -> list[Path]:
    return sorted((_ROOT / "leaderboard").rglob("leaderboard.json"))


def test_the_schemas_are_themselves_valid_json_schema() -> None:
    """A malformed schema validates nothing and reports success, so check the checker first."""
    for path in (_REPORT_SCHEMA, _BOARD_SCHEMA, *(p for p, _ in _SUPERSEDED_SCHEMAS)):
        Draft202012Validator.check_schema(_load(path))


@pytest.mark.parametrize("path", _committed_reports(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_every_committed_report_validates(path: Path) -> None:
    """Including the schema-2 and schema-3 artifacts, which predate the current model.

    That is the point of accepting `schema_version <= 4` rather than exactly 4: every bump so far
    has been additive with defaults, so an older artifact is still structurally valid. If a bump is
    ever NOT additive, this test fails on the historical files and that is the correct moment to
    find out — before a consumer does.
    """
    validator = Draft202012Validator(_load(_REPORT_SCHEMA))
    errors = sorted(validator.iter_errors(_load(path)), key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(
        f"  {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors[:8]
    )


@pytest.mark.parametrize("path", _committed_boards(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_every_committed_board_validates(path: Path) -> None:
    validator = Draft202012Validator(_load(_BOARD_SCHEMA))
    errors = sorted(validator.iter_errors(_load(path)), key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(
        f"  {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors[:8]
    )


def test_a_higher_schema_version_is_refused() -> None:
    """The version in the filename must mean something.

    A v4 schema that happily validates a v5 artifact is a schema that cannot tell a consumer their
    tool is too old, which is the one thing a versioned contract is for.
    """
    schema = _load(_REPORT_SCHEMA)
    ceiling = schema["properties"]["schema_version"]["maximum"]
    validator = Draft202012Validator(schema)
    sample = _load(_committed_reports()[0])
    sample["schema_version"] = ceiling + 1
    assert list(validator.iter_errors(sample)), (
        f"the v{ceiling} schema accepted a schema_version {ceiling + 1} report"
    )


def test_the_schemas_match_the_models_they_claim_to_describe() -> None:
    """Regenerating must be a no-op, or the published schema describes a model that moved.

    Only the top-level property NAMES are compared, not the full document: pydantic's emitted
    `$defs` ordering and description text churn on unrelated edits, and a test that fails on churn
    gets regenerated blindly, which defeats it.
    """
    for model, path in ((RunReport, _REPORT_SCHEMA), (Leaderboard, _BOARD_SCHEMA)):
        live = set(model.model_json_schema(mode="serialization").get("properties", {}))
        published = set(_load(path).get("properties", {}))
        assert live == published, (
            f"{path.name} is out of date with {model.__name__}: "
            f"only in model {sorted(live - published)}, only in schema {sorted(published - live)}. "
            f"Regenerate with scripts/gen_schemas.py."
        )


_ARTIFACTS = {"_BOARD_SCHEMA": _committed_boards, "_REPORT_SCHEMA": _committed_reports}
_CURRENT = {"_BOARD_SCHEMA": _BOARD_SCHEMA, "_REPORT_SCHEMA": _REPORT_SCHEMA}


@pytest.mark.parametrize(("schema_path", "kind"), _SUPERSEDED_SCHEMAS, ids=lambda v: getattr(v, "name", v))
def test_a_superseded_schema_still_accepts_the_artifacts_it_promised_to(
    schema_path: Path, kind: str
) -> None:
    """A published contract does not stop being a contract when a newer one appears.

    Every artifact committed at or below a superseded schema's version must still validate against
    it. Otherwise a consumer that pinned that `$id` — which is the correct, conservative thing for
    a consumer to do — starts rejecting artifacts the project still publishes.
    """
    schema = _load(schema_path)
    ceiling = schema["properties"]["schema_version"]["maximum"]
    validator = Draft202012Validator(schema)
    checked = 0
    for path in _ARTIFACTS[kind]():
        artifact = _load(path)
        if artifact.get("schema_version", 1) > ceiling:
            continue
        errors = list(validator.iter_errors(artifact))
        assert not errors, f"{path.name} no longer validates against {schema_path.name}: {errors[0]}"
        checked += 1
    assert checked, f"nothing at or below v{ceiling} remains to check {schema_path.name} against"


@pytest.mark.parametrize(("schema_path", "kind"), _SUPERSEDED_SCHEMAS, ids=lambda v: getattr(v, "name", v))
def test_a_superseded_schema_is_frozen_below_the_current_one(schema_path: Path, kind: str) -> None:
    """A superseded file keeps its own version, and that version is genuinely behind the current.

    `scripts/gen_schemas.py` writes `<name>.v<N>.schema.json` for the CURRENT N only, so a bump
    creates a new file and leaves the old one alone. What this checks is that it stayed alone: the
    filename, the `$id` and the declared `schema_version` ceiling still agree with each other and
    are still below the current contract. Rewriting one in place would be a rewrite of something
    already published at a stable URL, not a routine update — and the model comparison in
    `test_the_schemas_match_the_models_they_claim_to_describe` is deliberately NOT applied to
    these, because describing an older model is exactly what makes them a version.
    """
    schema = _load(schema_path)
    ceiling = schema["properties"]["schema_version"]["maximum"]
    current = _load(_CURRENT[kind])["properties"]["schema_version"]["maximum"]
    assert ceiling < current, f"{schema_path.name} is not superseded by anything"
    assert f".v{ceiling}." in schema_path.name, (
        f"{schema_path.name} declares a ceiling of {ceiling}; the filename and the contract it "
        "documents disagree, so a consumer resolving it by name gets something else."
    )
    assert schema["$id"].endswith(schema_path.name), (
        f"{schema_path.name} carries $id {schema['$id']}, which resolves elsewhere."
    )
