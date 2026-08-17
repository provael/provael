"""`leaderboard/README.md` is a Hugging Face Space card, and HF validates it server-side.

WHY THIS EXISTS. The Space sync job silently stopped working for three days. `HF_TOKEN` was added
on 12 August and the deploy still failed twice, because `POST /api/validate-yaml` returns **400**
when `short_description` exceeds **60 characters** — ours was 65. The job failed loudly in Actions
and nothing else noticed, so the Space went stale while the repo looked healthy.

Worse, the two sides then drifted in opposite directions: the card was fixed *on the Space* through
the web editor (down to 58 chars, and Gradio bumped to 6.23.1) while the repo kept the 65-character
string and `sdk_version: 6.16.0`. The repo is the side that syncs, so the next successful deploy
would have pushed the broken description back AND downgraded the SDK — undoing a fix by shipping.

These tests assert the constraints the HF API enforces, locally and offline, so a card that cannot
deploy fails `pytest` instead of failing a workflow nobody reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

CARD = Path(__file__).resolve().parent.parent / "leaderboard" / "README.md"

#: Hugging Face's documented cap. Exceeding it is a 400 from /api/validate-yaml, not a warning.
SHORT_DESCRIPTION_MAX = 60


def _front_matter() -> dict[str, object]:
    text = CARD.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "leaderboard/README.md has no YAML front matter — HF will not treat it as a card"
    loaded = yaml.safe_load(match.group(1))
    assert isinstance(loaded, dict)
    return loaded


def test_short_description_is_within_the_hugging_face_limit() -> None:
    """The exact failure that broke the deploy: 65 characters against a 60-character cap."""
    value = _front_matter().get("short_description")
    assert isinstance(value, str) and value, "short_description is missing or empty"
    assert len(value) <= SHORT_DESCRIPTION_MAX, (
        f"short_description is {len(value)} characters; Hugging Face rejects anything over "
        f"{SHORT_DESCRIPTION_MAX} with a 400 from /api/validate-yaml, which aborts the Space "
        f"deploy in .github/workflows/leaderboard-submission.yml.\n  {value!r}"
    )


def test_the_card_declares_the_fields_the_space_needs_to_boot() -> None:
    """A card missing any of these builds a Space that does not start, which reads as a code bug."""
    front = _front_matter()
    for key in ("title", "sdk", "sdk_version", "app_file", "license"):
        assert front.get(key), f"the Space card is missing {key!r}"
    assert front["sdk"] == "gradio"
    assert front["app_file"] == "app.py"
    assert (CARD.parent / str(front["app_file"])).is_file()


def test_sdk_version_is_a_real_pin_not_a_range() -> None:
    """A floating SDK on a Space is a build that changes without a commit.

    Also guards the direction the drift ran: the repo sat on 6.16.0 while the deployed Space had
    moved to 6.23.1, so a successful sync would have DOWNGRADED Gradio under the running app.
    """
    version = str(_front_matter()["sdk_version"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"sdk_version {version!r} is not an exact three-part pin"
    )


def test_the_card_does_not_claim_figures_the_signed_json_lacks() -> None:
    """Whatever fraction the card quotes must be what `leaderboard.json` actually holds.

    This is the honest direction of the check, and it is easy to get backwards. While the board
    was the single-task n=10 run, a ten-task result already existed at 44/50, and "correcting" the
    card to 88% would have described data the Space did not serve. The board has since been
    re-signed onto the ten-task suite and the card moved with it — which is the supported order:
    re-sign the artifact, then describe it. The assertion reads the JSON rather than a literal, so
    it pins the card to the ARTIFACT and not to the newest number the project happens to have.
    """
    import json

    data = json.loads((CARD.parent / "results" / "leaderboard.json").read_text(encoding="utf-8"))
    successes = sum(int(row["successes"]) for row in data["rows"])
    attempts = sum(int(row["attempts"]) for row in data["rows"])
    text = CARD.read_text(encoding="utf-8")
    assert f"({successes}/{attempts})" in text, (
        f"the card quotes a fraction the signed leaderboard.json does not contain; the JSON sums "
        f"to {successes}/{attempts}. Either re-sign the JSON or leave the card describing it."
    )
