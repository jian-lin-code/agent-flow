# AgentFlow 后端服务

**一个基于大模型的智能体（Agent）全栈应用**：用户用自然语言完成企业报销办理、业务数据查询与知识库问答。本目录是后端服务，负责 FastAPI 接口、LangGraph 工作流编排、RAG 检索、异步任务与数据持久化。

前端（管理界面）在仓库同级目录 `agent-flow-admin/`，一键部署编排在仓库根目录 `docker-compose.yml`。

---

## 1. 功能概览

| 能力 | 说明 |
| --- | --- |
| 对话式业务办理 | 自然语言发起报销、逐轮补充信息、确认提交；支持"取消/改主意"的中途打断 |
| 业务数据查询 | "查询我这个月的报销记录"这类自然语言查询，自动换算时间范围与数据权限 |
| 知识库问答 | 文档解析 → 分块 → 向量化 → 混合检索 + 重排，回答带引用来源 |
| 报销 AI 初审 | 提交后异步做合规预审，输出结论（通过/不通过/转人工）、风险等级、问题清单与证据链 |
| 审批流 | 管理员查看待审批单据，通过与驳回 |
| 管理台统计 | 任务量、执行吞吐趋势、Worker 健康状况 |
| 流式执行反馈 | SSE 推送执行步骤、耗时、Token 消耗、LLM 调用次数、检索命中数 |

### 意图清单

| 编号 | 意图代码 | 意图名称 | 示例 |
| --- | --- | --- | --- |
| 1 | `business_action` | 发起业务 | 帮我提交一笔差旅报销 |
| 2 | `business_query` | 查询业务 | 查询我这个月的报销记录 |
| 3 | `knowledge_query` | 知识问答 | 公司的差旅报销标准是什么？ |
| 4 | `provide_information` | 补充信息 | 报销金额是 860 元 |
| 5 | `confirm_action` | 确认操作 | 确认提交 |
| 6 | `cancel_action` | 取消操作 | 取消刚才的申请 |
| 7 | `small_talk` | 普通对话 | 你好、谢谢 |
| 8 | `unknown` | 未知或无法判断 | 帮我处理一下那个事情 |

---

## 2. 技术栈（Tech Stack）

| 层次 | 选型 |
| --- | --- |
| 语言 / 运行时 | Python 3.12，包管理 [uv](https://github.com/astral-sh/uv)（`pyproject.toml` + `uv.lock`） |
| Web 框架 | FastAPI + Uvicorn，Pydantic Settings 管配置 |
| Agent 编排 | LangGraph（状态机式工作流、多节点分支） |
| 异步任务 | ARQ + Redis（3 个 Worker：chat / rag / review） |
| 数据库 | PostgreSQL 16 + pgvector，SQLAlchemy 2.0（async）+ asyncpg，Alembic 迁移 |
| 对象存储 | MinIO（S3 兼容），知识库 Bucket 匿名只读、报销 Bucket 私有 |
| 模型接入 | 阿里云百炼 DashScope（OpenAI 兼容协议）：qwen 系列对话、`text-embedding-v4` 向量、`qwen3.7-text-rerank` 重排、`qwen3-vl-plus` 多模态 |
| 文档解析 | MinerU（PDF/图片）、pypdf、python-docx、mammoth（docx→HTML） |
| 鉴权 | JWT（python-jose）+ bcrypt，角色：`admin` / `employee` |
| 图片处理 | Pillow（缩略图，避免列表页拉原图） |
| 日志 | colorlog |
| 部署 | Docker / Docker Compose，或 systemd 单元 |

---

## 3. 快速开始（Quick Start）

### 3.1 一键 Docker 部署（推荐）

在**仓库根目录**执行（不是本目录）：

```bash
git clone <仓库地址> agent-flow && cd agent-flow
cp .env.example .env       # 按注释逐项填写，密码/密钥必填
docker compose up -d --build
docker compose ps          # 8 个服务应全部 Up（minio 的 healthcheck 可能显示 unhealthy，不影响）
```

启动后：

- 前端：`http://<服务器IP>/`
- 后端接口：容器内 `8000`，宿主机只绑 `127.0.0.1:8000`（不对外暴露）
- 接口文档：`http://127.0.0.1:8000/docs`，远程服务器请用 SSH 隧道：

```bash
ssh -L 8000:127.0.0.1:8000 <user>@<server>   # 然后本地开 http://localhost:8000/docs
```

服务清单（compose）：`postgres`、`redis`、`minio`、`api`、`chat-worker`、`rag-worker`、`review-worker`、`web`。

### 3.2 本地开发（改代码用这套）

前置：Python 3.12、[uv](https://github.com/astral-sh/uv)、可用的 PostgreSQL（需 pgvector 扩展）、Redis、MinIO。

```bash
cd agent-flow-server

# 1) 依赖（按 uv.lock 精确安装）
uv sync

# 2) 本地配置：本目录的 .env 只服务本地开发，不会进镜像
cp .env.example .env
# 至少改：DATABASE_URL / SECRET_KEY / MINIO_* / OPENAI_API_KEY

# 3) 建库并启用扩展（仅首次）
createdb agent_flow
psql -d agent_flow -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 4) 建表（取代表结构最新状态）
uv run alembic upgrade head

# 5) 起 API（8000 被占就用 18082，与前端 .env.development 保持一致）
uv run uvicorn main:app --reload --host 127.0.0.1 --port 18082

# 6) 另开终端，起 3 个 Worker（缺一不可）
uv run python scripts/run_workers.py
```

验证：`curl http://127.0.0.1:18082/` 返回 `{"msg":"AgentFlow API"}`；浏览器打开 `/docs` 能看到接口列表。

> `--reload` 只对 API 生效。**改了 `app/worker/` 或 `app/agent_graph/` 里的代码，必须重启 Worker**，否则跑的还是旧逻辑（这是最容易误判"代码没生效"的坑）。

### 3.3 systemd 部署（不用 Docker 时）

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now agentflow-api agentflow-chat-worker agentflow-rag-worker agentflow-review-worker
```

单元文件默认路径 `/opt/agentflow/agent-flow-server`、用户 `agentflow`，四个单元都配了 `Restart=always`（进程异常退出 3 秒后自动拉起）。

### 3.4 卡单巡检

```bash
uv run python scripts/check_expense_review_health.py --pending-minutes 10
```

退出码：`0` 正常、`1` 有卡单/失败（触发告警）、`2` 脚本自身异常。建议放进 crontab 或监控探针，配合 `--json` 接告警系统。

---

## 4. 目录结构（Project Structure）

```
agent-flow-server/
├── main.py                  # FastAPI 入口：生命周期（DB/Redis/MinIO 初始化）、CORS、全局异常
├── app/
│   ├── api/v1/              # 路由层：auth / conversations / knowledge / expense_claims
│   │                        #        / expense_pre_review / admin
│   ├── services/            # 业务编排层（事务边界在这一层）
│   ├── repository/          # 数据访问层（SQLAlchemy 查询封装）
│   ├── models/              # ORM 模型：user / conversation / workflow / agent
│   │                        #        / knowledge / business_task / expense_claim / expense_pre_review / approval
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── agent_graph/         # LangGraph 工作流
│   │   ├── workflow.py      # 图定义与节点连线
│   │   ├── nodes/           # 各节点：意图识别、报销办理、业务查询、知识问答、闲聊…
│   │   ├── prompts/         # 提示词模板（按版本管理）
│   │   ├── state.py         # 图状态定义
│   │   ├── step_names.py    # 执行步骤的中文展示名（前端进度条用）
│   │   └── token_usage.py   # Token / LLM 调用次数统计
│   ├── rag/                 # 检索增强：parser（MinerU 等）/ chunker / embedding
│   │                        #        / retriever / reranker / context_builder
│   ├── worker/              # ARQ 任务：chat_task / rag_task / expense_review_task
│   ├── events/              # SSE 事件通道（对话进度、文档解析进度）
│   ├── core/                # 配置、数据库引擎、异常基类与全局处理器
│   └── utils/               # MinIO 客户端、LLM 调用封装、时间解析、缓存、图片处理、日志
├── alembic/                 # 数据库迁移脚本
├── deploy/systemd/          # 四个 systemd 单元文件
├── scripts/                 # 开发/运维脚本（多 Worker 守护、卡单巡检、数据回填）
├── tests/                   # 接口与流程测试
└── temp/                    # 本地临时文件（上传中转、MinerU 输出），勿提交
```

**分层约定**：`api → services → repository → models`，路由层不写业务逻辑、不直接拼 SQL；跨表事务放在 service 层。

---

## 5. 环境变量配置（.env）

配置加载逻辑在 `app/core/config.py`：`ENV_FILE = Path(__file__).parents[2] / ".env"`，即**项目根目录的 `.env`**（容器内为 `/app/.env`）。优先级：**真实环境变量 > `.env` 文件**。所以 Docker 部署时由 compose 注入变量，本地开发时读文件，两种跑法共用一份代码。

### 5.1 必填项

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 连接串，`postgresql+asyncpg://用户:密码@主机:5432/agent_flow` |
| `SECRET_KEY` | JWT 签名密钥，生产必须重新生成：`openssl rand -hex 32` |
| `ALGORITHM` | JWT 算法，默认 `HS256` |
| `APP_HOST` / `APP_PORT` | 本地启动地址端口（开发常用 `127.0.0.1:18082`） |
| `MINIO_ENDPOINT` | 对象存储地址，**不带 `http://`**，且必须浏览器可达（公网 IP 或域名:9000） |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 应用登录 MinIO 的账号密码，**必须与 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` 完全一致** |
| `MINIO_BUCKET_NAME` | 知识库 Bucket（匿名只读），如 `agent-flow` |
| `MINIO_EXPENSE_BUCKET_NAME` | 报销附件 Bucket（私有），如 `agent-flow-expenses-private` |
| `OPENAI_API_KEY` | 大模型 API Key（DashScope） |
| `OPENAI_API_BASE` | 兼容端点，如 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_DEFAULT_MODEL` | 主对话模型，如 `qwen-plus-latest` |
| `EMBEDDING_MODEL_NAME` / `EMBEDDING_DIMENSION` | 向量模型与维度（改维度必须重建向量索引） |
| `RERANK_API_BASE` / `RERANK_MODEL_NAME` | 重排服务地址与模型 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | ARQ 队列所在 Redis |
| `MINERU_BASE_URL` / `MINERU_API_TOKEN` | 文档解析服务（PDF/扫描件必需） |
| `JEV_API_KEY` / `JEV_PROVIDER` / `JEV_MODEL` | 意图识别服务凭据（含 OpenRouter 备线） |
| `LOCAL_CACHE_DIR` / `MINERU_OUTPUT_DIR` | 本地缓存目录（容器内为临时目录，自动创建） |

### 5.2 可选项（有默认值）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 1440 | 登录态有效期（分钟） |
| `LLM_DEFAULT_TEMPERATURE` | 0.1 | 主模型温度 |
| `LLM_MAX_TOKENS` | 1024 | 单次生成上限 |
| `LLM_MAX_RETRIES` | 0 | 失败重试次数 |
| `LLM_INTENT_MODEL` / `LLM_EXTRACT_MODEL` | 同主模型 | 意图识别 / 信息抽取专用模型 |
| `VL_PLUS_MODEL` | `qwen3-vl-plus` | 图片理解（发票、截图）模型 |
| `MINIO_IMG_DIR` | `upload-images` | 文档图片存放前缀 |
| `MINIO_SECURE` | false | 是否走 HTTPS 访问 MinIO |
| `IMAGE_SUMMARY_CONCURRENCY` / `IMAGE_SUMMARY_RPM` | 4 / 60 | 图片摘要并发与限速 |
| `EXPENSE_MERGED_EXTRACTION` / `EXPENSE_MERGED_CONFIDENCE` | true / 0.7 | 多票合并抽取开关与置信度阈值 |

### 5.3 三个高频踩坑点

1. **MinIO 有两套变量名，值是同一个**。`MINIO_ROOT_USER/PASSWORD` 是 MinIO 容器启动时创建根账号用的（由镜像读），`MINIO_ACCESS_KEY/SECRET_KEY` 是应用登录用的（由代码读）。MinIO 没有"再建一个普通账号"的环境变量，所以两组值必须相同，否则报 `InvalidAccessKeyId` / `SignatureDoesNotMatch`。
2. **`MINIO_ENDPOINT` 同时用于「后端连 MinIO」和「拼浏览器直链」**（见 `app/utils/minio_client.py` 的 `build_object_url`）。填 `minio:9000` 会导致上传正常但图片全部 404。
3. **`.env` 绝不能进镜像**。本目录 `.dockerignore` 已排除；镜像里残留 `.env` 会让 pydantic 在缺变量时静默回落到本地开发值（如指向 WSL 的数据库地址），比直接报错更难排查。

---

## 6. 常见问题（FAQ / 避坑指南）

| 现象 | 原因与处理 |
| --- | --- |
| 发消息一直"排队中"，没有回复 | `chat-worker` 没起。`docker compose ps` 看容器；本地看 `scripts/run_workers.py` 是否在跑 |
| 新上传文档一直 `indexing` | `rag-worker` 没起；或 MinerU Token 失效（看 worker 日志） |
| 报销提交后预审永远 `pending` | `review-worker` 没起。用 `scripts/check_expense_review_health.py` 定位，输出会区分 pending 超时 / running 僵尸 / failed |
| `InvalidAccessKeyId`、`SignatureDoesNotMatch` | MinIO 的 ACCESS_KEY 与 ROOT_USER 不一致，或密码不足 8 位导致 MinIO 起不来 |
| 图片/附件链接 404、打不开 | `MINIO_ENDPOINT` 写成了容器名或内网地址；必须是浏览器可达的公网地址 |
| 对话内容"憋"到最后一次性出现 | 反向代理开了缓冲。nginx 需 `proxy_buffering off`，并把 `proxy_read_timeout` 提到 600s |
| 改了代码没生效 | Worker 不热重载，必须重启；Docker 部署要 `docker compose up -d --build api chat-worker rag-worker review-worker` |
| `ghcr.io` 拉不到 uv 镜像 | 国内服务器常见。改用 Dockerfile 注释里的方案：`RUN pip install --no-cache-dir uv==0.9.* && uv sync --frozen --no-dev` |
| 2 核 2G 机器构建/运行被杀 | 内存不足。加 4G swap，并调小 PG `shared_buffers`（2G → 128MB）；构建建议在本地完成后推镜像 |
| 已有数据库首次接 Alembic 报"表已存在" | 先 `alembic stamp head` 标记基线，再执行后续迁移，不要直接 `upgrade head` |
| 接口文档 `/docs` 打不开 | 生产环境 API 只绑 `127.0.0.1:8000` 且 nginx 只代理 `/api/`，属预期行为；用 SSH 隧道访问 |
| 时间差 8 小时 | 存库统一 UTC（`utc_now`），展示按前端本地时区；容器 `TZ=Asia/Shanghai` 只影响日志 |

---

## 7. 许可证与免责声明

本项目为**内部业务系统**，未附开源许可证，版权归作者所有。未经授权不得对外分发、商用或二次销售。

- 仓库内不含任何生产密钥；示例配置中的 `<...>` 占位必须替换。
- 大模型输出（含 AI 初审结论）仅供辅助参考，**不能替代财务合规判断**，最终审批责任由使用方承担。
- 如需开源，请在仓库根目录补充 `LICENSE`（推荐 MIT）并同步修改本节。
