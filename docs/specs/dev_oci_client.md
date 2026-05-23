# dev_oci_client — OCI SDK wrapper

## 1. Goals & Boundaries

### Goals

- Centralize every OCI SDK call into one async-friendly module.
- Maintain one set of SDK clients per configured profile, constructed
  at startup, so command handlers do not pay client-init latency on
  every call.
- Normalize OCI service errors into a single `OciApiError` that carries
  HTTP status, OCI error code, and `opc-request-id` for support.

### Boundaries

- The wrapper does **not** decide policy (allowlist, confirmation,
  formatting). It exposes thin async methods that mirror the SDK shape.
- The wrapper does not retry. OCI SDK retries are off by default and
  staying off keeps the user-visible latency predictable.
- The wrapper does not paginate to the caller; it returns the fully
  materialized list when the call is paginated (current resource sizes
  for the target use case fit easily in memory).

## 2. Interfaces / Responsibilities

### 2.1 Construction

`OciClient(oci_section)` validates every configured profile with
`oci.config.validate_config` and constructs the following SDK clients
per profile:

| Client                              | Used by                                          |
| ----------------------------------- | ------------------------------------------------ |
| `oci.core.ComputeClient`            | `list_instances`, `instance_action`              |
| `oci.core.VirtualNetworkClient`     | `get_ip_info`, `list_security_lists`, `get_security_list` |
| `oci.core.BlockstorageClient`       | `list_boot_volumes`                              |
| `oci.identity.IdentityClient`       | `list_availability_domains`                      |
| `oci.limits.LimitsClient`           | `list_limit_values`                              |

A small per-bundle cache stores availability-domain listings; ADs are
static at runtime.

### 2.2 Async surface

Every public method is an `async def` whose body wraps the blocking SDK
call in `asyncio.to_thread`:

```python
async def list_instances(profile: str | None = None) -> list[Any]: ...
async def get_instance(instance_id: str, profile: str | None = None) -> Any: ...
async def instance_action(instance_id: str, action: str, profile: str | None = None) -> Any: ...
async def get_ip_info(instance: Any, profile: str | None = None) -> IpRow: ...
async def list_security_lists(profile: str | None = None) -> list[Any]: ...
async def get_security_list(sl_id: str, profile: str | None = None) -> Any: ...
async def list_boot_volumes(profile: str | None = None) -> list[Any]: ...
async def list_availability_domains(profile: str | None = None) -> list[Any]: ...
async def list_limit_values(service_name: str, profile: str | None = None) -> list[Any]: ...
```

`instance_action` only accepts values in `INSTANCE_ACTIONS = {START,
STOP, SOFTSTOP, RESET, SOFTRESET}` and raises `ValueError` otherwise;
this is the boundary that prevents a misbehaving command module from
issuing an unintended action.

### 2.3 Error normalization

Any `oci.exceptions.ServiceError` raised by an SDK call is caught and
re-raised as `OciApiError(message, status=..., code=..., request_id=...)`.
The user-facing rendering is provided by `OciApiError.user_message()`,
which is what command modules emit when they catch the exception at
their boundary.

## 3. Code Mapping

| Concern                         | Location                                       |
| ------------------------------- | ---------------------------------------------- |
| All of the above                | [`app/oci_client.py`](../../app/oci_client.py) |
| Action whitelist constant       | `INSTANCE_ACTIONS` in the same file            |
| `IpRow` (formatter contract)    | [`app/formatters.py`](../../app/formatters.py) |

## 4. Tradeoffs

- **Sync SDK over async REST.** The official `oci` SDK is sync-only.
  Wrapping it in `to_thread` is one extra context switch per call but
  preserves correct request signing and retry behavior. Rolling our own
  async REST client with manual RFC 7616-style signing was rejected as
  the largest single source of risk we could introduce.
- **One client bundle per profile, eagerly constructed.** Lazy
  construction would save ~10–20 MB if profiles are unused, but it
  introduces a "first call is slow" gotcha that would surface in
  Telegram latency. The eager cost is acceptable inside our 120 MiB
  budget.
- See project-level [T-001](../tradeoffs.md#t-001--default-to-graceful-softstop--softreset)
  for the choice of `SOFTSTOP` / `SOFTRESET` as the default for
  `/stop_instance` and `/reboot_instance`.

## 5. Verification

- Every command module is tested against
  [`tests/fakes/oci_fake.py`](../../tests/fakes/oci_fake.py), which
  implements the same async surface in-memory. The real
  `OciClient` is never instantiated in the unit tests; its construction
  is exercised at import time and at startup.
- `OciApiError` formatting is exercised indirectly by the command
  failure tests (`OciApiError` is raised by the fake when it cannot
  resolve a profile, and command tests assert the user-visible message).
- Real OCI is only exercised in the manual acceptance run described in
  [`integration_acceptance.md`](integration_acceptance.md).
