# Tradeoffs Log

Records approved or unavoidable deviations from the spec. Each entry has a
stable ID so the matrix and design docs can reference it without duplicating
the rationale.

## Format

```
## T-NNN — short title

Date: YYYY-MM-DD
Scope: spec §X.Y or module path
Status: accepted | superseded | reverted

### Decision

What was actually done.

### Why

Why the spec direction was changed or could not be followed verbatim.

### Impact

What downstream behavior, verification, or future work this affects.
```

## Entries

## T-001 — Default to graceful SOFTSTOP / SOFTRESET

Date: 2026-05-23
Scope: spec §4.4 (`/stop_instance`, `/reboot_instance`), `app/commands/operations.py`
Status: accepted

### Decision

`/stop_instance` issues the OCI ``SOFTSTOP`` action and `/reboot_instance`
issues ``SOFTRESET``. These are the *graceful* variants (ACPI shutdown /
ACPI restart) rather than the hard variants (``STOP`` / ``RESET``).

### Why

The spec uses the bare words "stop" and "reboot" without committing to a
specific OCI action. OCI distinguishes:

- `STOP`     — hard power-off; risk of filesystem corruption.
- `SOFTSTOP` — request guest OS to shut down cleanly.
- `RESET`    — hard reboot.
- `SOFTRESET` — graceful reboot.

Defaulting to the graceful actions matches the intent of a "lite admin bot"
operated by humans through Telegram, where the worst case of an aborted
session leaves the VM in an unclean state. A future feature flag could
expose the hard variants if needed (e.g. when the guest is unresponsive).

### Impact

- Stop/reboot are slower (the OCI API waits for ACPI ack before transitioning).
- A hung guest will not shut down via `/stop_instance`; the user must wait
  for the OCI shutdown timeout or fall back to OCI Console / API.
- The confirmation message displays the actual action name ("Confirm
  SOFTSTOP instance?") so the user can see what they are about to do.

The action whitelist in `app/oci_client.py::INSTANCE_ACTIONS` accepts all
five action names so a future hard-stop command is straightforward to add.
