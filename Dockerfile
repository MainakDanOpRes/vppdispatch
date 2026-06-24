# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copy lockfile and project metadata first (layer cache)
COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install deps using the locked versions, no resolution needed
RUN uv sync --frozen --no-dev


# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src   /app/src

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Change the CMD line to this:
CMD ["sh", "-c", "uvicorn vpp_dispatch.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
