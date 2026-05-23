# dev_telegram_bot — Telegram command surface

## 1. Goals & Boundaries

### Goals

- Expose every supported feature as a Telegram slash command.
- Reject unauthorized callers with a clear, actionable message that
  reveals their own Telegram user id (so they can request access).
- Require an inline-button confirmation for any command that mutates
  instance state beyond power-on.
- Never make a synchronous OCI SDK call directly on the event loop;
  always defer to a worker thread.

### Boundaries

- The bot owns command routing and middleware (allowlist, audit logging,
  callback dispatch). It does **not** know how to call OCI directly —
  every command delegates to [`dev_oci_client.md`](dev_oci_client.md).
- The bot does not maintain persistent per-user state across restarts.
  Confirmation tokens are in-memory only; a restart cancels every
  pending action.
- Group chat, channels, and inline mode are out of scope. The bot is
  designed for 1:1 conversations with allowlisted operators.

## 2. Interfaces / Responsibilities

### 2.1 Command surface (slash commands)

| Command            | Args                                | Mutation | Confirmation | Spec link                  |
| ------------------ | ----------------------------------- | -------- | ------------ | -------------------------- |
| `/start`           | —                                   | no       | —            | legacy §4.1                |
| `/help`            | —                                   | no       | —            | legacy §4.1                |
| `/status`          | —                                   | no       | —            | legacy §4.1                |
| `/ping`            | —                                   | no       | —            | legacy §4.1                |
| `/whoami`          | —                                   | no       | bypass allowlist | legacy §4.1            |
| `/instances`       | `[profile]`                         | no       | —            | legacy §4.3                |
| `/instance`        | `<name\|short_id> [profile]`        | no       | —            | legacy §4.3                |
| `/public_ip`       | `[name\|short_id] [profile]`        | no       | —            | legacy §4.5                |
| `/start_instance`  | `<name\|short_id> [profile]`        | OCI START | no           | legacy §4.4                |
| `/stop_instance`   | `<name\|short_id> [profile]`        | OCI SOFTSTOP | yes      | legacy §4.4, T-001         |
| `/reboot_instance` | `<name\|short_id> [profile]`        | OCI SOFTRESET | yes     | legacy §4.4, T-001         |
| `/quota`           | `[profile]`                         | no       | —            | legacy §4.6                |
| `/security_lists`  | `[profile]`                         | no       | —            | legacy §4.7                |
| `/security_list`   | `<name\|short_id> [profile]`        | no       | —            | legacy §4.7                |
| `/boot_volumes`    | `[profile]`                         | no       | —            | legacy §13 P2              |
| `/regions`         | —                                   | no       | —            | legacy §13 P2              |

### 2.2 Middleware

A group=`-1` `MessageHandler(filters.COMMAND)` runs before any command
handler:

1. Extracts the command token from the message.
2. Lets it through if the command is in `PUBLIC_COMMANDS`
   (`{"whoami"}` only).
3. Otherwise calls `security.check`. On deny, replies with the
   "Unauthorized" template, writes an audit entry, and raises
   `ApplicationHandlerStop` so no command handler runs.

### 2.3 Callback dispatch

`/stop_instance` and `/reboot_instance` create a `PendingAction` in the
`ConfirmationStore` and send an `InlineKeyboardMarkup` with two buttons
whose callback data follows the format `cf:<verb>:<token>`. The
`CallbackQueryHandler` (`pattern=r"^cf:"`) in
`app/commands/operations.py`:

1. Re-checks the allowlist (defence in depth).
2. Reads `verb ∈ {confirm, cancel}` and `token`.
3. Calls `store.take(token, user_id)` (for confirm) or `store.cancel`
   (for cancel). Both require the callback's `from_user.id` to match
   the token owner.
4. On confirm, calls `oci.instance_action(...)` and edits the original
   message to reflect the outcome.

## 3. Code Mapping

| Concern                         | Location                                              |
| ------------------------------- | ----------------------------------------------------- |
| Application + handler wiring    | [`app/bot.py`](../../app/bot.py)                      |
| Shared audit/reply helpers      | [`app/commands/__init__.py`](../../app/commands/__init__.py) |
| Basic info commands             | [`app/commands/basic.py`](../../app/commands/basic.py) |
| Instance read commands          | [`app/commands/instances.py`](../../app/commands/instances.py) |
| Lifecycle + confirmation flow   | [`app/commands/operations.py`](../../app/commands/operations.py) |
| Quota                           | [`app/commands/quota.py`](../../app/commands/quota.py) |
| Network read commands           | [`app/commands/network.py`](../../app/commands/network.py) |
| Boot volumes                    | [`app/commands/volumes.py`](../../app/commands/volumes.py) |
| Regions                         | [`app/commands/regions.py`](../../app/commands/regions.py) |
| Confirmation store              | [`app/confirmations.py`](../../app/confirmations.py)  |

## 4. Tradeoffs

- **Polling, not webhooks.** PTB's long-polling is simpler to operate
  behind a non-public deployment; webhooks would require exposing an
  HTTPS endpoint to Telegram. No code path assumes polling beyond the
  call to `updater.start_polling()` in [`app/main.py`](../../app/main.py),
  so a future switch to webhooks is mechanical.
- **Stateless confirmation store.** Restarts cancel pending actions.
  This is intentional: stale tokens across restarts are a security
  liability, not a UX win.
- **Default to graceful stop/reboot.** See project-level
  [T-001](../tradeoffs.md#t-001--default-to-graceful-softstop--softreset).

## 5. Verification

- Per-command behaviour:
  [`tests/test_commands_basic.py`](../../tests/test_commands_basic.py),
  [`tests/test_commands_instances.py`](../../tests/test_commands_instances.py),
  [`tests/test_commands_operations.py`](../../tests/test_commands_operations.py),
  [`tests/test_commands_quota.py`](../../tests/test_commands_quota.py),
  [`tests/test_commands_network.py`](../../tests/test_commands_network.py),
  [`tests/test_commands_volumes.py`](../../tests/test_commands_volumes.py),
  [`tests/test_commands_regions.py`](../../tests/test_commands_regions.py).
- Confirmation token semantics: TTL, user binding, single-use, and
  concurrent uniqueness verified in
  [`tests/test_confirmations.py`](../../tests/test_confirmations.py).
- Allowlist guard tested via the operations callback denial test and
  [`tests/test_security.py`](../../tests/test_security.py).
- No test calls the real Telegram or OCI APIs.
