# dev_security — Allowlist, confirmation, OCID masking, audit

## 1. Goals & Boundaries

### Goals

- Enforce a Telegram user allowlist on every command except `/whoami`.
- Bind every stop/reboot to an inline-button confirmation that is
  user-bound, single-use, and time-bounded.
- Prevent full OCIDs from leaking into user-facing messages.
- Produce a tamper-evident JSONL audit trail of every command outcome,
  including denied attempts.

### Boundaries

- This component does not authenticate against Telegram itself; it
  trusts the `from_user.id` Telegram provides over its API. Telegram's
  trust model is the upstream boundary.
- The audit log is append-only on the local filesystem. Off-host
  forwarding (syslog, GCP / OCI Logging, etc.) is out of scope and
  belongs to whatever log shipper the operator uses.
- Encrypted storage of the OCI private key is not implemented; the
  operator is expected to mount `keys/` read-only with `0o600` perms
  and the config loader refuses anything more permissive.

## 2. Interfaces / Responsibilities

### 2.1 Allowlist (`app/security.py`)

```python
@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    user_id: int | None
    reason: str = ""

def check(telegram: TelegramConfig, user_id: int | None) -> AuthDecision
def unauthorized_message(user_id: int | None) -> str
```

`check` is a pure function and the only place the allowlist is
consulted. The bot middleware calls it on every command (except
`/whoami`); the callback handler calls it again as defence in depth.

### 2.2 Confirmation (`app/confirmations.py`)

```python
@dataclass(frozen=True)
class PendingAction:
    token: str
    user_id: int
    profile: str
    instance_id: str
    instance_name: str
    action: str
    expires_at: float

class ConfirmationStore:
    def __init__(self, ttl_sec: int) -> None
    async def create(...) -> PendingAction
    async def take(token: str, user_id: int) -> PendingAction | None
    async def cancel(token: str, user_id: int) -> PendingAction | None
    async def size() -> int
```

Invariants:

- `take` and `cancel` only return a value when both the token is known
  *and* `user_id` matches the original requester.
- A successful `take` removes the entry; the token cannot be reused.
- Expired entries are reaped lazily on the next `create` / `take` /
  `cancel` / `size`.
- Tokens come from `secrets.token_urlsafe(16)` — 128 bits of entropy.

### 2.3 OCID masking (`app/security.py`)

```python
OCID_RE = re.compile(r"^ocid1\.[a-z0-9]+\.[a-z0-9-]*\.[a-z0-9-]*\.[a-z0-9]+$")

def mask_ocid(ocid: str, *, suffix: int = 8) -> str
def mask_fingerprint(fp: str) -> str
```

`mask_ocid` returns `ocid1.<kind>...<last8>` on a real OCID, and the
input unchanged otherwise (so the caller can pass any string through
without crashing on non-OCID values).

### 2.4 Audit log (`app/audit.py`)

```python
class AuditLogger:
    def __init__(self, path) -> None
    async def record(*, user_id, username, command, profile=None,
                     target=None, result="ok", error=None, extra=None) -> None
```

Every record is a single JSON line. An `asyncio.Lock` serialises writes
to prevent two concurrent commands from interleaving partial JSON. The
parent directory is created at constructor time.

Required fields per record: `ts` (ISO 8601 UTC, "Z" suffix), `user_id`,
`username`, `cmd`, `result`. Optional: `profile`, `target`, `error`,
plus any `extra` keys merged at the top level.

## 3. Code Mapping

| Concern                  | Location                                                     |
| ------------------------ | ------------------------------------------------------------ |
| Allowlist                | [`app/security.py::check`](../../app/security.py)            |
| OCID masking             | [`app/security.py::mask_ocid`](../../app/security.py)        |
| Confirmation store       | [`app/confirmations.py`](../../app/confirmations.py)         |
| Audit logger             | [`app/audit.py`](../../app/audit.py)                         |
| Audit/reply helpers      | [`app/commands/__init__.py`](../../app/commands/__init__.py) |
| Allowlist middleware     | [`app/bot.py::_authorize`](../../app/bot.py)                 |
| Callback re-check        | [`app/commands/operations.py::_callback`](../../app/commands/operations.py) |

## 4. Tradeoffs

- **In-memory confirmation store.** Persisting tokens across restarts
  would let an operator finish a confirmation interrupted by a deploy,
  but the safer failure mode is to cancel everything: a token created
  before a restart could otherwise be confirmed against a different
  binary build. The store is small enough that the trade-off is local
  to this module and does not need a project-level tradeoff entry.
- **No rate limiting per user.** The allowlist is small and a single
  allowlisted user can be trusted; spam is a non-issue. Adding rate
  limiting later is a localized change.
- **`/whoami` bypasses the allowlist by design.** Without it, an
  operator added to the bot cannot discover their own Telegram id to
  request access. This is explicitly documented in
  [`app/commands/basic.py`](../../app/commands/basic.py).

## 5. Verification

- Allowlist: [`tests/test_security.py`](../../tests/test_security.py).
- Confirmation store invariants:
  [`tests/test_confirmations.py`](../../tests/test_confirmations.py)
  covers happy path, wrong user, unknown token, expiry, concurrent
  uniqueness, invalid TTL.
- Confirmation flow end-to-end:
  [`tests/test_commands_operations.py`](../../tests/test_commands_operations.py)
  covers stop/reboot inline-button flow, user mismatch, allowlist
  denial at callback time, audit emission.
- Audit log JSONL integrity:
  [`tests/test_audit.py`](../../tests/test_audit.py) verifies
  serialisation, concurrent write atomicity, and parent-directory
  creation.
- OCID masking: the regex is exercised by `tests/test_security.py` and
  every command test that asserts the absence of a full OCID in user
  output.
