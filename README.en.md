<p align="right">
   <a href="./README.md">中文</a> | <strong>English</strong>
</p>

# light_oci_manager

A lightweight Telegram-only daemon for managing Oracle Cloud (OCI) compute
instances.

The whole service is a single Python container with an idle RSS target of
≤ 120 MiB. It binds one port (`127.0.0.1:8818`) for the local Nginx to
proxy. No web UI, no database, no IP-snipe loop, no destructive commands.

See [`docs/specs/`](docs/specs/) for the formal specification.

## Features

P0 (must)

- `/start` `/help` `/status` `/ping` `/whoami`
- `/instances` `/instance` — list / inspect instances
- `/public_ip` — public / private IPs
- HTTP `/healthz` and `/version`

P1 (should)

- `/start_instance` — runs immediately
- `/stop_instance` `/reboot_instance` — Telegram inline-button confirmation
  (defaults to OCI `SOFTSTOP` / `SOFTRESET`)
- `/quota` — local compute usage + compute / vcn / block-storage limits

P2 (delivered)

- `/security_lists` `/security_list` — read-only ingress rules
- `/boot_volumes` — aggregated across availability domains
- `/regions` — configured profile regions

**Out of scope**: web UI, resource deletion, automatic IP rotation,
instance sniping, "open all ports" buttons, Cloudflare configuration. Full
non-goal list in
[`docs/specs/00_overview.md`](docs/specs/00_overview.md).

## Security model

- `telegram.allowed_user_ids` allowlist; unauthorized callers are rejected
  and logged.
- `/stop_instance` and `/reboot_instance` require a Telegram inline-button
  confirmation. Each token has a 60 s TTL and is bound to the requesting
  Telegram user.
- Full OCIDs are masked in every user-facing message.
- Audit records are written as JSONL to
  `/app/oci-helper/logs/audit.log`.

## Quick start

### 1. Prepare configuration

```bash
mkdir -p ~/light-oci/keys ~/light-oci/logs ~/light-oci/data
cp config.example.yml ~/light-oci/config.yml
chmod 600 ~/light-oci/config.yml
cp /path/to/oci_api_key.pem ~/light-oci/keys/
chmod 600 ~/light-oci/keys/oci_api_key.pem
```

Required fields in `config.yml`:

- `telegram.bot_token` — token from BotFather
- `telegram.allowed_user_ids` — list of Telegram user IDs (use `/whoami`
  to discover your own)
- `oci.profiles.<name>` — at least one OCI credential profile

### 2. Use the prebuilt image (recommended)

GitHub Actions automatically builds and publishes `linux/amd64` +
`linux/arm64` images to GitHub Container Registry on every push to `main`
and on every release tag:

```bash
docker pull ghcr.io/4everwz/light_oci_manager:latest
```

Run it:

```bash
HOST_OCI_HELPER_DIR=$HOME/light-oci docker compose up -d
```

To use the prebuilt image instead of building locally, replace the
`build:` line in `docker-compose.yml` with:

```yaml
    image: ghcr.io/4everwz/light_oci_manager:latest
```

### 3. Build locally

```bash
docker compose up -d --build
```

### 4. Verify

```bash
curl -s http://127.0.0.1:8818/healthz
# {"status":"ok","telegram":"running","profiles_loaded":N}
```

Then DM the bot `/whoami`, `/status`, `/instances`.

### 5. Nginx reverse proxy

```nginx
server {
    listen 8088;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:8818;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
```

## Development

```bash
uv sync               # create .venv and install deps
uv run pytest -q      # 92 unit / behaviour tests
uv run ruff check     # lint
```

The test suite does not touch real OCI or Telegram — every external
dependency is replaced by an in-memory fake in
[tests/fakes/](tests/fakes/).

## Docs

- [`docs/specs/00_overview.md`](docs/specs/00_overview.md) — project
  purpose, scope, non-goals, success criteria
- [`docs/specs/dev_*.md`](docs/specs/) — per-component leaf docs
- [`docs/specs/integration_acceptance.md`](docs/specs/integration_acceptance.md)
  — end-to-end acceptance checklist
- [`docs/design/architecture.md`](docs/design/architecture.md) — process
  model, module boundaries, concurrency, failure model
- [`docs/matrix_implementation.md`](docs/matrix_implementation.md) — spec
  → implementation mapping
- [`docs/tradeoffs.md`](docs/tradeoffs.md) — project-level deviations

## License

Apache License 2.0. See [LICENSE](LICENSE).
