"""The vulnerability-disclosure address must be one address, and the same one everywhere.

``SECURITY.md`` named a gmail address while the website's ``.well-known/security.txt`` named
``hello@provael.com``. A researcher who found something had two channels and no way to tell which
was monitored — at precisely the moment you want the report to land somewhere rather than be
abandoned. Worse, the two files are read by different audiences: ``security.txt`` is what an
automated scanner fetches, ``SECURITY.md`` is what a human reads on GitHub, so the two populations
were being sent to different inboxes.

WHY THIS IS A MIRROR AND NOT A SHARED CONSTANT. ``security.txt`` lives in the website repo and is
served by Cloudflare; ``SECURITY.md`` lives here. Different repos, different runtimes, no import
path between them — the same situation as the lead contract, which is likewise mirrored with a
drift test on each side rather than packaged. Each side pins the literal and tests its own copy.
Change one, change both; the website's counterpart lives in ``scripts/check-facts.mjs``.

Note this deliberately does NOT assert the address is unique to security. ``hello@provael.com`` also
receives sales and support, which is a real weakness on a site selling security services and is
tracked separately — it is a mailbox-provisioning decision, not something a test can fix.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: The canonical disclosure address. Mirrored in the website's .well-known/security.txt.
SECURITY_CONTACT = "hello@provael.com"

#: Addresses that must never reappear on a disclosure path.
_RETIRED_CONTACTS = ("getprovael@gmail.com",)


def _security_md() -> str:
    return (REPO / "SECURITY.md").read_text(encoding="utf-8")


def test_security_md_names_the_canonical_contact() -> None:
    assert SECURITY_CONTACT in _security_md(), (
        f"SECURITY.md must name {SECURITY_CONTACT} — it is the Contact: line in security.txt"
    )


def test_security_md_names_no_retired_contact() -> None:
    body = _security_md()
    # The HTML comment explaining the change is allowed to mention history; strip comments first.
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    found = [a for a in _RETIRED_CONTACTS if a in body]
    assert not found, f"SECURITY.md still routes disclosure to a retired address: {found}"


def test_exactly_one_email_on_the_disclosure_path() -> None:
    """Two addresses in one policy is the defect, regardless of which two."""
    body = re.sub(r"<!--.*?-->", "", _security_md(), flags=re.S)
    addresses = set(re.findall(r"[\w.%+-]+@[\w.-]+\.\w+", body))
    assert addresses == {SECURITY_CONTACT}, (
        f"SECURITY.md should name exactly one contact address, found: {sorted(addresses)}"
    )
