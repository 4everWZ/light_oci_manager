# Implementation Matrix

Maps spec sections in [`docs/specs/`](specs/) (overview:
[`00_overview.md`](specs/00_overview.md); legacy pre-implementation spec
preserved at
[`specs/legacy/oci-helper-lite-tg-spec.md`](specs/legacy/oci-helper-lite-tg-spec.md))
to current implementation locations and verification status.

Status legend:
- `done`   — implemented and covered by tests or manual verification
- `wip`    — partially implemented
- `todo`   — accepted scope, not yet implemented
- `out`    — explicitly out of scope per spec §13

Tradeoff IDs reference [`docs/tradeoffs.md`](tradeoffs.md).

## P0 scope

| Spec §   | Requirement                          | Implementation                                  | Verification                          | Status | Tradeoff |
| -------- | ------------------------------------ | ----------------------------------------------- | ------------------------------------- | ------ | -------- |
| 4.1      | `/start /help /status /ping /whoami` | `app/commands/basic.py`                         | `tests/test_commands_basic.py`        | done   | —        |
| 4.2      | YAML config + multi profile          | `app/config.py`                                 | `tests/test_config.py`                | done   | —        |
| 4.3      | `/instances` and `/instance`         | `app/commands/instances.py`                     | `tests/test_commands_instances.py`    | done   | —        |
| 4.5      | `/public_ip`                         | `app/commands/instances.py::_public_ip`         | `tests/test_commands_instances.py`    | done   | —        |
| 5        | aiohttp `/`, `/healthz`, `/version`  | `app/web.py`                                    | `tests/test_web.py`                   | done   | —        |
| 6        | Dockerfile + docker-compose.yml      | `Dockerfile`, `docker-compose.yml`              | manual (`docker compose up`)          | done   | —        |
| 8.1      | Telegram allowlist                   | `app/security.py::check` + `app/bot.py::_authorize` | `tests/test_security.py`, group=-1 guard in `bot.build` + callback re-check in operations | done | — |
| 8.2      | OCID masking in user-facing output   | `app/security.py::mask_ocid`, `app/formatters`  | `tests/test_security.py`              | done   | —        |
| 8.4      | Audit log                            | `app/audit.py` + `app/commands/__init__.py`     | `tests/test_audit.py`                 | done   | —        |
| 9        | Error classification                 | `app/oci_client.py::OciApiError` + command boundary | covered across `tests/test_commands_*.py` | done | — |
| 10       | Resource matching (OCID / name / id) | `app/resource_match.py`                         | `tests/test_resource_match.py`        | done   | —        |

## P1 scope

| Spec §   | Requirement                          | Implementation                                  | Verification                          | Status | Tradeoff |
| -------- | ------------------------------------ | ----------------------------------------------- | ------------------------------------- | ------ | -------- |
| 4.4      | `/start_instance`                    | `app/commands/operations.py::_start_instance`   | `tests/test_commands_operations.py`   | done   | T-001    |
| 4.4 / 8.3 | `/stop_instance` + confirmation     | `app/commands/operations.py::_confirm_command` + `_callback` | `tests/test_commands_operations.py` | done | T-001 |
| 4.4 / 8.3 | `/reboot_instance` + confirmation   | `app/commands/operations.py::_confirm_command` + `_callback` | `tests/test_commands_operations.py` | done | T-001 |
| 4.4      | Confirmation token TTL (60 s)        | `app/confirmations.py::ConfirmationStore`       | `tests/test_confirmations.py`         | done   | —        |
| 4.6      | `/quota` (compute + limits)          | `app/commands/quota.py`                         | `tests/test_commands_quota.py`        | done   | —        |

## P2 scope

| Spec §   | Requirement                          | Implementation                                  | Verification                          | Status | Tradeoff |
| -------- | ------------------------------------ | ----------------------------------------------- | ------------------------------------- | ------ | -------- |
| 4.7      | `/security_lists` + `/security_list` | `app/commands/network.py`                       | `tests/test_commands_network.py`      | done   | —        |
| §13 P2   | `/boot_volumes`                      | `app/commands/volumes.py`                       | `tests/test_commands_volumes.py`      | done   | —        |
| §13 P2   | `/regions`                           | `app/commands/regions.py`                       | `tests/test_commands_regions.py`      | done   | —        |

## Not doing (per spec §13)

| Spec §   | Requirement                          | Status | Note                                             |
| -------- | ------------------------------------ | ------ | ------------------------------------------------ |
| 4.7      | `/allow_port` / `/deny_port`         | out    | spec §4.7: "Phase 1 不实现修改安全组"            |
| §13 不做 | Web UI                               | out    | explicit non-goal                                |
| §13 不做 | 抢机 / 自动换 IP / 删除资源          | out    | explicit non-goal                                |
| §13 不做 | 一键开放全部端口                     | out    | explicit non-goal                                |
| §13 不做 | Cloudflare 配置 / 地图数据 / 备份 UI | out    | explicit non-goal                                |
| §13 P2   | 按钮式菜单                           | out    | Telegram slash commands cover the UI surface; inline buttons used only for stop/reboot confirmation |
| §13 P2   | 定时状态通知                         | out    | no user-facing requirement; cron belongs outside the bot |
| §13 P2   | 低内存 Go 重写                       | out    | Phase 2 — out of this iteration                  |
