# Community

Provael is built in the open by a solo maintainer, with the Embodied AI Security Top 10 meant to
become a community-owned list. Here is where things happen and what to expect.

## Where to talk

[GitHub Discussions](https://github.com/provael/provael/discussions) is the front door:

- **Announcements** — releases, new studies, roadmap notes (maintainer-posted).
- **Top-10 RFC** — propose or dispute a risk for the [Embodied AI Security Top 10](top10.md); see the
  [RFC process](top10-rfc.md).
- **Results** — share a run, a transfer result, or a checkpoint you red-teamed. Numbers welcome — with
  their controls (ASR + 95% CI + benign FPR).
- **Q&A** — usage questions, adapters, calibration, CI wiring.

For a **security vulnerability in the tool**, do not use Discussions — follow
[SECURITY.md](https://github.com/provael/provael/blob/main/SECURITY.md) (private advisory). For a bug
or an over-claim, open an issue with the matching template.

## What to expect

- This is a **solo, build-in-public** project — best-effort response, usually within a few days.
- Security reports are acknowledged within 3 business days (see SECURITY.md).
- Every claim ships with its control. If you think a number is over-claimed, the
  [evidence-defect issue](https://github.com/provael/provael/issues/new?template=evidence-defect.yml)
  is the fastest way to flag it.
- Contributions need a DCO sign-off (`git commit -s`) — see
  [CONTRIBUTING.md](https://github.com/provael/provael/blob/main/CONTRIBUTING.md).

## Build in public

Roadmap, findings, and honest nulls are published as they land — in the
[changelog](https://github.com/provael/provael/blob/main/CHANGELOG.md), the
[findings](findings/2026-instruction-transfer.md), and the pre-registered
[studies](studies/pi0-openpi-transfer.md). A cleanly-measured negative result is a first-class output
here, not a failure to hide.

## Where this project participates

*Accurate as of 2 September 2026. The dates below are other people's deadlines and will go stale —
check the linked source before relying on one.*

**Community indexes.** Provael has open submissions to a number of community-maintained lists of
embodied-AI and ML-security tooling. Those are other people's repositories on other people's
schedules, so the honest statement is that the submissions are open, not that they have all landed.

**Open calls this work is aimed at.**

- **NIST AI Standards "Zero Drafts"** — the initial public draft on public-facing AI documentation
  is open for comment; NIST will consider input received by **16 September 2026**. See
  [the project page](https://www.nist.gov/artificial-intelligence/nists-ai-standards-zero-drafts-pilot-project-accelerate-standardization).
- **SPAIS 2026 — The Science of Physical AI Safety**, a CoRL workshop
  ([spais-ws.org](https://spais-ws.org/)). Submissions close **1 October 2026**. Its third question
  asks whether robot foundation models need evaluation techniques meaningfully different from both
  LLMs and classical robotics, which is the question this tool answers in one narrow way. Worth
  stating plainly: the call is scoped to interpretability, alignment, control and evaluation, it
  does not name red-teaming or hardware-in-the-loop as topics, and Provael has **no hardware result
  of any kind** — so it speaks to part of what that workshop is asking and not the rest.

**Reproductions.** If you maintain a benchmark, a leaderboard or an index and you want a
reproduction run against it, [open an issue](https://github.com/provael/provael/issues/new/choose).
Reproductions of other people's numbers are welcome here and get published whichever way they come
out — including when they fail to reproduce ours.

<!--
========================================================================================
MAINTAINER TODO — one-time GitHub UI actions (cannot be set via API / not in this repo)
========================================================================================

1) SOCIAL PREVIEW IMAGE  (docs/assets/social_preview.png, 1280x640)
   GitHub does not allow setting the social preview via API — upload it by hand:
     Repo -> Settings -> General (the default Settings page) -> scroll to "Social preview"
       -> "Edit" -> "Upload an image..." -> choose docs/assets/social_preview.png -> save.
   This is the card shown when the repo is linked on X / LinkedIn / Slack / Discord.

2) REPO TOPICS  (repo home page -> "About" -> the gear icon -> "Topics")
   Add:
     robot-security, vla, embodied-ai, red-teaming, ai-security, smolvla, libero,
     lerobot, sarif, eu-ai-act, machinery-regulation, robotics, ai-safety

3) DISCUSSIONS + LABELS
   - Settings -> Features -> enable "Discussions", then create the categories above
     (Announcements, Top-10 RFC, Results, Q&A).
   - Labels used by the new issue forms — create if missing (Issues -> Labels):
       attack-family, assessment      (the "top10" label already exists)
========================================================================================
-->
