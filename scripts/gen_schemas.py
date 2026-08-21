"""Regenerate the published JSON Schemas from the pydantic models.

Run after ANY change to `RunReport` or `Leaderboard`; `tests/test_published_schemas.py` fails until
you do. Generated rather than hand-written so the published contract cannot describe a model that
has moved — the failure mode a third party would hit first and report last.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael.leaderboard import Leaderboard
from provael.types import RunReport

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "schemas"
BASE = "https://raw.githubusercontent.com/provael/provael/main/schemas"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for model, name, ver in ((RunReport, "report", 4), (Leaderboard, "leaderboard", 5)):
        schema = model.model_json_schema(mode="serialization")
        doc = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{BASE}/{name}.v{ver}.schema.json",
            "title": f"provael {name}.json (schema_version {ver})",
            **schema,
        }
        sv = doc.get("properties", {}).get("schema_version")
        if sv is not None:
            sv["maximum"] = ver
            sv["description"] = (
                (sv.get("description", "") + " ").strip()
                + f" This schema documents version {ver}; it accepts artifacts declaring {ver} or "
                f"lower, because every bump so far has been additive with defaults. It refuses a "
                f"higher version rather than silently validating a format it does not describe."
            )
        path = OUT / f"{name}.v{ver}.schema.json"
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
