# Pinned to a specific digest of python:3.13-slim (rebuild date 2026-05-22 UTC).
# Pinning to digest forces Buildx to pull this exact image — that's what
# carries patched Debian libxml2 and libexpat1, which a floating tag may
# silently revert to an older rebuild. Refresh the digest via:
#   docker pull python:3.13-slim && docker inspect --format '{{.RepoDigests}}' python:3.13-slim
FROM python:3.13-slim@sha256:7ba5f5888fbe0014ab9edb2278922995c2201fc3752c46b0be24763eb46fa9f3 AS base

# Node.js is needed because the Claude Agent SDK spawns the bundled Claude
# Code CLI as a subprocess.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        nodejs \
        npm \
        tesseract-ocr \
        tesseract-ocr-deu \
        tesseract-ocr-eng \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged runtime user (matches macOS UID 501 by default).
ARG UID=501
ARG GID=20
RUN groupadd -g ${GID} aido 2>/dev/null || true \
    && useradd -m -u ${UID} -g ${GID} -s /bin/bash aido 2>/dev/null || true

WORKDIR /app

# Copy install metadata and source so pip can resolve dependencies.
# We include src/ at this stage since setuptools needs it to read pyproject.toml.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8765
USER aido

CMD ["python", "-m", "aido", "run", "--config", "/app/config.yaml", "--pidfile", "/tmp/aido.pid"]
