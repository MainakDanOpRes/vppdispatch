# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy only the files needed to resolve dependencies first
# (keeps this layer cached when only source code changes)
COPY pyproject.toml .
COPY src/ src/

# Install production deps into a local venv
RUN uv sync --no-dev


# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Copy the venv and source from the builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src   /app/src

# Make sure the venv binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

# Don't buffer stdout/stderr (so logs appear immediately)
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "vpp_dispatch.api:app", "--host", "0.0.0.0", "--port", "8000"]