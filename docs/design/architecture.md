# oci-helper-lite-tg Architecture

Reference: [`docs/specs/oci-helper-lite-tg-spec.md`](../specs/oci-helper-lite-tg-spec.md)

## Process model

Single Python process inside one Docker container. The process runs two
co-operating asyncio tasks:

```
                          aiohttp HTTP server  (port 8818)
                              GET /, /healthz, /version
                              ↑
                              │
  ┌───────────────────────────┴────────────────────────────┐
  │                  asyncio event loop                    │
  │                                                        │
  │   python-telegram-bot Application (long-polling)       │
  │       command handlers → run_in_executor → OCI SDK     │
  │                                                        │
  └────────────────────────────────────────────────────────┘
                              │
                              ↓
                    ThreadPoolExecutor (default)
                              │
                              ↓
                    oci.core / oci.identity (blocking, HTTPS)
```

Why this shape:

- python-telegram-bot is asyncio-native and we want fast command latency.
- Official `oci` SDK is sync-only, so blocking calls are pushed to the default
  executor via `asyncio.to_thread()` to keep the event loop responsive.
- aiohttp on the same loop is cheap and gives `Nginx → 127.0.0.1:8818`
  a real HTTP target without bringing in FastAPI/Uvicorn.

## Module boundaries

| Module                       | Owns                                                     | Depends on                |
| ---------------------------- | -------------------------------------------------------- | ------------------------- |
| `app/config.py`              | YAML load, validation, runtime config dataclasses        | stdlib, PyYAML            |
| `app/security.py`            | allowlist check, OCID masking                            | config                    |
| `app/audit.py`               | append-only JSONL audit logger                           | stdlib                    |
| `app/resource_match.py`      | resolving user input → OCID                              | none                      |
| `app/formatters.py`          | Telegram-safe formatting + chunking                      | none                      |
| `app/oci_client.py`          | per-profile OCI SDK clients, executor-bound calls        | config, oci               |
| `app/commands/basic.py`      | `/start /help /status /ping /whoami`                     | config, security, audit   |
| `app/commands/instances.py`  | `/instances /instance /public_ip`                        | oci_client, formatters    |
| `app/bot.py`                 | Telegram Application wiring, middleware                  | commands, security, audit |
| `app/web.py`                 | aiohttp routes for `/`, `/healthz`, `/version`           | config                    |
| `app/main.py`                | entrypoint, lifecycle, signal handling                   | bot, web, config          |

`commands/*` never imports `bot.py`; `bot.py` imports commands. This keeps
command handlers unit-testable with a fake `Update` / `Context`.

## Configuration topology

- Single YAML file mounted read-only at `/app/oci-helper/config.yml`.
- Private keys mounted read-only under `/app/oci-helper/keys/`.
- Audit log written to `/app/oci-helper/logs/audit.log`.
- No environment-variable secrets in P0; all secrets come from the mounted
  YAML + key directory. See spec §4.2.

## Concurrency invariants

- Exactly one Telegram polling loop.
- Each `OciClient` instance is per-profile and created at startup.
  The SDK clients are thread-safe for read-only operations we use.
- Audit log writes use a single asyncio `Lock` to keep JSONL lines intact.

## Failure model

- Config errors are fatal at startup; the process exits with a non-zero code
  so docker-compose `restart: always` does not loop forever on a broken
  config without surfacing the cause.
- OCI API errors are caught at the command boundary, returned to the user
  as a short message, and the full traceback + request-id (if any) go to
  stderr + the audit record.
- Telegram send errors are logged but do not crash the bot.
