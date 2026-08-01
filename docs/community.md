# Community

Provael is built in the open by a solo maintainer, with the Embodied AI Security Top 10 meant to
become a community-owned list. Here is where things happen and what to expect.

## Where to talk

[GitHub Discussions](https://github.com/provael/provael/discussions) is the front door:

- **Announcements** — releases, new studies, roadmap notes (maintainer-posted).
- **Top-10 RFC** — propose or dispute a risk for the [Embodied AI Security Top 10](TOP10.md); see the
  [RFC process](TOP10_RFC.md).
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
