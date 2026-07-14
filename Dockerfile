# syntax=docker/dockerfile:1
#
# EditScope - Dockerized reproducible scope oracle
# ------------------------------------------------
# The canonical oracle (scope_oracle/) is pure-Python. Its only optional deps
# are pyflakes + mypy, which sharpen the W2 symbolic resolver. The frozen
# soundness suite runs with NO dataset and NO network, so this image is small,
# deterministic, and safe to run in an air-gapped grading environment.
#
# Build:   docker build -t editscope:0.1.0 .
# Run:     docker run --rm editscope:0.1.0            # -> frozen soundness suite
# See DOCKER.md for parity / Track A / live-model usage.

FROM python:3.13-slim

# Reproducible, quiet, no .pyc clutter
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---- Dependency layer (cached until requirements/pyproject change) ----------
# Copy only the metadata needed to resolve deps first, for better layer caching.
COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- Project sources + editable install ------------------------------------
COPY . .
RUN pip install --no-cache-dir -e . \
 && chmod +x docker/entrypoint.sh

# ---- Sanity: bake the soundness guarantee into the build ------------------
# If the frozen invariants ever break, the image fails to build. This turns the
# core scientific claim (never wrongly authorize) into a hard build gate.
RUN python -m scope_oracle.tests.test_audit_freeze \
 && python -m scope_oracle.tests.test_intra_unit_hardening \
 && python -m scope_oracle.tests.test_grounding_precision

# ---- Drop privileges (avoids root-owned files on mounted volumes) ----------
RUN useradd --create-home --uid 1000 editscope \
 && chown -R editscope:editscope /app
USER editscope

# Dataset mount point for parity / Track A (bind-mount ./canitedit here).
ENV CANITEDIT_DIR=/data/canitedit

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["freeze"]
