<p align="right">
   <strong>中文</strong> | <a href="./README.en.md">English</a>
</p>

# light_oci_manager

通过 Telegram Bot 管理 Oracle Cloud (OCI) 实例的轻量服务。

整个进程是一个 Python 容器，常驻内存目标 ≤ 120 MiB，对外只暴露一个端口
(`127.0.0.1:8818`) 给本机 Nginx 反代。没有 Web UI、没有数据库、没有抢机
逻辑、没有删除资源的命令。

详细规格见 [`docs/specs/`](docs/specs/)。

## 功能

P0（必须）

- `/start` `/help` `/status` `/ping` `/whoami`
- `/instances` `/instance` —— 列出 / 查看实例
- `/public_ip` —— 公网 / 私网 IP
- `/healthz`、`/version` —— HTTP 健康检查

P1（应该）

- `/start_instance` —— 立即开机
- `/stop_instance` `/reboot_instance` —— Telegram inline 按钮二次确认
  (默认走 OCI `SOFTSTOP` / `SOFTRESET`)
- `/quota` —— 实例用量 + compute / vcn / block-storage 限额

P2（已交付的）

- `/security_lists` `/security_list` —— 只读
- `/boot_volumes` —— 跨可用域聚合
- `/regions` —— 列出已配置 profile 的区域

**不做**：Web UI、删除资源、自动换 IP、抢机、一键开放全部端口、
Cloudflare 配置。完整非目标列表见
[`docs/specs/00_overview.md`](docs/specs/00_overview.md)。

## 安全模型

- `telegram.allowed_user_ids` 白名单；未授权用户被拒并写入审计日志。
- `/stop_instance` / `/reboot_instance` 走 inline 按钮 + 60 秒 TTL 的
  one-shot token，且 token 绑定发起人 user_id。
- 全 OCID 输出前自动掩码（前缀 + 后 8 位）。
- 审计日志 JSONL 格式追加写入 `/app/oci-helper/logs/audit.log`。

## 快速开始

### 1. 准备配置

复制示例并填实际值：

```bash
mkdir -p ~/light-oci/keys ~/light-oci/logs ~/light-oci/data
cp config.example.yml ~/light-oci/config.yml
chmod 600 ~/light-oci/config.yml
# 把 OCI API private key 放入：
cp /path/to/oci_api_key.pem ~/light-oci/keys/
chmod 600 ~/light-oci/keys/oci_api_key.pem
```

`config.yml` 必填：

- `telegram.bot_token` —— BotFather 发的 token
- `telegram.allowed_user_ids` —— Telegram 用户 ID 列表
  （先用 `/whoami` 自查）
- `oci.profiles.<name>` —— 至少一个 OCI 凭证 profile

### 2. 用预构建镜像（推荐）

GitHub Actions 在 `main` 分支或 release tag 推送时自动构建 `linux/amd64`
+ `linux/arm64` 多架构镜像并发布到 GitHub Container Registry：

```bash
docker pull ghcr.io/4everwz/light_oci_manager:latest
```

启动：

```bash
HOST_OCI_HELPER_DIR=$HOME/light-oci docker compose up -d
```

`docker-compose.yml` 默认 `build:` 本地源码。要直接用预构建镜像，把
`build:` 行替换为：

```yaml
    image: ghcr.io/4everwz/light_oci_manager:latest
```

### 3. 本地构建

```bash
docker compose up -d --build
```

### 4. 验证

```bash
curl -s http://127.0.0.1:8818/healthz
# {"status":"ok","telegram":"running","profiles_loaded":N}
```

然后在 Telegram 给 bot 发 `/whoami`、`/status`、`/instances`。

### 5. Nginx 反代（保持原有端口约定）

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

## 开发

```bash
uv sync               # 创建 .venv 并装依赖
uv run pytest -q      # 92 个单元 / 行为测试
uv run ruff check     # 代码风格
```

测试不打真实 OCI / Telegram —— 所有外部依赖通过
[tests/fakes/](tests/fakes/) 内的 in-memory 替身注入。

## 文档

- [`docs/specs/00_overview.md`](docs/specs/00_overview.md) ——
  项目目的、范围、非目标、成功标准
- [`docs/specs/dev_*.md`](docs/specs/) —— 各组件 leaf docs
- [`docs/specs/integration_acceptance.md`](docs/specs/integration_acceptance.md)
  —— 端到端验收清单
- [`docs/design/architecture.md`](docs/design/architecture.md) ——
  进程模型、模块边界、并发与失败模型
- [`docs/matrix_implementation.md`](docs/matrix_implementation.md) ——
  规格 → 实现 映射
- [`docs/tradeoffs.md`](docs/tradeoffs.md) —— 项目级偏差记录

## License

Apache License 2.0. See [LICENSE](LICENSE).
