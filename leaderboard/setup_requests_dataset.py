#!/usr/bin/env python3
"""Create the submission-queue dataset the Space opens PRs against. Run once, by a maintainer.

WHY THIS IS A SCRIPT AND NOT A README STEP. The queue was aimed at an org that never existed, from
the day it shipped until it was found two months later, because "create the dataset" lived only in
prose and prose does not fail. A script fails, says what it did, and can be re-run to verify.

It is idempotent: run it again and it reports the dataset already exists rather than erroring, so it
doubles as the check for "is the queue actually open?".

    export HF_TOKEN=hf_...          # needs WRITE scope on the account that owns REQUESTS_REPO
    python leaderboard/setup_requests_dataset.py

The same token then goes on the Space (Settings -> Variables and secrets -> New secret, name
HF_TOKEN). Without it the submit button reports the queue as disabled, which is honest but shut.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Read the target from app.py rather than restating it. Two copies of a repo id is how the first one
# went stale, and this script exists because of that exact class of drift.
sys.path.insert(0, str(Path(__file__).resolve().parent))

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

    from app import REQUESTS_REPO  # noqa: PLC0415 - read the single source of truth

    api = HfApi(token=token)
    who = api.whoami()["name"]
    owner = REQUESTS_REPO.split("/")[0]
    if who != owner and owner not in {o["name"] for o in api.whoami().get("orgs", [])}:
        print(
            f"Token belongs to '{who}', which cannot write to '{REQUESTS_REPO}'.\n"
            f"Use a token for '{owner}', or change REQUESTS_REPO in leaderboard/app.py.",
            file=sys.stderr,
        )
        return 1

    existed = api.repo_exists(repo_id=REQUESTS_REPO, repo_type="dataset")
    api.create_repo(repo_id=REQUESTS_REPO, repo_type="dataset", exist_ok=True, private=False)
    api.upload_file(
        path_or_fileobj=DATASET_CARD.encode(),
        path_in_repo="README.md",
        repo_id=REQUESTS_REPO,
        repo_type="dataset",
    )

    url = f"https://huggingface.co/datasets/{REQUESTS_REPO}"
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
