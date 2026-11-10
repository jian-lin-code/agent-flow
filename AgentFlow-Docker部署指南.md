# AgentFlow Docker 部署指南

> 适用版本：当前仓库（`agent-flow-server` + `agent-flow-admin`）
> 部署方式：单机 Docker Compose（API + 3 个 Worker + PostgreSQL + Redis + MinIO + Nginx）
> 文档性质：部署方案与操作手册，**本文不代替实际执行**。所有路径以仓库根目录 `agent-flow/` 为基准。

---

## 一、服务器配置推荐

### 1.1 结论先行

| 场景 | 规格 | 适用规模 | 说明 |
| --- | --- | --- | --- |
| 内部试用 / POC | **4 核 8G**，100G SSD，5Mbps | ≤ 30 人，日对话 ≤ 300 轮 | 全套容器单机跑，够用但无冗余 |
| **正式生产（推荐首版）** | **8 核 16G**，200G SSD，10~20Mbps | 100~300 人，日对话 2000~3000 轮，同时在线对话 10~20 | 单机 Compose 全套，预留了 PG / MinIO / 解析峰值内存 |
| 规模化 / 多部门 | **16 核 32G** + 200G SSD，PG 独立 4C8G、Redis 独立 | 日对话 5000 轮以上 | Worker 水平扩容，数据库与对象存储独立 |

**推荐首版直接上 8C16G。** 4C8G 能跑，但知识库解析大 PDF 时（rag-worker）内存峰值会顶到 1~1.5G，连同 PostgreSQL、MinIO、3 个 Worker 一起容易触发 OOM Kill，表现为"文档一直 indexing""消息突然中断"。

### 1.2 为什么不需要 GPU

本项目的模型能力**全部走外部 API**，服务器只做编排：

| 能力 | 实际调用方 | 是否占本机算力 |
| --- | --- | --- |
| 对话 / 意图 / 抽取 | 阿里云 DashScope（`qwen-plus-latest`、`qwen3.7-plus`） | 否 |
| 图片理解（发票、文档配图） | DashScope `qwen3-vl-plus` | 否 |
| 向量化 | DashScope `text-embedding-v4`（1024 维） | 否 |
| 重排序 | 独立 rerank 服务（`qwen3.7-text-rerank`） | 否 |
| PDF 转 Markdown | MinerU 云端 API | 否 |

所以：**不需要 GPU 实例，也不需要本地磁盘模型权重。** 瓶颈在 CPU 调度、内存和外部 API 配额（RPM/TPM），不在算力。

### 1.3 各组件资源画像（估算，基于本机实测）

本机实测：单个 Python 进程（已加载 langchain / langgraph）常驻内存 **130~160MB**。

| 组件 | 常驻内存 | 峰值内存 | CPU | 说明 |
| --- | --- | --- | --- | --- |
| `api`（uvicorn 单进程） | 250~350MB | 500MB | 0.2~0.5 核 | 主要做鉴权、CRUD、SSE 转发 |
| `chat-worker`（max_jobs=4） | 300~400MB | 600~900MB | 0.5~1.5 核 | 一次对话 5~15s，并发 4 路 LLM 流 |
| `rag-worker`（max_jobs=4） | 350~500MB | **1~1.5GB** | 1~2 核 | 解析 PDF/docx、分块、批量向量化 |
| `review-worker`（max_jobs=2） | 300~400MB | 600MB | 0.3~0.8 核 | 报销单 AI 初审 |
| `postgres`（pgvector） | 300~500MB | 1~2GB | 0.5~1 核 | 随数据量增长，`shared_buffers` 可调 |
| `redis` | 50~150MB | 300MB | < 0.2 核 | 队列 + 缓存，数据量小 |
| `minio` | 150~250MB | 500MB | 0.2 核 | 文件上传下载 |
| `web`（nginx） | 20~30MB | 50MB | < 0.1 核 | 静态资源 + 反向代理 |
| **合计** | **约 2~2.5GB** | **约 5~6GB** | **3~5 核** | 8C16G 有充足余量 |

### 1.4 其他硬指标

| 项目 | 建议 | 原因 |
| --- | --- | --- |
| 磁盘 | SSD，≥ 100G（生产 200G） | 后端镜像约 1.2~1.5G，前端镜像约 300M；会话消息与 `document_chunks` 增长较快；MinIO 存原始文件 |
| 带宽 | 出网 ≥ 5Mbps，建议 10~20Mbps | 上传发票/文档是主要流量；LLM 走外网，需稳定出口 |
| 地域 | 与 DashScope 同地域（华东上海 / 华北北京） | LLM 调用占比高，就近访问可降低 RTT（收益有限但无成本） |
| 操作系统 | Ubuntu 22.04 / 24.04 LTS，x86_64 | 官方 Docker 支持最好；ARM 也能跑但部分 wheel 需编译 |
| Swap | 4G（`vm.swappiness=10`） | 兜底防 OOM，不作为常规内存使用 |
| 外网访问 | 必须能访问 DashScope、MinerU、rerank、Jev/OpenRouter 域名 | 任一不通会导致对应意图直接失败 |

> 若公司网络有出口白名单，请提前放行：`dashscope.aliyuncs.com`、`mineru.net`、rerank 的 MaaS 域名、`openrouter.ai`（或 `jevmodel.org`）。

### 1.5 2核2G 的小机器能跑吗（如 Flexus L 实例：2C2G/40G/2Mbps/100G 流量）

**能跑，但属于压线配置，必须做下面的减配调整。** 个人使用（1~5 人）时同时只有 1 个对话/解析任务在跑，Worker 的 `max_jobs=4` 只是上限不会真用满，实际内存占用比 1.3 节的估算低不少：

| 组件 | 个人使用实际占用 |
| --- | --- |
| api | ~300MB |
| chat-worker（单任务） | ~300MB |
| rag-worker（解析时瞬时） | ~500MB |
| review-worker（单任务） | ~300MB |
| postgres（调参后） | ~200MB |
| redis / minio / nginx | ~250MB |
| **合计** | **约 1.8~2GB，贴着 2G 上限** |

**必须做的调整（缺一不可）：**

1. **加 4G swap**，否则大一点的文档解析会直接 OOM Kill：
   ```bash
   sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   sysctl vm.swappiness=10
   ```
2. **调小 PostgreSQL**：compose 里 `command` 改为
   `["postgres", "-c", "max_connections=100", "-c", "shared_buffers=128MB"]`
3. **不要 `--scale` 扩容任何 worker**，也不要给 api 加 `--workers`。
4. **开启 nginx gzip**（本文 4.4 已包含）。

**这台机器的短板要有预期：**

- **2Mbps 带宽**：上传一张 5MB 发票约 20 秒；首屏 gzip 后约 2 秒，可接受；对话本身是文本流，几乎无感。带宽是这台机器最大的体验瓶颈。
- **100G 流量/月**：个人使用（网页 + 文本对话 + 少量文件）一个月约 2~5G，够用；但如果频繁上传大文档/图片要注意。
- **40G 磁盘**：镜像约 2.5G + 系统约 5G，剩余给数据，个人用足够；定期 `docker image prune -f`。
- **大 PDF（>30MB）解析**可能触发 swap 变慢，耐心等即可，不影响其他功能。

**结论**：纯自用、预算敏感 → 2C2G + 上面的调整可以用；预算再加 ¥50/月 左右升到 **2核4G** 是体验最优解（不用 swap，解析大文档也不慌），按 1.1 的建议 4C8G 则是"多人用也不用心"的档位。

### 1.6 单机够不够？什么时候拆分


- **首版：单机 8C16G 一体化部署即可。** 组件之间通过 Docker 内网通信，无额外网络开销。
- 出现以下情况再拆分：
  1. `document_chunks` 超过 100 万行、向量检索变慢 → PostgreSQL 独立（4C8G + SSD）；
  2. 附件/文档总量超过 50G → MinIO 换成云 OSS（需改 `minio_client` 的 URL 拼接逻辑）；
  3. 日对话超过 5000 轮 → 增加 `chat-worker` 副本（见 7.4），PG 独立。

---

## 二、部署架构与端口

```
                     ┌──────────────────────────────┐
  浏览器 ──80/443──▶ │  web (nginx + 前端静态资源)   │
                     │  /api/ 反代 → api:8000        │
                     └──────────────┬───────────────┘
                                    │
                     ┌──────────────▼───────────────┐
                     │  api (uvicorn, :8000)        │
                     └───┬──────────┬───────────┬───┘
                         │          │           │
              ┌──────────▼──┐  ┌────▼────┐  ┌───▼──────────────┐
              │  postgres   │  │  redis  │  │  minio :9000     │◀── 浏览器直连（文件预览）
              │  pgvector   │  │  队列   │  │  (9001 控制台)   │
              └─────────────┘  └────┬────┘  └──────────────────┘
                                    │ 消费队列
                    ┌───────────────┼────────────────┐
           ┌────────▼──────┐ ┌──────▼───────┐ ┌──────▼─────────┐
           │ chat-worker   │ │ rag-worker   │ │ review-worker  │
           │ 会话工作流     │ │ 文档解析     │ │ AI 初审        │
           └───────────────┘ └──────────────┘ └────────────────┘
```

| 服务 | 端口 | 是否对外 | 说明 |
| --- | --- | --- | --- |
| `web` | 80 / 443 | **是** | 前端页面 + `/api/` 反向代理（含 SSE） |
| `api` | 8000 | 否（仅 127.0.0.1 便于调试） | FastAPI |
| `minio` | 9000 | **是（关键）** | 浏览器直接读文件/图片，见 4.6 说明 |
| `minio` 控制台 | 9001 | 否 | 仅管理网访问 |
| `postgres` | 5432 | 否 | 仅内网 |
| `redis` | 6379 | 否 | 仅内网 |

### ⚠️ 三个必须理解的约束

1. **MinIO 的地址必须浏览器可达**。后端返回的文件直链是 `http://{MINIO_ENDPOINT}/{bucket}/{path}`（写死在 `app/utils/minio_client.py` 的 `build_object_url`），不是经过 API 转发。如果 `MINIO_ENDPOINT` 写成容器名 `minio:9000`，前端预览一定 404。
2. **MinIO 走 HTTP**。`build_object_url` 固定拼 `http://`，所以不要给 MinIO 配 TLS 后把 `MINIO_SECURE` 改 true，会出现签名与直链协议不一致。
3. **前端生产环境用相对路径**。`agent-flow-admin/.env.production` 里 `VITE_API_BASE_URL` 为空，所有请求打到同源 `/api/v1/...`，由 nginx 反代。因此 nginx 的 `/api/` 反代不能少。

---

## 三、部署前准备

### 3.1 清单

- [ ] 服务器（推荐 8C16G / 200G SSD），已装 Docker Engine ≥ 24 与 Compose Plugin
- [ ] 域名（可选但强烈建议）与 HTTPS 证书
- [ ] 安全组放行：`80`、`443`、`9000`（MinIO；可限制来源 IP）
- [ ] 外部服务凭据：DashScope API Key、MinerU Token、Rerank 地址与 Key、Jev/OpenRouter Key
- [ ] 代码仓库（或 `scp` 上传两个子目录）

### 3.2 安装 Docker（Ubuntu）

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
docker --version && docker compose version
```

### 3.3 目录规划

```
/opt/agentflow/                ← = git 仓库根（monorepo），git clone 即完成同步
├── agent-flow-server/        # 后端代码（内含 Dockerfile、.dockerignore）
├── agent-flow-admin/         # 前端代码（内含 Dockerfile、nginx.conf、.dockerignore）
├── deploy/docker/
│   └── initdb/00-extensions.sql
├── docker-compose.yml        # 已随仓库提供
├── .env.example              # 环境变量模板（提交）
├── .env                      # 生产配置（chmod 600，已由 .gitignore 排除，不提交）
└── AgentFlow-Docker部署指南.md
```

```bash
# 代码与部署配置同属一个 git 仓库，clone 即完成同步：
git clone <你的仓库地址> /opt/agentflow
cd /opt/agentflow
cp .env.example .env && vim .env   # 填写生产配置
chmod 600 .env
```

---

## 四、配置文件

以下文件**已全部随 git 仓库提供**，服务器上 clone 后无需手工创建（下文保留完整内容，便于核对或重建）：

| 文件 | 路径 |
| --- | --- |
| 后端镜像 | `agent-flow-server/Dockerfile` + `agent-flow-server/.dockerignore` |
| 前端镜像 | `agent-flow-admin/Dockerfile` + `agent-flow-admin/.dockerignore` |
| 前端 nginx | `agent-flow-admin/nginx.conf` |
| 容器编排 | `docker-compose.yml`（仓库根） |
| 环境变量模板 | `.env.example`（复制为 `.env` 后填写） |
| pgvector 初始化 | `deploy/docker/initdb/00-extensions.sql` |

### 4.1 `agent-flow-server/Dockerfile`

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# curl 用于容器健康检查
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# 使用 uv 按 lock 文件安装依赖（与开发环境完全一致）
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
# 若服务器拉不到 ghcr.io（国内网络常见），改用：
# RUN pip install --no-cache-dir uv==0.9.* && uv sync --frozen --no-dev

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
```

### 4.2 `agent-flow-server/.dockerignore`

```
.venv
__pycache__
*.pyc
.env
.env.*
temp
tests
.pytest_cache
.idea
```

> `.env` 必须排除，否则开发环境的数据库密码、API Key 会被打进镜像。

### 4.3 `agent-flow-admin/Dockerfile` 与 `.dockerignore`

```dockerfile
# ---------- 构建 ----------
FROM node:22-alpine AS build
WORKDIR /app

RUN npm i -g pnpm@9
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# ---------- 运行 ----------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

`agent-flow-admin/.dockerignore`：

```
node_modules
dist
*.log
.git
.idea
```

> 不加这个文件，`node_modules`（十几万文件）会一起进构建上下文，构建时间从 1 分钟变成十分钟以上。

### 4.4 `agent-flow-admin/nginx.conf`

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # 静态资源压缩：主 JS 包约 1.3MB，gzip 后约 450KB
    # 2Mbps 小带宽机器上，这是首屏从 6 秒变 2 秒的关键
    gzip on;
    gzip_comp_level 5;
    gzip_min_length 1k;
    gzip_types text/plain text/css application/javascript application/json image/svg+xml;
    gzip_vary on;

    # 知识库文档可能较大；后端业务附件限制为 10MB，这里统一放宽到 100MB
    client_max_body_size 100m;

    # 前端单页应用：刷新任意路由都回落到 index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源缓存（文件名带 hash）
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 后端 API：必须关闭缓冲，否则 SSE（对话流）会被 nginx 攒着不发
    location /api/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;
        gzip off;

        # 一次对话可能持续数十秒，别用默认 60s 掐断
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 10s;
    }
}
```

### 4.5 `docker-compose.yml`（放在仓库根目录）

```yaml
name: agentflow

x-backend: &backend
  image: agentflow/server:${TAG:-latest}
  build:
    context: ./agent-flow-server
  env_file: .env
  restart: unless-stopped
  logging:
    driver: json-file
    options:
      max-size: "50m"
      max-file: "3"
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy

services:

  postgres:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-agentflow}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?请在 .env 中设置 POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-agent_flow}
      TZ: Asia/Shanghai
    # 连接池预算：api/chat/rag/review 各 20 条（pool 10 + overflow 10），再留出余量
    # shared_buffers 按内存调整：16G → 1GB，8G → 512MB，4G → 256MB
    command: ["postgres", "-c", "max_connections=200", "-c", "shared_buffers=1GB"]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./deploy/docker/initdb:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-agentflow} -d ${POSTGRES_DB:-agent_flow}"]
      interval: 10s
      timeout: 5s
      retries: 10
    ports:
      - "127.0.0.1:5432:5432"

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    # noeviction：ARQ 队列 key 绝不能被内存策略淘汰，否则任务直接丢失
    command: ["redis-server", "--appendonly", "yes", "--maxmemory-policy", "noeviction"]
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 10

  minio:
    image: minio/minio:latest
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:?请在 .env 中设置 MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:?请在 .env 中设置 MINIO_ROOT_PASSWORD}
      TZ: Asia/Shanghai
    volumes:
      - miniodata:/data
    ports:
      # 9000 必须让浏览器可访问（文件直链）；建议安全组限制来源 IP
      - "9000:9000"
      # 控制台只给内网
      - "127.0.0.1:9001:9001"
    healthcheck:
      # 若该镜像不含 mc，这里会一直显示 unhealthy，但 minio 未加入其它服务的 depends_on，
      # 不会阻塞启动；此时直接删除本段 healthcheck 即可
      test: ["CMD-SHELL", "mc ready local || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 10

  api:
    <<: *backend
    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
    ports:
      - "127.0.0.1:8000:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:8000/ || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 20s

  chat-worker:
    <<: *backend
    command: ["arq", "app.worker.chat_task.WorkerSettings"]

  rag-worker:
    <<: *backend
    command: ["arq", "app.worker.rag_task.WorkerSettings"]

  review-worker:
    <<: *backend
    command: ["arq", "app.worker.expense_review_task.WorkerSettings"]

  web:
    image: agentflow/admin:${TAG:-latest}
    build:
      context: ./agent-flow-admin
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - api
    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "3"

volumes:
  pgdata:
  redisdata:
  miniodata:
```

> **不要给服务加 `container_name`**。否则 7.4 节的 `--scale` 会因容器名冲突失败。

### 4.6 `.env`（生产配置，放仓库根目录，`chmod 600`）

```ini
# ==================== 数据库 ====================
# 容器内使用服务名 postgres；3 个 worker 与 api 共用同一份配置
DATABASE_URL=postgresql+asyncpg://agentflow:<强密码>@postgres:5432/agent_flow
POSTGRES_USER=agentflow
POSTGRES_PASSWORD=<强密码，与上面一致>
POSTGRES_DB=agent_flow

# ==================== 应用 ====================
APP_HOST=0.0.0.0
APP_PORT=8000
SECRET_KEY=<执行 openssl rand -hex 32 生成>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# ==================== Redis（ARQ 队列） ====================
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# ==================== MinIO ====================
# 必须是浏览器可达的地址，且不带 http:// 前缀
MINIO_ENDPOINT=<服务器公网IP或域名>:9000
MINIO_ACCESS_KEY=<与 MINIO_ROOT_USER 一致>
MINIO_SECRET_KEY=<与 MINIO_ROOT_PASSWORD 一致>
MINIO_BUCKET_NAME=agent-flow
MINIO_EXPENSE_BUCKET_NAME=agent-flow-expenses-private
MINIO_IMG_DIR=upload-images
MINIO_SECURE=false
MINIO_ROOT_USER=<MinIO 管理账号>
MINIO_ROOT_PASSWORD=<MinIO 管理强密码>

# ==================== LLM（DashScope 兼容模式） ====================
OPENAI_API_KEY=<DashScope API Key>
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_DEFAULT_MODEL=qwen-plus-latest
LLM_DEFAULT_TEMPERATURE=0.1
LLM_MAX_TOKENS=1024
LLM_MAX_RETRIES=0
LLM_INTENT_MODEL=qwen3.7-plus
LLM_EXTRACT_MODEL=qwen3.7-plus
VL_PLUS_MODEL=qwen3-vl-plus

# ==================== 向量与重排 ====================
EMBEDDING_MODEL_NAME=text-embedding-v4
EMBEDDING_DIMENSION=1024
RERANK_API_BASE=<rerank 服务地址，含 /compatible-api/v1>
RERANK_MODEL_NAME=qwen3.7-text-rerank

# ==================== MinerU ====================
MINERU_BASE_URL=https://mineru.net/api/v4
MINERU_API_TOKEN=<MinerU Token>

# ==================== 意图识别（Jev） ====================
JEV_PROVIDER=openrouter
JEV_MODEL=jev-latest
JEV_API_BASE=https://jevmodel.org/v1/systemone
JEV_API_KEY=<Jev Key>
JEV_OPENROUTER_BASE=https://openrouter.ai/api/v1/systemone
JEV_OPENROUTER_KEY=<OpenRouter Key>

# ==================== 本地缓存目录（容器内临时目录，自动创建） ====================
LOCAL_CACHE_DIR=temp/uploads
MINERU_OUTPUT_DIR=temp/mineru

# ==================== 可选调优 ====================
IMAGE_SUMMARY_CONCURRENCY=4
IMAGE_SUMMARY_RPM=60
EXPENSE_MERGED_EXTRACTION=true
```

**易错点：**
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` 必须与 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` 一致，否则后端连不上。
- `MINIO_ENDPOINT` 不能写 `minio:9000`（容器名），也不能带 `http://`。
- `DATABASE_URL` 的密码要与 `POSTGRES_PASSWORD` 完全一致；密码含 `@ : / #` 等字符需 URL 编码。
- 凭据不要与开发环境共用，`SECRET_KEY` 必须重新生成。

### 4.7 `deploy/docker/initdb/00-extensions.sql`

```sql
-- 仅首次初始化数据目录时执行；pgvector 镜像已内置该扩展
CREATE EXTENSION IF NOT EXISTS vector;
```

### 4.8 （可选）MinIO 子域反代

生产环境若不想直接暴露 9000，可在 `agent-flow-admin/nginx.conf`（4.4 节那个文件）里**追加**一个 server 块，把 `minio.example.com` 反代到 `minio:9000`：

```nginx
server {
    listen 80;
    server_name minio.example.com;

    client_max_body_size 100m;

    location / {
        proxy_pass http://minio:9000;
        proxy_http_version 1.1;
        # 必须保留原始 Host，否则 S3 预签名 URL 校验失败
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }
}
```

此时 `.env` 改为 `MINIO_ENDPOINT=minio.example.com`（不带端口）。注意 `build_object_url` 仍拼 `http://`，所以该子域只能是 HTTP；要上 HTTPS 需要先改代码。

---

## 五、首次部署步骤

### 5.1 构建镜像

```bash
cd /opt/agentflow
export TAG=$(date +%Y%m%d-%H%M)      # 用时间戳做版本号，便于回滚
docker compose build
docker images | grep agentflow
```

首次构建约 3~6 分钟（依赖下载）。

### 5.2 先起基础组件

```bash
docker compose up -d postgres redis minio
docker compose ps                     # 等 postgres/redis 变 healthy
docker compose logs -f postgres | tail -20
```

确认扩展已装：

```bash
docker compose exec -T postgres psql -U agentflow -d agent_flow -c "SELECT extname FROM pg_extension;"
# 期望看到 vector
```

### 5.3 初始化表结构（关键，勿跳过）

> **为什么不能只跑 `alembic upgrade head`**：仓库的 `alembic/versions/c3e113f96917_initial_database_baseline.py` 是在「已有表」的库上生成的（内容全是 `alter_column` / `add_column`），从空库执行会直接报 `relation "conversations" does not exist`。
> 全新环境必须先用 ORM 建全表，再 `alembic stamp head` 对齐版本号。**已有数据库迁移过来的场景不适用本节**（用 5.7 的 dump/restore）。

```bash
# 1) 按 ORM 元数据建表（含 pgvector 向量列）
docker compose run --rm -T --entrypoint python api - <<'PY'
import asyncio
from app.core import database
from app.core.base import Base
import app.models  # noqa: F401  确保所有模型注册到 metadata

async def main():
    database.init_db_engine()
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("tables created:", ", ".join(sorted(Base.metadata.tables)))
    await database.close_db_engine()

asyncio.run(main())
PY

# 2) 对齐 alembic 版本号（不再重复执行历史迁移）
docker compose run --rm -T --entrypoint alembic api stamp head
docker compose run --rm -T --entrypoint alembic api current
```

### 5.4 启动全部服务

```bash
docker compose up -d
docker compose ps
docker compose logs -f --tail=50 api chat-worker rag-worker review-worker
```

日志里应出现：

- `✅ 启动：初始化数据库链接资源`
- `✅ 启动：创建arq redis池`
- `✅ 启动：MinIO 存储桶初始化完成`
- rag / review worker：`ARQ Worker 启动完毕...`

MinIO 的两个 Bucket（`agent-flow`、`agent-flow-expenses-private`）由后端启动时自动创建，无需手工建桶。

### 5.5 创建管理员账号

系统没有注册接口，初始账号需直接写库：

```bash
docker compose exec -T api python - <<'PY'
import asyncio
from sqlalchemy import select
from app.core import database
from app.core.security import hash_password
from app.models import User

USERNAME = "admin"
PASSWORD = "换成你的强密码"

async def main():
    database.init_db_engine()
    async with database.async_session() as s:
        exists = (await s.execute(select(User).where(User.username == USERNAME))).scalar_one_or_none()
        if exists:
            print("已存在，跳过:", USERNAME)
        else:
            s.add(User(username=USERNAME, password_hash=hash_password(PASSWORD),
                       role="admin", nickname="管理员", is_active=True))
            await s.commit()
            print("已创建管理员:", USERNAME)
    await database.close_db_engine()

asyncio.run(main())
PY
```

### 5.6 首次验收

见第六节清单，全部通过后再配 HTTPS 与监控。

### 5.7 从已有数据库迁移（可选）

如果要把开发/测试库的数据带到生产：

```bash
# 源库导出（用容器里的 pg_dump，避免宿主没装客户端，版本也更匹配）
docker run --rm -e PGPASSWORD='<源库密码>' postgres:16 \
  pg_dump -h <源库地址> -p 5432 -U postgres -d agent_flow -Fc > agent_flow.dump

# 目标库导入（先停业务容器，只留 postgres）
docker compose stop api chat-worker rag-worker review-worker web
docker compose exec -T postgres pg_restore -U agentflow -d agent_flow --clean --if-exists --no-owner < agent_flow.dump

# 补齐后续迁移
docker compose run --rm -T --entrypoint alembic api upgrade head

docker compose up -d
```

导入后务必修改：`users` 表的默认密码、`.env` 中的 `SECRET_KEY`（旧 token 会立即失效）。

---

## 六、验收清单

| # | 检查项 | 命令 / 操作 | 期望 |
| --- | --- | --- | --- |
| 1 | 容器状态 | `docker compose ps` | 8 个服务全部 `running`，postgres/redis/api 为 `healthy` |
| 2 | 后端存活 | `curl -s http://127.0.0.1:8000/` | `{"msg":"AgentFlow API"}` |
| 3 | 前端页面 | 浏览器打开 `http://<服务器IP>/` | 登录页正常，静态资源 200 |
| 4 | 登录 | `admin` / 刚才设置的密码 | 进入工作台，无跨域报错 |
| 5 | API 反代 | 浏览器 F12 查看 `/api/v1/auth/login` | 200，非 502/504 |
| 6 | 对话 | 发一句「你好」 | 出现「思考中」，几秒后流式返回 |
| 7 | SSE 不被缓冲 | 观察回复是否**逐字**出现 | 若是整段突然出现，检查 `proxy_buffering off` |
| 8 | 报销办理 | 「我要报销一笔差旅费」→ 补全信息 → 确认 | 生成正式单号，状态「待审批」 |
| 9 | AI 初审 | 详情页抽屉 | 10~60s 内出现初审结果（非一直 pending） |
| 10 | 知识库 | 上传一个 docx，等解析完成 | 状态 `indexed`，预览正常 |
| 11 | 文件预览 | 打开知识库文档 / 发票图片 | 图片能显示（验证 MinIO 直链可达） |
| 12 | 业务健康 | 管理员调用 `GET /api/v1/admin/dashboard/health` | DB/Redis/MinIO 均 ok，Worker 有心跳 |
| 13 | 定时巡检 | `docker compose exec -T api python scripts/check_expense_review_health.py` | 退出码 0 |

> 第 6~9 项任一失败，先看 `docker compose logs --tail=100 chat-worker api`，90% 是 worker 没起或 `.env` 的 API Key 错。

---

## 七、日常运维

### 7.1 日志

```bash
docker compose logs -f --tail=200 api            # 单服务
docker compose logs -f --tail=100 chat-worker    # 会话工作流
docker compose logs -f --tail=100 rag-worker     # 文档解析
docker compose logs --since 30m | grep -i error
```

日志走 Docker json-file（已限制 50MB × 3），不会无限增长。若需集中采集，可接 Loki / ELK，把 driver 换成 `loki`。

### 7.2 重启与升级

```bash
# 常规重启
docker compose restart api chat-worker

# 版本升级（api 与 3 个 worker 必须同版本，否则字段/事件不一致）
cd /opt/agentflow
git pull
export TAG=$(date +%Y%m%d-%H%M)
docker compose build
docker compose run --rm -T --entrypoint alembic api upgrade head   # 有新迁移时执行
docker compose up -d                                               # 全量按新镜像重建
docker compose ps
```

回滚：

```bash
TAG=<上一个版本号> docker compose up -d
# 若同时回滚了数据库迁移，需先 alembic downgrade 到对应 revision（谨慎，先备份）
```

> **经验**：ARQ worker 不热加载代码。改了任何 `app/` 下的代码，只重启 api 不够，三个 worker 必须一起重建，否则会出现"新接口配旧 worker"，表现为字段缺失、指标时有时无。

### 7.3 备份

```bash
mkdir -p /backup/agentflow

# 数据库（自定义格式，支持并行恢复）
docker compose exec -T postgres pg_dump -U agentflow -d agent_flow -Fc \
  > /backup/agentflow/db_$(date +%F_%H%M).dump

# MinIO 数据卷
docker run --rm -v agentflow_miniodata:/data -v /backup/agentflow:/backup alpine \
  tar czf /backup/minio_$(date +%F_%H%M).tar.gz -C /data .

# 配置
cp .env /backup/agentflow/env_$(date +%F).bak && chmod 600 /backup/agentflow/env_*.bak
```

建议 crontab 每日 02:00 执行，并保留 14 天：

```cron
0 2 * * * cd /opt/agentflow && docker compose exec -T postgres pg_dump -U agentflow -d agent_flow -Fc > /backup/agentflow/db_$(date +\%F).dump && find /backup/agentflow -name 'db_*.dump' -mtime +14 -delete
```

恢复：

```bash
docker compose stop api chat-worker rag-worker review-worker web
docker compose exec -T postgres pg_restore -U agentflow -d agent_flow --clean --if-exists < /backup/agentflow/db_2026-11-09.dump
docker compose start api chat-worker rag-worker review-worker web
```

### 7.4 扩容

**加会话并发**（最常见）：chat-worker 无状态，同队列多副本即可。

```bash
docker compose up -d --scale chat-worker=2
docker compose ps | grep chat-worker
```

- 每个 chat-worker 进程会开 20 条数据库连接，扩副本前确认 PG `max_connections` 足够（8C16G 建议 200，极限可到 300）。
- 同样可 `--scale rag-worker=2`（文档解析高峰）。

**加 API 并发**：在 compose 的 api command 里加 `--workers 2`，但每个 uvicorn worker 各自建连接池，连接数翻倍，需同步调整 PG 参数；单机 8C 不建议超过 2。

**估算公式**：日对话轮数 ÷ 2000 ≈ chat-worker 副本数（单次对话 5~15s，单进程并发 4）。

### 7.5 巡检与监控

```bash
# 报销初审卡单（每 10 分钟，退出码非 0 触发告警）
docker compose exec -T api python scripts/check_expense_review_health.py --pending-minutes 10 --json

# 容器健康
docker compose ps --format "table {{.Service}}\t{{.Status}}"

# 磁盘与内存
df -h /var/lib/docker
free -g

# PG 连接数
docker compose exec -T postgres psql -U agentflow -d agent_flow \
  -c "SELECT count(*) AS conns, state FROM pg_stat_activity GROUP BY state;"
```

建议监控项（任选 Prometheus / 云监控）：

| 指标 | 阈值 |
| --- | --- |
| 容器重启次数 | 10 分钟内 > 2 次告警 |
| `check_expense_review_health.py` 退出码 | 非 0 告警 |
| PG 连接数 | > 150 告警 |
| 磁盘使用率 | > 80% 告警 |
| `workflow_runs` 失败率 | 5 分钟内 > 10% 告警 |

### 7.6 清理

```bash
docker image prune -f                 # 清理悬空镜像
docker builder prune -f --filter until=168h
# 谨慎：不要删 volume（pgdata/miniodata）
```

---

## 八、故障排查

| 现象 | 最可能原因 | 处理 |
| --- | --- | --- |
| 页面 404 / 刷新子路由白屏 | nginx 缺 `try_files ... /index.html` | 检查 4.4 配置 |
| 登录请求 502 | `api` 未起或 crash | `docker compose logs api`，多为 `.env` 缺变量（pydantic 启动即报错） |
| 登录成功但接口全 404 | `VITE_API_BASE_URL` 被写成了后端地址，或 nginx 未反代 `/api/` | 生产应为空值；检查 `location /api/` |
| 消息一直「思考中」 | `chat-worker` 未运行 / Redis 连不上 / 队列积压 | `docker compose ps`、`logs chat-worker`、`redis-cli LLEN` |
| 回复整段突然出现（不流式） | nginx 缓冲 | `proxy_buffering off` + `gzip off`，重启 web |
| 文档一直 `indexing` | `rag-worker` 未运行 / MinerU Token 失效 / 超大 PDF 超时 | 看 rag-worker 日志中的 MinerU 报错 |
| AI 初审一直 `pending` | `review-worker` 未运行 | 起服务；存量单据在详情页点「重新初审」 |
| 图片/文档预览 404 | `MINIO_ENDPOINT` 不可浏览器访问，或写成了容器名 | 改为公网 IP/域名:9000；确认安全组放行 |
| 预签名图片 403 | MinIO 与浏览器时钟偏差 / AccessKey 不一致 | 校准 NTP；核对 `MINIO_ACCESS_KEY` 与 root 用户 |
| 上传 413 | nginx `client_max_body_size` 太小 | 调到 100m 并 `docker compose restart web` |
| 提交报销报「附件关联的草稿明细不存在」 | 历史遗留孤儿附件（旧版本缺陷） | 已在新版本修复为清理+告警；老数据可在草稿里重新上传 |
| `type "vector" does not exist` | 用了普通 postgres 镜像或未建扩展 | 换 `pgvector/pgvector:pg16`，执行 `CREATE EXTENSION vector` |
| `too many connections` | API/worker 副本多、连接池叠加 | 提高 `max_connections` 或调小 `pool_size`（`app/core/database.py`） |
| 时间显示差 8 小时 | 容器时区不是东八区 | 所有服务加 `TZ=Asia/Shanghai` |
| 容器反复 OOM 重启（exit 137） | 内存不足，rag 解析峰值 | 升到 16G 或加 swap；限制 `rag-worker` 并发（`max_jobs`） |
| 改了代码但行为没变 | worker 未重建 | `docker compose up -d --build` 全量重建 |

---

## 九、上线前安全加固

- [ ] `SECRET_KEY` 已重新生成，未使用仓库里的开发值
- [ ] PostgreSQL / MinIO 使用强密码，且与开发环境不同
- [ ] `.env` 权限 600，未提交到 git；`.dockerignore` 已排除 `.env`
- [ ] 对外只暴露 80/443；9000 用安全组限制来源 IP（或走子域反代）
- [ ] MinIO 9001 控制台不对公网开放
- [ ] 配置 HTTPS（证书可挂到 web 容器，或在前面加云负载均衡）
- [ ] 关闭/修改默认账号 `admin` 的初始密码
- [ ] CORS：后端当前为 `allow_origins=["*"]`，若前后端同域可收紧为具体域名
- [ ] 已配置每日备份并做过一次恢复演练
- [ ] 已配置 `check_expense_review_health.py` 定时巡检
- [ ] 服务器开启安全组/防火墙，仅放行必要端口
- [ ] 确认出口可访问 DashScope / MinerU / rerank 域名

---

## 十、附：与 systemd 部署的关系

仓库里同时保留了 `agent-flow-server/deploy/systemd/` 四个单元文件（裸机部署用）。**Docker 部署时不要启用它们**，否则会出现两套 api/worker 同时消费同一队列，导致消息重复处理、状态错乱。

选择一种方式即可：

| 方式 | 适用场景 |
| --- | --- |
| Docker Compose（本文） | 推荐；环境一致、升级回滚简单 |
| systemd + 本机 venv | 已有运维体系、不便装 Docker |

---

## 十一、成本参考（云服务器，按月）

| 档位 | 典型规格 | 参考价（华东，按量/包年） |
| --- | --- | --- |
| 试用 | 4C8G + 100G SSD | 约 ¥300~500/月 |
| 生产 | 8C16G + 200G SSD | 约 ¥700~1200/月 |
| 规模化 | 16C32G + 500G SSD，另加 RDS | 约 ¥2000~3500/月 |

> 外加对象存储与外部 AI API 费用：对话成本主要在 DashScope Token（按量计费），文件解析按 MinerU 调用次数计费。首版不建议自建对象存储替代 MinIO，改造点在 URL 拼接与预签名逻辑。
