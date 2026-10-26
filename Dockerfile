# Thoma Studio in one container: Python app, headless Chromium renderer, Qoder CLI and Claude CLI
# (the script writers), the local backup voice and the music. Your data, videos, keys and YouTube
# sign-in live outside the image (see docker-compose.yml), so rebuilding never loses anything.
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:/root/.local/bin:$PATH

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tzdata git \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm i -g @qoder-ai/qodercli \
 && npm cache clean --force \
 && rm -rf /var/lib/apt/lists/*

# Claude Code: backup script writer (signs in with CLAUDE_CODE_OAUTH_TOKEN from .env)
RUN curl -fsSL https://claude.ai/install.sh | bash

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project --python /usr/local/bin/python3 \
 && playwright install --with-deps chromium-headless-shell \
 && rm -rf /var/lib/apt/lists/*

COPY . .
RUN uv sync --frozen --python /usr/local/bin/python3 && ./deploy/fetch-assets.sh

CMD ["thoma", "daemon"]
