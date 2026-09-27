# CycloneDX 1.6 JSON schema (vendored for tests)

`tests/test_mlbom.py` validates every ML-BOM provael emits against the official CycloneDX 1.6
JSON schema, offline, with the `jsonschema` package the dev group already carries. These three
files are copied unmodified from the CycloneDX specification repository at tag **1.6.2**
(commit `e833d732337dd33aceb45ff1991f896796f1e5e7`), `schema/`:

- `bom-1.6.schema.json` — the BOM schema (draft-07)
- `spdx.schema.json` — SPDX licence identifiers, referenced by the BOM schema
- `jsf-0.82.schema.json` — JSON Signature Format, referenced by the BOM schema

Source: https://github.com/CycloneDX/specification/tree/e833d732337dd33aceb45ff1991f896796f1e5e7/schema — licensed Apache-2.0,
as is this repository. Replace all three together, from one tag, when moving to a new spec version.
