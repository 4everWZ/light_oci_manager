# Implementation Matrix

Maps spec sections in [`docs/specs/oci-helper-lite-tg-spec.md`](specs/oci-helper-lite-tg-spec.md)
to current implementation locations and verification status.

Status legend:
- `done`   — implemented and covered by tests or manual verification
- `wip`    — partially implemented
- `todo`   — accepted scope, not yet implemented
- `out`    — explicitly out of P0 per user decision

Tradeoff IDs reference [`docs/tradeoffs.md`](tradeoffs.md).

## P0 scope

| Spec §   | Requirement                          | Implementation                                  | Verification                          | Status | Tradeoff |
| -------- | ------------------------------------ | ----------------------------------------------- | ------------------------------------- | ------ | -------- |
| 4.1      | `/start /help /status /ping /whoami` | `app/commands/basic.py`                         | `tests/test_commands_basic.py`        | done   | —        |
| 4.2      | YAML config + multi profile          | `app/config.py`                                 | `tests/test_config.py`                | done   | —        |
| 4.3      | `/instances` and `/instance`         | `app/commands/instances.py`                     | `tests/test_commands_instances.py`    | done   | —        |
| 4.5      | `/public_ip`                         | `app/commands/instances.py::public_ip`          | `tests/test_commands_instances.py`    | done   | —        |
| 5        | aiohttp `/`, `/healthz`, `/version`  | `app/web.py`                                    | `tests/test_web.py`                   | done   | —        |
| 6        | Dockerfile + docker-compose.yml      | `Dockerfile`, `docker-compose.yml`              | manual (`docker compose up`)          | done   | —        |
| 8.1      | Telegram allowlist                   | `app/security.py::check` + `app/bot.py::_authorize` | `tests/test_security.py`, group=-1 guard in `bot.build` | done   | —        |
| 8.2      | OCID masking in user-facing output   | `app/security.py::mask_ocid`, `app/formatters`  | `tests/test_security.py`              | done   | —        |
| 8.4      | Audit log                            | `app/audit.py`                                  | `tests/test_audit.py`                 | done   | —        |
| 9        | Error classification                 | `app/oci_client.py` + command boundary          | `tests/test_commands_instances.py`    | done   | —        |
| 10       | Resource matching (OCID / name / id) | `app/resource_match.py`                         | `tests/test_resource_match.py`        | done   | —        |

## P1 scope (deferred from this iteration)

| Spec §   | Requirement                          | Status | Note                                          |
| -------- | ------------------------------------ | ------ | --------------------------------------------- |
| 4.4      | `/start_instance` etc + confirmation | todo   | scaffolding ready in commands/, not enabled   |
| 4.6      | `/quota`                             | todo   | requires `oci.limits` client                  |

## P2 / Not doing

| Spec §   | Requirement                          | Status | Note                                          |
| -------- | ------------------------------------ | ------ | --------------------------------------------- |
| 4.7      | `/security_lists` read-only          | out    | P2 per spec §13                               |
| §13 "不做" | Web UI / arbitrary exec / delete    | out    | explicitly excluded                           |
