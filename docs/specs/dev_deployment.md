# dev_deployment — Container, compose, Nginx, GHCR

## 1. Goals & Boundaries

### Goals

- Run the service as a single non-root container.
- Keep the host-side deployment topology compatible with the upstream
  `oci-helper` layout, so the operator can swap the Java container for
  this one without touching Nginx or the host directory tree.
- Provide multi-arch (`linux/amd64` + `linux/arm64`) prebuilt images so
  the same image works on x86 laptops and Oracle Ampere A1 (arm64)
  hosts.
- Make every behaviour-changing build artefact reproducible from `main`
  via GitHub Actions.

### Boundaries

- The image does not include `websockify`, noVNC, a watcher, or any
  process supervisor. It runs exactly one Python process.
- TLS termination is out of scope for the container. Nginx (or any
  fronting load balancer) owns TLS.
- Secret material (`bot_token`, OCI private key) is mounted, never
  baked. The image must not be useful if leaked.

## 2. Interfaces / Responsibilities

### 2.1 Container image

| Property               | Value                                                                 |
| ---------------------- | --------------------------------------------------------------------- |
| Base                   | `python:3.12-slim`                                                    |
| Builder tool           | `uv` 0.5.4 (copied from `ghcr.io/astral-sh/uv`)                       |
| Runtime user           | `app` (non-root, system uid)                                          |
| Workdir                | `/app/oci-helper`                                                     |
| Exposed port           | `8818/tcp`                                                            |
| Entrypoint             | `python -m app.main`                                                  |
| Config path (env)      | `OCI_HELPER_CONFIG=/app/oci-helper/config.yml`                        |
| Log level (env)        | `OCI_HELPER_LOG_LEVEL=INFO`                                           |

### 2.2 Mounted layout (per `docker-compose.yml`)

```
${HOST_OCI_HELPER_DIR:-/home/ubuntu/oci-helper}/
├── config.yml      → /app/oci-helper/config.yml  (ro)
├── keys/           → /app/oci-helper/keys        (ro)
├── logs/           → /app/oci-helper/logs        (rw)
└── data/           → /app/oci-helper/data        (rw)
```

`config.yml` and every file under `keys/` must have mode `0o600`. The
config loader refuses startup if the key file is world-readable.

### 2.3 Compose options

- `mem_limit: 256m` — twice the idle budget, leaves room for spikes.
- `restart: always` — a config error exits with code 2, which the
  operator will see in `docker logs`; non-fatal errors are caught and
  logged.
- `healthcheck:` runs `urllib.request.urlopen("http://127.0.0.1:8818/healthz")`
  every 30 s with a 5 s timeout and a 15 s grace period.

### 2.4 Nginx topology

```
0.0.0.0:8088   ─→   127.0.0.1:8818
       (Nginx)            (container)
```

The Nginx vhost is provided in [`README.md`](../../README.md). The
service does not depend on Nginx — `curl http://127.0.0.1:8818/healthz`
works directly.

### 2.5 GitHub Actions build pipeline

Triggers:

- push to `main`
- push of any `v*` tag
- manual `workflow_dispatch`

Outputs (to GitHub Container Registry):

- `ghcr.io/<owner>/<repo>:latest` (on `main`)
- `ghcr.io/<owner>/<repo>:<git-sha-short>` (on every push)
- `ghcr.io/<owner>/<repo>:<tag>` (on tag pushes, e.g. `v0.1.0`)
- Platforms: `linux/amd64` and `linux/arm64`.

The workflow runs `uv run pytest -q` and `uv run ruff check` as a gate
before any image push.

## 3. Code Mapping

| Concern                       | Location                                                                  |
| ----------------------------- | ------------------------------------------------------------------------- |
| Image build                   | [`Dockerfile`](../../Dockerfile)                                          |
| Local deploy                  | [`docker-compose.yml`](../../docker-compose.yml)                          |
| Configuration template        | [`config.example.yml`](../../config.example.yml)                          |
| CI build & publish            | [`.github/workflows/docker.yml`](../../.github/workflows/docker.yml)      |
| Health endpoint               | [`app/web.py`](../../app/web.py)                                          |
| Process lifecycle             | [`app/main.py`](../../app/main.py)                                        |

## 4. Tradeoffs

- **Long-polling, not webhook.** Avoids exposing an HTTPS endpoint to
  Telegram and keeps the deployment behind Nginx without TLS work.
- **`uv sync` inside the Dockerfile rather than `pip install`.** uv is
  faster and produces a lockfile-derived environment. The cost is one
  external image dependency (`ghcr.io/astral-sh/uv`).
- **No multi-stage push of the venv.** We do copy `/opt/venv` between
  stages, but we do not strip the SDKs or compile against musl. The
  resulting image is ~120 MB compressed and ~280 MB on disk; smaller
  is possible (alpine + manual wheel build) but the next bottleneck is
  the OCI SDK, which is 30 MB on its own.

## 5. Verification

### Automatic

- The CI workflow refuses to push images when either `uv run pytest -q`
  or `uv run ruff check` fails.
- `docker build .` is implicitly verified by every CI run (the GHCR
  push step depends on it).
- Healthcheck loop is exercised in `docker compose up` smoke runs.

### Manual

- `curl http://127.0.0.1:8818/healthz` on the host returns
  `{"status":"ok",...}` within seconds of `docker compose up -d`.
- `curl http://127.0.0.1:8088/healthz` (through Nginx) returns the same
  payload.
- `docker stats --no-stream` shows idle RSS ≤ 120 MiB.

The full acceptance checklist lives in
[`integration_acceptance.md`](integration_acceptance.md).
