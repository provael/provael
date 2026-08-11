"""The ATLAS submission artifact must stay well-formed, and must not drift from what was sent.

WHY THIS EXISTS. `docs/standards/atlas-submission-2026-08-08.yaml` was emailed to `atlas@mitre.org` on
8 August 2026, and `docs/standards/index.md` states that "the exact file submitted is committed" so the
submission is reproducible. That promise is only worth something if something enforces it: a later edit
to the committed file would silently make the repository's record of what was sent untrue, and the
person who noticed would be a MITRE reviewer comparing the email to the repo.

So these tests pin the SHAPE and the load-bearing content, and deliberately do not pin every string —
a test that fails on a typo fix teaches people to edit the test.

They also check the file against the ATLAS v6 object model's ID conventions, which is the validation
the submission needed before it could ever become a pull request against `mitre-atlas/atlas-data`
rather than an email. Offline: the corpus itself is not fetched here (CI has no network), so the
conventions are asserted as literals with the fetch recorded in `docs/standards/index.md`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

SUBMISSION = Path(__file__).resolve().parent.parent / "docs" / "standards" / "atlas-submission-2026-08-08.yaml"
INDEX = Path(__file__).resolve().parent.parent / "docs" / "standards" / "index.md"

#: `AML.T####` and `AML.T####.###` — the technique and sub-technique forms in ATLAS v6. Verified
#: against collection 2026.07: 178 techniques, of which 77 carry the two-dot sub-technique form.
ATLAS_TECHNIQUE_ID = re.compile(r"^AML\.T\d{4}(\.\d{3})?$")
ATLAS_CASE_STUDY_ID = re.compile(r"^AML\.CS\d{4}$")


@pytest.fixture(scope="module")
def submission() -> dict[str, Any]:
    return yaml.safe_load(SUBMISSION.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_submission_parses(submission: dict[str, Any]) -> None:
    assert isinstance(submission, dict)
    assert set(submission) >= {"atlas_version_checked", "submitter", "techniques", "case_studies"}


def test_it_names_the_collection_version_it_was_checked_against(submission: dict[str, Any]) -> None:
    """A submission that does not say which corpus it was checked against cannot be re-checked.

    This is also the field that caught a real error: the argument was first built against
    `dist/ATLAS.yaml`, which still self-reports 5.6.0 with 170 techniques and 57 case studies. The
    current release is 2026.07 with 178 and 68. Citing the smaller legacy distribution at a reviewer
    would have understated their own corpus.
    """
    assert submission["atlas_version_checked"] == "2026.07"


def test_no_atlas_id_is_invented(submission: dict[str, Any]) -> None:
    """Assigning an `AML.T` id is MITRE's to do.

    A submission that arrives with an id already chosen is asking the maintainers to ratify a decision
    they own. `proposed_id: null` is the correct state, and this test keeps it that way — while still
    asserting that IF an id is ever filled in (after MITRE assigns one), it matches their form.
    """
    for technique in submission["techniques"]:
        proposed = technique.get("proposed_id")
        if proposed is None:
            continue
        assert ATLAS_TECHNIQUE_ID.match(proposed), (
            f"{proposed!r} is not an ATLAS technique id; expected AML.T#### or AML.T####.###"
        )

    for case_study in submission["case_studies"]:
        proposed = case_study.get("proposed_id")
        if proposed is not None:
            assert ATLAS_CASE_STUDY_ID.match(proposed)


def test_the_case_study_is_typed_exercise_not_incident(submission: dict[str, Any]) -> None:
    """The single most important honesty property of the whole submission.

    No fielded system was attacked and no robot moved. ATLAS's own schema admits `exercise` for
    red-team work, and typing this `incident` would claim a real-world event that did not happen —
    in a corpus whose value to defenders rests on that distinction holding.
    """
    for case_study in submission["case_studies"]:
        assert case_study["type"] == "exercise"


def test_the_case_study_carries_its_scope_limits(submission: dict[str, Any]) -> None:
    """Simulation-only, one policy, uncalibrated. A case study without them overstates the evidence."""
    for case_study in submission["case_studies"]:
        raw = case_study.get("honest_scope_limits", "")
        # The field is prose in this submission, but a list is the natural shape for a schema. Accept
        # both rather than pinning one — the property under test is that the limits are STATED.
        limits = raw if isinstance(raw, str) else " ".join(str(x) for x in raw)
        assert limits, "case study has no honest_scope_limits"
        assert "simulation" in limits.lower()


def test_the_technique_argues_the_impact_surface_gap(submission: dict[str, Any]) -> None:
    """The whole argument for the technique existing, in one sentence.

    VERIFIED against ATLAS collection 2026.07 (fetched 12 August 2026): the Impact tactic AML.TA0011
    has 19 techniques and sub-techniques, and every one of them lands on an informational or economic
    surface — Evade AI Model, Denial of AI Service, Erode AI Model Integrity, Cost Harvesting (+3),
    Spamming with Chaff Data, External Harms (Financial / Reputational / Societal / User Harm, AI IP
    Theft), Erode Dataset Integrity, Data Destruction via AI Agent Tool Invocation, and Machine
    Compromise (+2). `User Harm` is defined as "financial and reputational"; `Societal Harm` as
    reaching "the general public". **None names an actuator, a trajectory, or physical motion as the
    impact surface**, which is precisely the gap this technique proposes to fill.
    """
    blob = " ".join(str(v) for t in submission["techniques"] for v in t.values()).lower()
    assert "actuator" in blob, "the physical-actuation framing is the argument; it must be present"
    assert "action sequence" in blob or "trajectory" in blob


def test_the_index_records_the_disposition() -> None:
    """A submission artifact in the repo whose disposition is unrecorded is the failure mode here.

    Three states are distinguishable and the page must name which one holds: prepared, sent, answered.
    """
    text = INDEX.read_text(encoding="utf-8")
    assert "atlas-submission-2026-08-08.yaml" in text
    assert "atlas@mitre.org" in text
    assert re.search(r"\bSENT\b|\bSent\b", text), "the index must state whether it was sent"
