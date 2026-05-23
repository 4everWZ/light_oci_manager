### Build stage — uv produces a minimal site-packages tree without dev deps.
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Install uv from the official static binary image to avoid pulling pip + curl.
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /src

# Cache the dependency layer separately from the source tree.
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync --no-dev --no-install-project --frozen 2>/dev/null \
 || uv sync --no-dev --no-install-project

COPY app ./app
RUN uv sync --no-dev --frozen 2>/dev/null \
 || uv sync --no-dev


### Runtime stage — copy the prepared venv and app, drop root.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=Asia/Shanghai

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
 && mkdir -p /app/oci-helper/keys /app/oci-helper/logs /app/oci-helper/data \
 && chown -R app:app /app

WORKDIR /app/oci-helper

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app /app/app

USER app

EXPOSE 8818

CMD ["python", "-m", "app.main"]
