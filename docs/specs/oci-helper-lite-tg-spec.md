下面这份可以直接作为 `docs/oci-helper-lite-tg-spec.md` 或交给 Codex/Claude Code 的实现规格。

# oci-helper-lite-tg Spec v0.1

## 1. 目标

将现有 `oci-helper` fork 改写为轻量版服务，只保留 **Telegram Bot 管理 Oracle Cloud 实例**的核心功能。

当前部署链路保持不变：

```text
公网: http://<server-ip>:8088/
        ↓
Nginx listen 8088
        ↓
127.0.0.1:8818  lightweight oci-helper-tg service
```

现有目录保持：

```text
~/oci-helper
├── docker-compose.yml
├── application.yml / config.yml
├── keys/
├── logs/
└── data/
```

目标是替换 Java Spring Boot Web 面板，降低常驻内存占用。

当前观察：

```text
oci-helper Java 容器 idle RSS ≈ 203 MiB
其他容器普遍 3–30 MiB
```

轻量版目标：

```text
Python prototype: idle RSS <= 80–120 MiB
Go rewrite target: idle RSS <= 30–60 MiB
CPU idle <= 1%
不依赖前端 Web UI
不依赖 Spring Boot / Tomcat
```

---

## 2. 非目标

明确不做：

```text
1. 不保留 Vue 前端 Web 管理界面
2. 不保留 Java Spring Boot 后端
3. 不保留 watcher 自动更新容器
4. 不保留 websockify / noVNC，除非后续单独启用
5. 不实现抢机复杂策略
6. 不实现多用户权限系统，只支持 allowlist Telegram ID
7. 不支持任意 shell 命令执行
8. 不支持删除实例、删除卷、删除 VCN 等高风险操作
```

高风险功能默认不做：

```text
delete instance
delete boot volume
delete VCN/subnet/security list
mass open all ports
arbitrary command execution
```

---

## 3. 推荐技术路线

### Phase 1：Python 快速轻量版

优先实现，改动快，验证快。

依赖：

```text
python-telegram-bot
oci
PyYAML
aiohttp 或 fastapi 可选，仅用于 health endpoint
```

建议 Python 版本：

```text
Python 3.11 / 3.12 slim
```

目录结构：

```text
oci-helper-lite/
├── app/
│   ├── main.py
│   ├── bot.py
│   ├── config.py
│   ├── oci_client.py
│   ├── commands/
│   │   ├── instances.py
│   │   ├── quota.py
│   │   ├── network.py
│   │   └── health.py
│   ├── security.py
│   ├── formatters.py
│   └── audit.py
├── config.example.yml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

### Phase 2：Go 低内存版

如果 Python + OCI SDK 仍觉得重，再迁移 Go。

Go 版目标：

```text
单 binary
官方 OCI Go SDK
内存更低
部署更干净
```

但 Phase 1 不要直接上 Go，除非明确要追求极限内存。

---

## 4. 功能范围

### 4.1 Telegram Bot 基础命令

必须实现：

```text
/start
/help
/status
/ping
/whoami
```

行为：

```text
/start     显示菜单和当前用户 ID
/help      显示命令列表
/status    显示服务状态、已加载 OCI profile、当前区域
/ping      返回 pong + latency
/whoami    返回 Telegram user_id，用于配置 allowlist
```

---

### 4.2 OCI 配置管理

配置通过 YAML 文件，不做 Web 表单。

配置文件：

```text
/app/oci-helper/config.yml
```

示例：

```yaml
server:
  host: "0.0.0.0"
  port: 8818

telegram:
  bot_token: "123456789:xxxx"
  allowed_user_ids:
    - 123456789

oci:
  default_profile: "oracle-sydney"
  profiles:
    oracle-sydney:
      tenancy: "ocid1.tenancy.oc1..xxxx"
      user: "ocid1.user.oc1..xxxx"
      fingerprint: "aa:bb:cc:dd:..."
      region: "ap-sydney-1"
      key_file: "/app/oci-helper/keys/oci_api_key.pem"
      compartment_id: "ocid1.compartment.oc1..xxxx"

    oracle-ashburn:
      tenancy: "ocid1.tenancy.oc1..xxxx"
      user: "ocid1.user.oc1..xxxx"
      fingerprint: "aa:bb:cc:dd:..."
      region: "us-ashburn-1"
      key_file: "/app/oci-helper/keys/oci_api_key.pem"
      compartment_id: "ocid1.compartment.oc1..xxxx"

runtime:
  default_page_size: 20
  command_timeout_sec: 30
  confirmation_ttl_sec: 60
  audit_log: "/app/oci-helper/logs/audit.log"
```

要求：

```text
1. 不把 private key 内容写进 YAML
2. key_file 使用容器内路径
3. 启动时校验 key_file 存在且权限合理
4. 支持多个 OCI profile
5. 支持默认 profile
```

---

### 4.3 实例查询命令

必须实现：

```text
/instances
/instances <profile>
/instance <instance_ocid_or_name>
```

`/instances` 输出：

```text
Profile: oracle-sydney
Region: ap-sydney-1

1. instance-20260331-2201
   State: RUNNING
   Shape: VM.Standard.A1.Flex
   OCPU: 1
   Memory: 6 GB
   Public IP: 192.9.181.26
   AD: xxxx
```

要求：

```text
1. 默认只显示 compartment 下实例
2. 支持按 profile 查询
3. 如果实例过多，分页显示
4. Telegram 消息长度超过限制时自动拆分
5. 不暴露完整 OCID，默认只显示短 ID 或 name
```

---

### 4.4 实例操作命令

必须实现：

```text
/start_instance <instance_name_or_short_id>
/stop_instance <instance_name_or_short_id>
/reboot_instance <instance_name_or_short_id>
```

安全要求：

```text
1. start 可以直接执行
2. stop/reboot 必须二次确认
3. 二次确认使用 Telegram inline button
4. 确认 token 60 秒过期
5. 每次操作写 audit log
```

交互例子：

```text
User:
/stop_instance instance-20260331-2201

Bot:
Confirm STOP instance?
Name: instance-20260331-2201
Region: ap-sydney-1

[Confirm Stop] [Cancel]
```

禁止实现：

```text
/delete_instance
/delete_volume
```

---

### 4.5 公网 IP 查询

必须实现：

```text
/public_ip
/public_ip <instance_name_or_short_id>
```

输出：

```text
Instance: instance-20260331-2201
State: RUNNING
Public IP: 192.9.181.26
Private IP: 10.0.0.x
Subnet: xxx
VNIC: xxx
```

可选：

```text
/refresh_ip_info
```

只查询，不主动换 IP。

---

### 4.6 配额查询

建议实现：

```text
/quota
/quota <profile>
```

输出核心资源：

```text
Region: ap-sydney-1

Compute:
- OCPU used / limit
- Memory used / limit
- Instance count

Network:
- Public IP count
- VNIC count

Block Volume:
- Boot volume count
- Volume size
```

Phase 1 可以只实现最常用资源，缺失项返回：

```text
Not implemented in lite version.
```

---

### 4.7 安全列表查询

只读实现：

```text
/security_lists
/security_list <name_or_short_id>
```

输出入站规则：

```text
Ingress:
- TCP 22 from 0.0.0.0/0
- TCP 80 from 0.0.0.0/0
- TCP 443 from 0.0.0.0/0
- TCP 8088 from x.x.x.x/32
```

Phase 1 不实现修改安全组。

可选 Phase 2：

```text
/allow_port <port> <cidr>
/deny_port <port> <cidr>
```

但必须二次确认。

---

## 5. Web / Health Endpoint

虽然不保留 Web UI，但保留 `8818` 端口，方便现有 Nginx 不改。

必须提供：

```text
GET /
GET /healthz
GET /version
```

`GET /` 返回纯文本或简单 HTML：

```text
oci-helper-lite-tg is running.
Telegram bot: enabled
Version: 0.1.0
```

`GET /healthz` 返回：

```json
{
  "status": "ok",
  "telegram": "running",
  "profiles_loaded": 2
}
```

这样现有 Nginx 8088 可以继续：

```nginx
location / {
    proxy_pass http://127.0.0.1:8818;
}
```

---

## 6. Docker 部署规格

### Dockerfile

Python prototype：

```dockerfile
FROM python:3.12-slim

WORKDIR /app/oci-helper

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8818

CMD ["python", "-m", "app.main"]
```

`requirements.txt`：

```text
python-telegram-bot>=21
oci
PyYAML
aiohttp
```

---

### docker-compose.yml

保留你现在的路径和端口习惯：

```yaml
services:
  oci-helper:
    build: .
    container_name: oci-helper
    restart: always
    ports:
      - "127.0.0.1:8818:8818"
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - /home/ubuntu/oci-helper/config.yml:/app/oci-helper/config.yml:ro
      - /home/ubuntu/oci-helper/keys:/app/oci-helper/keys:ro
      - /home/ubuntu/oci-helper/logs:/app/oci-helper/logs
      - /home/ubuntu/oci-helper/data:/app/oci-helper/data
    mem_limit: 256m
```

不再默认启动：

```text
watcher
websockify
frontend
```

如果未来需要 VNC，单独恢复 `websockify`，但不是 lite-tg 核心功能。

---

## 7. Nginx 保持现状

你现在的 80 端口服务不动：

```text
/em-agent/
/splayer/
/label-studio/
/upload/
```

oci-helper-lite 继续走独立端口：

```nginx
server {
    listen 8088;
    listen [::]:8088;
    server_name _;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8818;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

注意：

```text
1. 不再使用 /oci-helper/ 子路径
2. 不再需要 /js/ /css/ 补丁
3. 不污染 80 端口已有服务
4. 8088 继续由 iptables + OCI 安全组控制
```

---

## 8. 安全要求

### 8.1 Telegram allowlist

所有命令必须先检查：

```text
telegram.user_id in allowed_user_ids
```

未授权用户返回：

```text
Unauthorized.
Your Telegram ID: <id>
```

并记录日志。

---

### 8.2 敏感信息屏蔽

禁止在 Telegram 消息里输出：

```text
private key
完整 fingerprint 可选屏蔽
完整 tenancy OCID
完整 user OCID
完整 compartment OCID
```

显示时只展示：

```text
ocid1.instance...abcd1234
```

---

### 8.3 操作确认

必须二次确认：

```text
stop instance
reboot instance
modify security rule
change public IP
```

不需要确认：

```text
list
status
quota
public_ip
start instance
```

`start instance` 风险较低，但也可以配置为需要确认。

---

### 8.4 审计日志

每个命令写入：

```text
timestamp
telegram_user_id
username
command
profile
target_resource
result
error_message
```

日志文件：

```text
/app/oci-helper/logs/audit.log
```

格式：

```json
{"ts":"2026-05-23T20:00:00Z","user_id":123456,"cmd":"/instances","result":"ok"}
```

---

## 9. 错误处理

错误分类：

```text
ConfigError
AuthError
PermissionError
OciApiError
ResourceNotFound
AmbiguousResource
CommandTimeout
TelegramSendError
```

行为：

```text
1. 用户看到简短错误
2. 详细 traceback 只进日志
3. OCI API 错误要显示 request id，如果有
4. 找不到实例时提示当前 profile 和 region
5. 名称匹配多个实例时列出候选项，不自动选择
```

例子：

```text
Instance not found.

Profile: oracle-sydney
Region: ap-sydney-1
Query: test-vm

Use /instances to list available instances.
```

---

## 10. 资源匹配规则

用户输入可以是：

```text
完整 OCID
实例 display_name
短 ID
```

匹配优先级：

```text
1. 完整 OCID 精确匹配
2. display_name 精确匹配
3. display_name 前缀匹配
4. OCID 后 8–12 位匹配
```

如果多个匹配：

```text
Ambiguous instance name.
1. xxx
2. xxx
Please use full name or short id.
```

---

## 11. 验收标准

### 11.1 部署验收

```bash
docker compose up -d
docker ps
curl -s http://127.0.0.1:8818/healthz
curl -s http://127.0.0.1:8088/healthz
```

期望：

```text
HTTP 200
status=ok
```

---

### 11.2 内存验收

```bash
docker stats --no-stream
```

Python prototype：

```text
oci-helper <= 120 MiB idle
```

如果超过：

```text
1. 检查是否引入 FastAPI/Uvicorn 多 worker
2. 检查是否缓存了大对象
3. 检查 OCI client 是否重复初始化
4. 考虑迁移 Go
```

---

### 11.3 Bot 验收

Telegram 测试：

```text
/start
/whoami
/status
/instances
/public_ip
/quota
```

实例操作测试：

```text
/start_instance <stopped-instance>
/reboot_instance <running-instance>
```

stop 测试必须出现确认按钮：

```text
/stop_instance <instance>
```

---

### 11.4 安全验收

用非 allowlist Telegram 账号测试：

```text
/start
/instances
```

期望：

```text
Unauthorized.
Your Telegram ID: xxx
```

审计日志有记录。

---

## 12. 迁移计划

### Step 1：保留现有服务备份

```bash
cd ~/oci-helper
cp docker-compose.yml docker-compose.yml.java-backup
cp application.yml application.yml.java-backup
```

保留原始 Java 容器镜像，不立即删除。

---

### Step 2：新增 lite 配置

```bash
mkdir -p ~/oci-helper/logs ~/oci-helper/data ~/oci-helper/keys
nano ~/oci-helper/config.yml
```

把原来 Oracle API key 继续放在：

```text
~/oci-helper/keys/
```

容器内路径继续是：

```text
/app/oci-helper/keys/
```

---

### Step 3：替换 compose

停止旧服务：

```bash
cd ~/oci-helper
docker compose down
```

启动 lite：

```bash
docker compose up -d --build
```

---

### Step 4：验证

```bash
curl -s http://127.0.0.1:8818/healthz
curl -s http://127.0.0.1:8088/healthz
docker stats --no-stream
docker logs -f oci-helper
```

---

### Step 5：Telegram 验证

```text
/whoami
/status
/instances
```

确认实例列表正确后，再启用实例操作命令。

---

## 13. 实现优先级

### P0：必须

```text
config.yml 加载
Telegram bot 启动
allowed_user_ids 权限检查
OCI profile 加载
/healthz
/status
/whoami
/instances
/public_ip
audit log
Dockerfile
docker-compose.yml
```

### P1：应该

```text
/start_instance
/stop_instance + confirmation
/reboot_instance + confirmation
/quota
多 profile 支持
错误分类
消息分页
```

### P2：可选

```text
/security_lists 只读
/boot_volumes 只读
/regions
按钮式菜单
定时状态通知
低内存 Go 重写
```

### 不做

```text
Web UI
抢机任务
自动换 IP
删除资源
一键开放全部端口
Cloudflare 配置
地图数据
备份恢复 UI
```

---

## 14. 推荐最终运行状态

你的机器上保留：

```text
em-agent-frontend
em-agent-backend
filegator
label-studio
splayer-api
oci-helper-lite-tg
nginx
```

移除或停用：

```text
oci-helper-watcher
oci-helper-websockify
Java oci-helper
```

预期资源：

```text
oci-helper-lite-tg: 50–120 MiB
Nginx: 很低
无前端资源 404 问题
无 /oci-helper 子路径问题
无需暴露 8818 公网
```

---

## 15. 给实现 Agent 的一句话任务

```text
Rewrite this fork as a lightweight Telegram-only OCI management daemon. Remove the Spring Boot web UI and watcher/websockify dependencies. Preserve the existing deployment topology: Docker container listens on 127.0.0.1:8818 and Nginx exposes port 8088. Configuration must be YAML-based, OCI API keys must be mounted from /app/oci-helper/keys, and all Telegram commands must be restricted by allowed_user_ids. Implement read-only instance listing, public IP query, status, health check, audit logging, and safe start/stop/reboot instance operations with confirmation buttons. Target idle memory below 120 MiB for the Python prototype.
```

这版 spec 的核心原则：**不要在原 Java 项目里“删功能瘦身”，而是保留部署外壳，重写成一个 Telegram-only OCI daemon。**
