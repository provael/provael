#!/usr/bin/env python3
"""Create the submission-queue dataset the Space opens PRs against. Run once, by a maintainer.

WHY THIS IS A SCRIPT AND NOT A README STEP. The queue was aimed at an org that never existed, from
the day it shipped until it was found two months later, because "create the dataset" lived only in
prose and prose does not fail. A script fails, says what it did, and can be re-run to verify.

It is idempotent: run it again and it reports the dataset already exists rather than erroring, so it
doubles as the check for "is the queue actually open?".

    export HF_TOKEN=hf_...          # needs WRITE scope on the account that owns repo
    python leaderboard/setup_requests_dataset.py

The same token then goes on the Space (Settings -> Variables and secrets -> New secret, name
HF_TOKEN). Without it the submit button reports the queue as disabled, which is honest but shut.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent / "app.py"


def requests_repo() -> str:
    """Read repo out of app.py as TEXT, not by importing it.

    `from app import repo` was the obvious version and it crashed: app.py imports gradio at
    module scope, and gradio is a Space dependency that a maintainer running a one-off setup script
    has no reason to have installed. The script whose whole job is "make the queue work" failed on
    its own first line, which is the failure it exists to prevent.

    Parsing keeps the single-source-of-truth property — there is still exactly one place the repo id
    is written — without dragging in a UI framework to read one string.
    """
    m = re.search(r'^REQUESTS_REPO\s*=\s*["\']([^"\']+)["\']', APP.read_text(), re.M)
    if not m:
        raise SystemExit(f"could not find REQUESTS_REPO in {APP}")
    return m.group(1)

DATASET_CARD = """\
---
license: apache-2.0
tags:
  - provael
  - vla
  - red-teaming
  - leaderboard
---

# Provael leaderboard — submission queue

Incoming results for the [Provael VLA policy ASR leaderboard](https://www.provael.com/leaderboard/).
This dataset is a **queue**, not the board. A maintainer validates each submission and promotes it;
until then a file here is a request, not a published result.

## How a result gets here

Either route works and both end in the same review:

1. The **Submit a result** tab on the
   [Space](https://huggingface.co/spaces/Sattyam/provael-leaderboard) — uploads your JSON and opens
   a pull request against this dataset.
2. A [GitHub issue](https://github.com/provael/provael/issues/new) with the JSON attached. Needs no
   Hugging Face account, and is the route the Space falls back to when this queue is unavailable.

## What a submission must contain

The output of `provael leaderboard build` — which carries the ASR, its 95% Wilson interval, the
benign control, the attempt count, and the transfer status of every row. Validate before sending:

```bash
pip install provael
provael submit --dry-run --in <your-run-dir>
```

That signs and prints exactly what would be submitted, touching no network.

## What gets rejected, so it is not a surprise

- A result with no benign control. The control is what makes an ASR mean anything.
- A row that reports an attack success rate without its denominator.
- A stub-policy run presented as a real-model result. Stub runs are welcome and are labelled as
  stub — the labelling is the requirement, not the policy.

Null results are **wanted**. The published board already carries measured zeros, and a family that
does not transfer is a finding.
"""


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print(
            "HF_TOKEN is not set.\n\n"
            "  export HF_TOKEN=hf_...   # write scope, on the account owning the dataset\n\n"
            "Create one at https://huggingface.co/settings/tokens",
            file=sys.stderr,
        )
        return 2

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("pip install huggingface_hub", file=sys.stderr)
        return 2

    repo = requests_repo()
    api = HfApi(token=token)

    # Wrapped, because an expired or mistyped token is the most likely thing to go wrong here and
    # the unwrapped version dumped a raw HfHubHTTPError traceback. That is the same defect this
    # whole change set fixed in the Space's submit button; shipping it in the setup script would be
    # a poor joke.
    try:
        me = api.whoami()
    except Exception as exc:  # noqa: BLE001 - the message must reach the operator, not a log
        print(
            f"HF_TOKEN was rejected: {exc}\n\n"
            "Check it is a WRITE token and not read-only, and that it has not expired:\n"
            "  https://huggingface.co/settings/tokens",
            file=sys.stderr,
        )
        return 1
    who = me["name"]
    owner = repo.split("/")[0]
    if who != owner and owner not in {o.get("name") for o in me.get("orgs", [])}:
        print(
            f"Token belongs to '{who}', which cannot write to '{repo}'.\n"
            f"Use a token for '{owner}', or change REQUESTS_REPO in leaderboard/app.py.",
            file=sys.stderr,
        )
        return 1

    existed = api.repo_exists(repo_id=repo, repo_type="dataset")
    api.create_repo(repo_id=repo, repo_type="dataset", exist_ok=True, private=False)
    api.upload_file(
        path_or_fileobj=DATASET_CARD.encode(),
        path_in_repo="README.md",
        repo_id=repo,
        repo_type="dataset",
    )

    url = f"https://huggingface.co/datasets/{repo}"
    print(f"{'Verified (already existed)' if existed else 'Created'}: {url}")
    print(
        "\nThe queue is open once the SAME token is set on the Space:\n"
        "  https://huggingface.co/spaces/Sattyam/provael-leaderboard/settings\n"
        "  -> Variables and secrets -> New secret -> name HF_TOKEN\n\n"
        "Then press Submit on the Space with any results JSON. A PR should appear at\n"
        f"  {url}/discussions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
