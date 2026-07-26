# Reproducible Provael image (CPU core — no GPU, no model). Multi-stage uv build.
#   docker build -t provael .
#   docker run --rm provael attack --recipe full-sweep
#
# Pin the uv image by digest in your own fork for full reproducibility.
FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim AS build

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
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
# Defence in depth: the CPU CLI needs no root, so run as an unprivileged user.
RUN useradd --create-home --uid 10001 provael
USER provael
ENTRYPOINT ["provael"]
CMD ["--help"]
