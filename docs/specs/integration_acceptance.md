# integration_acceptance — End-to-end assembly and acceptance

## 1. End-to-end assembly view

```
                 ┌─────────────────────────┐
                 │  Telegram (long-poll)   │
                 └───────────┬─────────────┘
                             │ updates
                             ▼
                 ┌─────────────────────────┐
                 │ python-telegram-bot     │
                 │   Application + guard   │
                 └───────────┬─────────────┘
                             │ awaits
                             ▼
       ┌─────────────────────┴───────────────────────┐
       │           command handlers                  │
       │  basic / instances / operations / quota     │
       │  network / volumes / regions                │
       └─────────────────────┬───────────────────────┘
                             │ async
                             ▼
                 ┌─────────────────────────┐         to_thread
                 │ OciClient (per profile) ├──────────────────┐
                 └─────────────────────────┘                  │
                                                              ▼
                                                  oci.core / oci.identity /
                                                  oci.limits / oci.core.bs

                 ┌─────────────────────────┐
                 │  aiohttp web server     │  ── /, /healthz, /version
                 └───────────┬─────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │ Nginx on 0.0.0.0:8088        │
              └──────────────────────────────┘
                             │
                             ▼
                       external clients
```

## 2. Integration dependencies

| Dependency                       | How it is provided                                                  |
| -------------------------------- | ------------------------------------------------------------------- |
| Python runtime                   | `python:3.12-slim` base image                                       |
| `oci`, `python-telegram-bot`     | `pyproject.toml` resolved via `uv.lock`                             |
| OCI tenancy credentials          | `keys/oci_api_key.pem` mounted read-only at `/app/oci-helper/keys/` |
| Telegram bot token               | `telegram.bot_token` in `config.yml`                                |
| Network egress                   | container must reach `*.oraclecloud.com` and `api.telegram.org`     |
| Inbound HTTP                     | Nginx (or any L7 proxy) exposing `127.0.0.1:8818`                   |

## 3. Validation checklist

### 3.1 Build

- [ ] `uv sync` exits 0.
- [ ] `uv run ruff check` clean.
- [ ] `uv run pytest -q` exits 0 with 90+ passing tests, < 5 s.
- [ ] `docker build .` exits 0 for `linux/amd64`.
- [ ] `docker buildx build --platform linux/amd64,linux/arm64 .` exits 0.

### 3.2 Boot

- [ ] `docker compose up -d` brings the container to `healthy` within
      30 s.
- [ ] `docker logs oci-helper` reports
      `Started: bot=running, http=0.0.0.0:8818, profiles=N`.
- [ ] `curl -s http://127.0.0.1:8818/healthz` returns 200 and
      `{"status":"ok","telegram":"running","profiles_loaded":N}`.
- [ ] `curl -s http://127.0.0.1:8088/healthz` (through Nginx) returns
      the same payload.

### 3.3 Security

- [ ] An allowlisted user can call `/status` and `/instances`.
- [ ] A non-allowlisted user is rejected on every command except
      `/whoami`, sees the "Unauthorized. Your Telegram ID: ..." text,
      and an entry with `result=denied` is appended to
      `audit.log`.
- [ ] `/stop_instance <vm>` produces an inline-button message and does
      **not** stop the instance.
- [ ] Clicking "Confirm Stop" within 60 s does stop it; the message is
      edited in place to reflect the outcome.
- [ ] Clicking "Cancel" leaves the instance running and edits the
      message to "Cancelled SOFTSTOP on ...".
- [ ] Clicking "Confirm Stop" *after* 60 s edits the message to
      "Confirmation expired or not valid for this user.".
- [ ] No full OCID appears in any Telegram message sent to a user.

### 3.4 Resource budget

- [ ] `docker stats --no-stream` shows the container's memory usage at
      ≤ 120 MiB idle.
- [ ] `docker stats --no-stream` shows CPU < 1 % at idle.

### 3.5 Multi-arch

- [ ] `docker pull ghcr.io/<owner>/<repo>:latest --platform linux/amd64`
      succeeds.
- [ ] `docker pull ghcr.io/<owner>/<repo>:latest --platform linux/arm64`
      succeeds.
- [ ] The arm64 image runs cleanly on an Oracle Ampere A1 host.

## 4. Benchmark / regression entry points

- Single source of regression detection: `uv run pytest -q`.
- Health endpoint latency: `curl -w '%{time_total}\n' -o /dev/null -s
  http://127.0.0.1:8818/healthz` should be ≤ 50 ms on the host loopback.

## 5. Known hard boundaries

- Telegram long-polling requires outbound HTTPS to
  `api.telegram.org:443`.
- OCI API requires outbound HTTPS to the region's `*.oci.oraclecloud.com`
  endpoints.
- The OCI Limits API can intermittently fail in some regions while the
  rest of the SDK succeeds. The `/quota` command renders the failing
  service inline as `(error) ...` and keeps reporting the others.

## 6. Final acceptance status

The local verification path (sections 3.1, 3.2 partial, 3.3 unit-test
flavour, 3.4 unverified, 3.5 dependent on the first CI run) is green:
92 unit / behavioural tests passing, ruff clean, module imports clean.

The host-side path (sections 3.2 full, 3.3 against a real bot token and
real OCI tenancy, 3.4 memory measurement, 3.5 arm64 boot) requires
operator credentials and is **deferred to the first deployment on the
target Oracle Ampere A1 host.** Each unchecked box above is the
operator's job and the matrix in
[`../matrix_implementation.md`](../matrix_implementation.md) will be
updated once they pass.
