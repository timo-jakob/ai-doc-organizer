# Bookworm (Debian 12) base, pinned to a specific digest (rebuild 2026-05-31).
# We switched off the default `python:3.14-slim` (trixie) because Debian 13
# hadn't yet shipped the libxml2 / libexpat1 patches Snyk was flagging;
# Bookworm has had those for longer. Pinning to digest stops Buildx from
# silently moving us to an older rebuild. Refresh via:
#   docker pull python:3.14-slim-bookworm && \
#   docker inspect --format '{{.RepoDigests}}' python:3.14-slim-bookworm
FROM python:3.14-slim-bookworm@sha256:a9bee15510a364124aa24692899d269835683b883de42f7ebec8c293cf679ccb AS base

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
