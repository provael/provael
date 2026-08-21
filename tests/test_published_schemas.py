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
_REPORT_SCHEMA = _SCHEMAS / "report.v4.schema.json"
_BOARD_SCHEMA = _SCHEMAS / "leaderboard.v5.schema.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _committed_reports() -> list[Path]:
    return sorted((_ROOT / "results").rglob("report.json"))


def _committed_boards() -> list[Path]:
    return sorted((_ROOT / "leaderboard").rglob("leaderboard.json"))


def test_the_schemas_are_themselves_valid_json_schema() -> None:
    """A malformed schema validates nothing and reports success, so check the checker first."""
    for path in (_REPORT_SCHEMA, _BOARD_SCHEMA):
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
    validator = Draft202012Validator(_load(_REPORT_SCHEMA))
    sample = _load(_committed_reports()[0])
    sample["schema_version"] = 5
    assert list(validator.iter_errors(sample)), "the v4 schema accepted a schema_version 5 report"


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
