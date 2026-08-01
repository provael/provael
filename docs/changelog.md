# Changelog

The changelog is maintained at the repository root as
[`CHANGELOG.md`](https://github.com/provael/provael/blob/main/CHANGELOG.md) — that file is the
canonical record and is updated in the same PR as the change it describes.

It is linked rather than duplicated here on purpose. A second copy inside the docs would be a second
thing to update, and the failure mode of two copies is that one of them is quietly wrong — which for
a changelog is worse than not having one, because a reader trusts it to say what changed.

- **[Full changelog](https://github.com/provael/provael/blob/main/CHANGELOG.md)** — every release,
  with the reasoning.
- **[Releases](https://github.com/provael/provael/releases)** — tagged versions and their artifacts.
- **[Errata](errata.md)** — corrections to artifacts that were already published. A changelog says
  what changed going forward; an erratum says what was wrong in something you may already hold.

## Reading a release honestly

Two things in this project's history are worth knowing when you read a diff:

- **A release re-pins the version in roughly a dozen adopter-facing files** — the citation file, the
  Action, the pre-commit hook, the README and docs snippets, the example CI workflows.
  `tests/test_version_consistency.py` scans every tracked file for a stale pin or one naming a tag
  that never existed, so a release is a search-and-replace the suite then confirms.
- **A large share of `fix:` and `docs:` commits are self-corrections of this project's own claims.**
  That is deliberate and the pattern is consistent: correct the claim *and* land the guard that makes
  the error impossible to repeat.
