# 00 — Overview

## Project purpose

Provide a single-process Telegram bot that an operator can use to inspect
and perform safe lifecycle operations on Oracle Cloud (OCI) compute
instances. The service is intentionally narrow: list / inspect resources,
power on, gracefully stop, gracefully reboot, look at limits and
read-only network state. Everything else — deletion, IP rotation,
instance sniping, modifying security rules, exposing a web UI — is out
of scope.

The motivation is replacing a heavier Java fork (`oci-start`) with a
service whose idle RSS is small enough to comfortably co-exist with
other workloads on a single Oracle Ampere A1 host.

## Scope (in)

| Capability                              | Spec leaf                                             |
| --------------------------------------- | ----------------------------------------------------- |
| Telegram command surface and dispatch   | [`dev_telegram_bot.md`](dev_telegram_bot.md)          |
| OCI SDK integration (read + lifecycle)  | [`dev_oci_client.md`](dev_oci_client.md)              |
| Allowlist, confirmation, OCID masking   | [`dev_security.md`](dev_security.md)                  |
| Container, compose, Nginx, GHCR build   | [`dev_deployment.md`](dev_deployment.md)              |
| End-to-end acceptance                   | [`integration_acceptance.md`](integration_acceptance.md) |

## Explicit non-goals

The service must **not** implement, even as a hidden flag:

1. Any web UI or HTML rendering beyond the static plain-text `/`
   landing page.
2. Resource deletion: instances, boot volumes, VCNs, subnets, security
   lists.
3. Modifying security rules (`/allow_port`, `/deny_port` and similar).
4. Automatic IP rotation, "snipe" loops, or any background lifecycle
   automation.
5. Arbitrary shell execution from Telegram.
6. Multi-user authorization beyond the Telegram allowlist.
7. Bundling a database, message queue, or noVNC / websockify.
8. Any kind of telemetry or beaconing back to the maintainer.

Deviations from this list require a dated entry in
[`../tradeoffs.md`](../tradeoffs.md) before code is written.

## Primary success criteria

S1. **Allowlist enforcement.** A Telegram user outside
`telegram.allowed_user_ids` cannot trigger any command except
`/whoami`. The denial is recorded in the audit log.

S2. **Confirmation for destructive-adjacent actions.** `/stop_instance`
and `/reboot_instance` cannot reach the OCI API without a click on an
inline button generated for that specific request, by the same user,
within the configured TTL (default 60 s).

S3. **OCID masking.** No full OCID appears in any Telegram message a
user can receive. Backing OCIDs in the audit log are full strings (the
log is server-side).

S4. **Health endpoint.** `GET http://127.0.0.1:8818/healthz` returns
HTTP 200 with `{"status":"ok", ...}` within 3 seconds while the bot is
running.

S5. **Memory budget.** Idle RSS of the running container ≤ 120 MiB on
`linux/amd64` and `linux/arm64`.

S6. **Verifiability without OCI.** `uv run pytest -q` exits 0 in under
five seconds without any network access.

## Top-level decomposition

```
                  Telegram API           OCI APIs
                       │                    │
                       ▼                    ▼
   ┌──────────────────────────────────────────────────┐
   │                  app process                     │
   │                                                  │
   │   bot.py (PTB Application + allowlist guard)     │
   │       │                                          │
   │       ▼                                          │
   │   commands/* (one module per command family)     │
   │       │                                          │
   │       ▼                                          │
   │   oci_client.py (sync SDK behind to_thread)      │
   │                                                  │
   │   confirmations.py — TTL-bound action tokens     │
   │   security.py     — allowlist + OCID masking     │
   │   audit.py        — JSONL append-only log        │
   │   web.py          — aiohttp /, /healthz, /version│
   │   main.py         — entrypoint, lifecycle, sig   │
   └──────────────────────────────────────────────────┘
                       │
                       ▼
              Nginx (port 8088) ─→ users
```

## Links

- [`docs/design/architecture.md`](../design/architecture.md) — concrete
  process model, module table, concurrency invariants, failure model.
- [`docs/matrix_implementation.md`](../matrix_implementation.md) — spec
  section to source-file mapping with verification status.
- [`docs/tradeoffs.md`](../tradeoffs.md) — project-level deviations
  (stable `T-NNN` IDs referenced from leaf docs).
- [`docs/specs/legacy/oci-helper-lite-tg-spec.md`](legacy/oci-helper-lite-tg-spec.md)
  — original pre-implementation spec, preserved verbatim.
