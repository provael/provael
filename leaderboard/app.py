"""Provael ASR leaderboard — Hugging Face Space (Gradio).

Renders the committed ``results/*.json`` (from ``provael leaderboard build``) as a ranked table
with a RoboArena-style **all-policies vs. open-source-policies** split, example attacked payloads,
and an **open-submission** tab that opens a PR to a requests dataset for review
(Open-LLM-Leaderboard pattern). No GPU is used to *view*; submissions are validated offline by a
maintainer before promotion.

Both the Hub client and ZeroGPU are imported lazily/guarded so this app also runs locally with
``python app.py`` (submission is disabled without ``HF_TOKEN``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import gradio as gr

try:  # Available on Hugging Face ZeroGPU Spaces; absent locally.
    import spaces  # noqa: F401  (kept for a future @spaces.GPU live-run button)
except ImportError:  # pragma: no cover - environment dependent
    spaces = None  # type: ignore[assignment]

RESULTS_DIR = Path(__file__).parent / "results"

#: The requests dataset a submission opens a PR against (Open-LLM-Leaderboard pattern).
#:
#: This used to point at `provael-submissions/requests`, an ORG THAT WAS NEVER CREATED — verified
#: 2026-08-08: org page 404, datasets API 401, `?author=provael-submissions` returns `[]`. The
#: submit button had been aimed at nothing since it shipped.
#:
#: It now points under the same account that owns the Space, so the token the Space already needs
#: covers it and there is no org to administer. A separate org is the Open-LLM-Leaderboard shape and
#: is worth revisiting if submissions ever reach a volume that justifies it; at zero third-party
#: submissions in the leaderboard's lifetime, an org was infrastructure standing between a stranger
#: and a contribution.
#:
#: It still may not exist — `scripts/setup_requests_dataset.py` creates it — and the code below
#: treats that as a state to report rather than a crash. See GUARANTEED_ROUTE.
REQUESTS_REPO = "Sattyam/provael-leaderboard-requests"

#: Where a submitter is sent when the queue is unavailable. A GitHub issue on the product repo needs
#: no HF org, no token and no dataset to exist — it is the route that cannot break. Same discipline
#: as the website's lead-sink chain: never report a capture that did not happen, and always leave a
#: working path rather than an apology.
GUARANTEED_ROUTE = "https://github.com/provael/provael/issues/new"

#: Adversarial families in the `provael` registry (excluding the benign `baseline` control) — the
#: denominator of the coverage line below.
#:
#: Hardcoded because this Space deliberately installs **no** `provael` (see requirements.txt:
#: viewing renders committed JSON and needs no package), so it cannot import the registry to count
#: them. A hardcoded count is a claim, and claims here drift: the repo shipped a release with three
#: documents still saying "fourteen" after this number became 15. `tests/test_counted_claims.py`
#: therefore checks this constant against the live registry and fails the build if they disagree.
TOTAL_ADVERSARIAL_FAMILIES = 16

#: The release this Space was published from — the "you are here" against which `measured_with`
#: reads as stale. Checked against `provael.__version__` by `tests/test_counted_claims.py` for the
#: same reason as above: an unguarded version string in an uninstalled Space rots invisibly.
CURRENT_RELEASE = "0.37.0"

#: Policies considered open-source (weights available) — drives the RoboArena-style split.
OPEN_SOURCE_POLICIES = frozenset(
    {"stub", "smolvla", "pi0", "pi05", "pi0fast", "groot", "openvla"}
)

ROW_HEADERS = [
    "rank", "policy", "suite", "family", "ASR (95% CI)", "benign", "n", "transfer",
    "submitted by", "provenance",
]
EXAMPLE_HEADERS = ["family", "attack", "example adversarial payload"]


def _load_results() -> tuple[list[dict], list[dict], bool, list[dict]]:
    """Load and merge every results JSON file. Returns (rows, examples, is_demo, provenance)."""
    rows: list[dict] = []
    examples: dict[str, dict] = {}
    provenance: list[dict] = []
    real_seen = False
    for path in sorted(RESULTS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(data.get("rows", []))
        for example in data.get("examples", []):
            examples.setdefault(example["attack"], example)
        if not data.get("is_demo", True):
            real_seen = True
        if data.get("generated_at") or data.get("inputs_digest"):
            provenance.append({
                "file": path.name,
                "generated_at": data.get("generated_at"),
                "commit": data.get("commit"),
                "inputs_digest": data.get("inputs_digest"),
                "measured_with": data.get("measured_with") or [],
                "signed": data.get("signature") is not None,
            })
    rows.sort(key=lambda r: (-r["asr"], r["policy"], r["suite"], r["family"]))
    ordered_examples = sorted(examples.values(), key=lambda e: (e["family"], e["attack"]))
    return rows, ordered_examples, not real_seen, provenance


def _coverage_banner(rows: list[dict], provenance: list[dict]) -> str:
    """State what this board measured, with what, and — the part that rots silently — how long ago.

    A board is rebuilt by re-aggregating committed report files, so `generated_at` moves to today
    while the numbers stay exactly as old as they were. Schema v3 records `measured_with` for that
    reason, but it lived only inside the JSON: the rendered page showed a fresh build date over
    numbers measured 28 releases earlier, and a signature underneath. A signature over stale data
    is worse than no signature, because it reads as currency.

    Everything here is computed from the loaded board rather than written into prose, so the
    statement cannot drift from the rows it describes. The one exception is
    :data:`TOTAL_ADVERSARIAL_FAMILIES`, which the repo's test suite pins to the live registry.
    """
    measured_with = sorted({v for p in provenance for v in p["measured_with"]})
    policies = sorted({r["policy"] for r in rows})
    suites = sorted({r["suite"] for r in rows})
    # The benign control is not an adversarial family; counting it as coverage would inflate the
    # numerator with the one arm that is definitionally not an attack.
    covered = sorted({r["family"] for r in rows if r["family"] != "baseline"})
    missing = TOTAL_ADVERSARIAL_FAMILIES - len(covered)

    if not measured_with:
        return ""
    stale = CURRENT_RELEASE not in measured_with
    versions = ", ".join(f"`{v}`" for v in measured_with)
    lines = [
        f"> {'⚠️ **Stale measurement.**' if stale else '**Measurement provenance.**'} "
        f"The rows below were measured with **provael {versions}**"
        + (f", not the current release (`{CURRENT_RELEASE}`). " if stale else ". ")
        + "Rebuilding a board re-stamps its date and commit but **never re-runs a policy**, so "
        "the build stamp below is newer than the numbers.",
        "",
        f"> **Coverage.** {len(policies)} policy ({', '.join(policies)}) on "
        f"{len(suites)} suite ({', '.join(suites)}); **{len(covered)} of "
        f"{TOTAL_ADVERSARIAL_FAMILIES} adversarial families** measured "
        f"({', '.join(covered)}). **{missing} families have no real-model measurement at all** — "
        "they are absent from this board, which is not the same as scoring 0%.",
        "",
        "> **No clean-task-success control.** The underlying SmolVLA × LIBERO run predates the "
        "competence control, so `clean_task_success_rate` is unrecorded: these rates are read "
        "against a 0% benign false-positive control, but not against a measured demonstration "
        "that the policy completes its benign task unattacked. Not back-filled.",
        "",
        _independence_line(rows),
    ]
    return "\n".join(lines)


def _independence_line(rows: list[dict]) -> str:
    """Who produced these numbers — the question a column of repeated names answers too quietly.

    A board of four rows from one maintainer run and a board of four rows from four independent
    labs are identical in every other field on this page. Stating the count means the page cannot
    imply external validation it does not have, and it makes a real third-party submission
    visible the day it lands.
    """
    submitters = sorted({str(r["submitted_by"]) for r in rows if r.get("submitted_by")})
    independent = sorted(
        {
            str(r["submitted_by"])
            for r in rows
            if r.get("submitted_by") and r.get("provenance") == "third-party-submission"
        }
    )
    if not submitters:
        return (
            "> **Independence.** No submitter is recorded on these rows — they predate submitter "
            "attribution. Read them as unattributed, not as independently reproduced."
        )
    if not independent:
        return (
            f"> ⚠️ **Independence: none.** All {len(rows)} rows were submitted by "
            f"**{', '.join(str(s) for s in submitters)}** (the maintainer). Nobody outside the "
            "project has yet reproduced or submitted a result. Submit one with `provael submit`."
        )
    return (
        f"> **Independence.** {len(submitters)} submitter(s); **{len(independent)} independent** "
        f"({', '.join(str(s) for s in independent)}) — rows submitted from outside the project."
    )


def _ci(row: dict) -> str:
    ci = row.get("ci95")
    if not ci:
        return ""
    return f" [{100.0 * ci[0]:.0f}-{100.0 * ci[1]:.0f}%]"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100.0 * x:.1f}%"


def _provenance_label(row: dict) -> str:
    """Provenance, rendered per row rather than left in the JSON.

    The field has always been recorded and never displayed, which is the worst of both: a reader
    cannot tell a self-reported row from an externally submitted one, and the board looks like a
    leaderboard while being a changelog of our own runs. The summary line above the table states the
    count; this states it per row, so a single third-party entry is visible in place rather than
    only in an aggregate.

    Unknown values are passed through rather than mapped to a default. A provenance this code does
    not recognise is not evidence of anything, and quietly labelling it "maintainer-run" would be a
    guess in the direction that flatters the board.
    """
    provenance = row.get("provenance")
    if not provenance:
        return "unrecorded"
    return {
        "maintainer-run": "maintainer-run (self-reported)",
        "third-party-submission": "third-party ✔",
    }.get(str(provenance), str(provenance))


def _row_table(rows: list[dict]) -> list[list[str]]:
    return [
        [
            str(rank), r["policy"], r["suite"], r["family"],
            f"{100.0 * r['asr']:.1f}%{_ci(r)}", _pct(r.get("benign_fpr")),
            f"{r['successes']}/{r['attempts']}",
            "real" if r.get("transfer_status") == "real-transfer" else "stub",
            r.get("submitted_by") or "unattributed",
            _provenance_label(r),
        ]
        for rank, r in enumerate(rows, start=1)
    ]


def _example_table(examples: list[dict]) -> list[list[str]]:
    return [[e["family"], e["attack"], e["example"]] for e in examples]


def submit_result(model_id: str, results_file: str | None) -> str:
    """Open a PR to the requests dataset with a submitted results JSON (queued for review)."""
    if not model_id or results_file is None:
        return "Provide a model id and a `provael` results JSON file."
    try:
        from huggingface_hub import HfApi
    except ImportError:  # pragma: no cover - environment dependent
        return "huggingface_hub not available — run on the Space (or pip install huggingface_hub)."
    token = os.environ.get("HF_TOKEN")
    if not token:
        return (
            "Submission queue disabled locally: set HF_TOKEN on the Space. Submitting opens a PR "
            f"to `{REQUESTS_REPO}` for a maintainer to validate and promote."
        )
    api = HfApi(token=token)  # pragma: no cover - requires a live token
    # "Submitted" is only ever returned when the API call actually succeeded AND handed back a PR
    # URL to prove it. The previous version returned that string unconditionally after an unguarded
    # upload_file into a repo that does not exist — so the outcome was either a raw traceback or, if
    # the call had ever silently succeeded, a false success on the project's only external-
    # contribution funnel. A submitter told "Submitted" when nothing was captured is the exact
    # failure the website's lead-sink chain was rebuilt twice to eliminate.
    try:
        info = api.upload_file(
            path_or_fileobj=results_file,
            path_in_repo=f"requests/{model_id.replace('/', '__')}.json",
            repo_id=REQUESTS_REPO,
            repo_type="dataset",
            create_pr=True,
        )
    except Exception as exc:  # noqa: BLE001 - any failure here must reach the submitter, not a log
        return (
            f"**Not submitted.** The queue at `{REQUESTS_REPO}` did not accept it: `{exc}`.\n\n"
            "Nothing was captured — this is not a display problem, your result is not queued.\n\n"
            f"Working route, no account or token needed: [open an issue]({GUARANTEED_ROUTE}) and "
            "attach the same JSON. A maintainer validates and promotes it exactly as the queue "
            "would have."
        )
    pr = getattr(info, "pr_url", None)
    if not pr:
        return (
            "**Uncertain.** The upload returned no pull-request URL, so there is nothing to point "
            "you at and no way to confirm it queued.\n\n"
            f"Treat it as not submitted and [open an issue]({GUARANTEED_ROUTE}) with the JSON."
        )
    return f"Submitted — [PR opened]({pr}) on `{REQUESTS_REPO}` for review."


_DEMO_BANNER = (
    "> ⚠️ **Demo data.** These results come from the deterministic CPU **stub** policy, not a "
    "real model. Illustrative until real-model runs are added (GPU command in the README)."
)
_REAL_BANNER = "> ✅ Includes real-model results."
_TRANSFER_NOTE = (
    "> **Honest scope.** On the real **SmolVLA × LIBERO** policy, only the **instruction** family "
    "transfers today (roleplay 100%, goal_substitution 60%); **visual and injection attacks are "
    "0%** on the real model. Every rate carries its 95% Wilson CI and the benign (`none`) control. "
    "Rows are labelled `real` vs `stub`; stub rows are deterministic scaffolding, not a real "
    "transfer. Evidence, not certification."
)
_INTRO = (
    "# 🦾 Provael — VLA Red-Team ASR Leaderboard\n\n"
    "Attack Success Rate (ASR) of templated attacks against Vision-Language-Action robot "
    "policies in simulation. **Lower ASR = more robust.**\n"
)


def _table(rows: list[dict]) -> gr.Dataframe:
    return gr.Dataframe(
        value=_row_table(rows), headers=ROW_HEADERS, datatype="str", interactive=False, wrap=True
    )


def _provenance_md(provenance: list[dict]) -> str:
    """A one-line-per-source provenance footer (build date, commit, inputs digest, signed)."""
    lines = ["**Provenance.** Each real board is stamped and reproducible from its inputs:"]
    for p in provenance:
        digest = (p.get("inputs_digest") or "")[:16]
        signed = " · signed" if p.get("signed") else ""
        # `measured_with` belongs next to `generated_at`, because the two are routinely different
        # and only one of them is about the numbers.
        measured = ", ".join(p.get("measured_with") or []) or "n/a"
        lines.append(
            f"- `{p['file']}` — built {p.get('generated_at') or 'n/a'} from commit "
            f"`{p.get('commit') or 'n/a'}`, **measured with provael {measured}**, "
            f"inputs `sha256:{digest}…`{signed}"
        )
    return "\n".join(lines)


def build_demo() -> gr.Blocks:
    rows, examples, is_demo, provenance = _load_results()
    open_rows = [r for r in rows if r["policy"] in OPEN_SOURCE_POLICIES]
    with gr.Blocks(title="Provael ASR Leaderboard") as demo:
        gr.Markdown(_INTRO)
        gr.Markdown(_DEMO_BANNER if is_demo else _REAL_BANNER)
        if not is_demo:
            # Above the tables, not below them: a reader who takes one number away should have
            # passed the sentence saying how old it is on the way to it.
            coverage = _coverage_banner(rows, provenance)
            if coverage:
                gr.Markdown(coverage)
            gr.Markdown(_TRANSFER_NOTE)
        with gr.Tabs():
            with gr.Tab("All policies"):
                _table(rows)
            with gr.Tab("Open-source policies"):
                _table(open_rows)
            with gr.Tab("Example payloads"):
                gr.Dataframe(
                    value=_example_table(examples), headers=EXAMPLE_HEADERS,
                    datatype="str", interactive=False, wrap=True,
                )
            with gr.Tab("Submit a result"):
                gr.Markdown(
                    "Submit a `provael leaderboard build` results JSON. It opens a PR to "
                    f"`{REQUESTS_REPO}`; a maintainer validates and promotes it.\n\n"
                    "If the queue is unavailable you are told so plainly and sent to "
                    f"[a GitHub issue]({GUARANTEED_ROUTE}) — which always works. You will never be "
                    "shown a success message for a result that was not captured."
                )
                model_in = gr.Textbox(label="Model id (e.g. org/my-vla)")
                file_in = gr.File(label="results JSON", type="filepath")
                out = gr.Markdown()
                gr.Button("Submit", variant="primary").click(
                    submit_result, inputs=[model_in, file_in], outputs=out
                )
        if provenance:
            gr.Markdown(_provenance_md(provenance))
        gr.Markdown(
            "Built with [`provael`](https://github.com/provael/provael) — "
            "`provael leaderboard build --real <results> [--sign]`. Verify offline with "
            "`provael leaderboard verify`. Apache-2.0."
        )
    return demo


if __name__ == "__main__":
    build_demo().launch()
