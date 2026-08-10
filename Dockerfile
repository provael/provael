# Reproducible Provael image (CPU core — no GPU, no model). Multi-stage uv build.
#   docker build -t provael .
#   docker run --rm provael attack --recipe full-sweep
#
# BOTH BASES ARE PINNED BY DIGEST, not by tag. A tag is a moving pointer: `python:3.12-slim-bookworm`
# is rebuilt on every CVE patch, so the same Dockerfile builds a different image next week and the
# published `provael/provael:0.33.0` stops being reproducible from its own source. For a security
# tool that ships evidence artifacts, "which base did this run on" has to have one answer.
#
# Each digest is the MULTI-ARCH INDEX (application/vnd.oci.image.index.v1+json), never a per-arch
# manifest. Pinning one architecture's manifest would silently drop arm64 from the published image —
# which already happened once here, in the other direction, and was invisible to CI because the
# runner is x86_64. Verify before changing:
#
#   docker buildx imagetools inspect python@sha256:4766d8... | head -3   # must say "Index"
#
# To refresh, resolve the tag and confirm the media type is an index:
#   crane digest python:3.12-slim-bookworm
#
# THIS PIN MUST TRACK THE LOCKFILE FORMAT, not just "some uv". uv.lock is `revision = 3`, a field
# uv 0.5.11 predates entirely, so the old pin failed at `uv sync --locked` with:
#
#     error: Failed to parse `uv.lock` / TOML parse error at line 3320
#
# It had been broken for a while and nobody saw it, because nothing built this image — the
# Dockerfile shipped in the repo and was never exercised by CI. ci.yml now builds it on every PR
# (build only, no push) so the next drift fails in review instead of on the first publish attempt.
# uv 0.9.18 — the pin must track the lockfile format (see above), so bump it deliberately.
FROM ghcr.io/astral-sh/uv@sha256:0b074d1ae15f5c3f1861354917d356e5afbd5a4c53c1190e81ad2f2add46e45b AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Two phases, so that editing src/ does not re-resolve and reinstall the dependency tree: the
# first layer's cache key covers only the lockfile, the second only the project. README.md is
# needed in phase one because pyproject's `readme = "README.md"` is read during metadata prep.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- runtime: copy only the venv, no build tooling ---
# python:3.12-slim-bookworm, resolved 2026-08-10.
FROM python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS runtime
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
# Defence in depth: the CPU CLI needs no root, so run as an unprivileged user.
RUN useradd --create-home --uid 10001 provael
USER provael

# WORKDIR must be somewhere this user can WRITE, and /app is root-owned. Every run writes its
# report to `--out` (default `runs/`, relative to cwd), so with WORKDIR /app the very first
# command anyone tries dies on:
#
#     PermissionError: [Errno 13] Permission denied: 'runs'
#
# `provael --version` still worked, which is exactly why this survived: the image looked fine to
# anything that did not actually run a scan. Keep the unprivileged user — drop the unwritable cwd.
#
# To keep results after `--rm`, mount over it:
#   docker run --rm -v "$PWD/runs:/home/provael/runs" ghcr.io/provael/provael:latest attack --recipe quick
WORKDIR /home/provael

ENTRYPOINT ["provael"]
CMD ["--help"]
