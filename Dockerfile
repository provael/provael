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

# Resolve deps first (cached) from the lockfile, then install the project.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- runtime: copy only the venv, no build tooling ---
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["provael"]
CMD ["--help"]
