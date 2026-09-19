# Trademark policy

**Status, stated plainly.** "Provael" and the Proof-Path mark are **unregistered** marks of
Sattyam Jain. No trademark application has been filed as of 20 September 2026; one is planned in
India (classes 9 and 42). The ™ symbol on this project's surfaces denotes a claimed, unregistered
mark — it is not a registration claim, and this file will change the day a filing exists.

The code is Apache-2.0. Section 6 of that licence grants no trademark rights and expects the
project to say what it does permit; this is that statement. It follows the shape of the Mozilla
trademark policy: truthful reference is free, confusion is not.

## You may, without asking

- **Refer to the project truthfully**: "built with Provael", "tested with Provael 0.43.0",
  "compatible with Provael", "a fork of Provael" — in text, talks, papers, READMEs and package
  metadata, including a link to provael.com or the repository.
- **Redistribute unmodified releases** (the sdist, wheel, container image or a Git tag as published)
  under the name Provael.
- **Cite the measured results and the Embodied AI Security Top 10** by name. The Top 10 is a
  separate community document under CC-BY-SA 4.0; it is deliberately unbranded and this policy does
  not cover it.

## You need written permission for

- **Modified builds distributed under the name.** A fork or patched build must be renamed so a user
  can tell whose measurement they are running; keeping "Provael" in the package name, the CLI name
  or the report header of a modified build is not permitted. Saying "based on Provael" is.
- **Hosted or managed services named after the project** ("Provael as a service", "Provael Cloud",
  a paid evaluation offered under the name), and any product, company or domain name that
  incorporates "Provael".
- **Use of the Proof-Path logo** other than as an unmodified link to the project.

## Reserved

- **"Provael Attested"** and any phrase implying that an attestation was issued by the project is
  reserved for attestations signed under the project's published key
  (`leaderboard.pub`; see `docs/attestation.md`). An attestation produced with `provael attest` and
  your own key is yours and says so in its payload; it is not "Provael Attested".
- Nothing here grants an endorsement. A result produced with the tool is your result; the project
  did not review it unless a signed artifact says it did.

## Asking

Write to hello@provael.com with what you want to call the thing and where it will appear. The
default answer to a truthful, non-confusing use is yes; the answer to a use that suggests the project
produced, reviewed or endorsed something it did not is no.

## The name and the standard

Keep the product name distinct from the standard's name when citing either: the Embodied AI
Security Top 10 is not a Provael product, and Provael is not affiliated with or endorsed by the
OWASP® Foundation or MITRE®, whose own marks belong to them.
