# AgentFlow 管理端

**AgentFlow 的前端管理界面**：面向企业员工与财务管理员，提供 AI 对话式业务办理（报销、查询、知识问答）、知识库管理、报销单审批与数据看板。

后端服务在仓库同级目录 `agent-flow-server/`，一键部署编排在仓库根目录 `docker-compose.yml`（本目录作为 `web` 服务，由 Nginx 托管静态文件并反代 `/api`）。

---

## 1. 功能概览

| 页面 | 路由 | 说明 |
| --- | --- | --- |
| 登录 | `/login` | 账号密码登录，JWT 存 localStorage，按角色跳转工作台 |
| 员工工作台 | `/dashboard/employee` | 我的申请统计、快捷入口、最近记录 |
| 管理工作台 | `/dashboard/admin` | 任务统计、执行吞吐趋势（1h / 24h / 7d）、系统健康与 Worker 状态 |
| AI 对话 | `/ai-chat` | 流式对话（SSE）、执行过程面板、相关任务侧栏、附件上传、Markdown 渲染、会话搜索/重命名/删除 |
| 我的申请 | `/my-claims` | 报销单列表、详情、AI 预审结果（结论/风险等级/问题清单）、重新初审、附件预览 |
| 待我审批 | `/pending-approvals` | 管理员视角全部单据，通过与驳回 |
| 知识库 | `/kb-manage` | 知识库列表与详情、文档上传与解析进度、成员权限分配 |

**角色**：`employee`（员工，提单与查看自己的申请）、`admin`（管理员，审批 + 知识库管理 + 全局看板）。路由守卫 + 菜单按角色渲染。

**执行过程面板的真实数据来源**：模型名（`LLM_DEFAULT_MODEL`）、耗时（run 起止时间）、Token 消耗与 LLM 调用次数（后端 `run_metrics`，挂在该条助手消息的 `extra_data` 上）、检索命中数（重排后条数）。历史会话会从最近一条助手消息回填，不回填时显示"暂无数据"。

---

## 2. 技术栈（Tech Stack）

| 层次 | 选型 |
| --- | --- |
| 框架 | Vue 3.5（`<script setup>` + Composition API） |
| 语言 | TypeScript 6，`vue-tsc` 做构建期类型检查 |
| 构建 | Vite 8 |
| UI | Element Plus 2.14 + `@element-plus/icons-vue` |
| 状态 | Pinia 4（`stores/user.ts`） |
| 路由 | Vue Router 4（`createWebHistory`，路由级懒加载 + 空闲预取） |
| 国际化 | vue-i18n 9，简体中文 / English 双语 |
| 请求 | axios（统一实例 + 拦截器），SSE 用原生 `fetch` + `ReadableStream` |
| 内容渲染 | `marked`（Markdown）、`pretext-markdown` |
| 代码规范 | TS strict，路径别名 `@` → `src` |
| 部署 | Nginx 1.27（gzip、SPA fallback、`/api` 反代）、Docker 多阶段构建 |
| 包管理 | pnpm 9，Node 22 |

---

## 3. 快速开始（Quick Start）

### 3.1 一键 Docker 部署（推荐）

在**仓库根目录**执行（不是本目录）：

```bash
git clone <仓库地址> agent-flow && cd agent-flow
cp .env.example .env       # 后端变量，前端不需要配
docker compose up -d --build
```

访问 `http://<服务器IP>/` 即可。前端镜像走两阶段构建：`node:22-alpine` 里 `pnpm build` 产出 `dist/`，再拷进 `nginx:1.27-alpine`，最终只对外暴露 80 端口。

默认账号由后端初始化创建（开发环境默认 `admin/123456`、`employee/123456`），**首次登录后请立刻改密码**，生产环境不要沿用。

### 3.2 本地开发

前置：Node 22、pnpm 9，且后端已在 `127.0.0.1:18082` 运行。

```bash
cd agent-flow-admin
pnpm install            # 按 pnpm-lock.yaml 安装
pnpm dev                # 默认 http://localhost:5173
```

`.env.development` 已指向本地后端：

```
VITE_API_BASE_URL=http://127.0.0.1:18082
```

后端端口不是 18082 时改这里即可（改完需要重启 dev server）。开发态是**跨端口直连**，依赖后端 `main.py` 里的 CORS 放行。

### 3.3 生产构建

```bash
pnpm build              # 先 vue-tsc 类型检查，再 vite build，产物在 dist/
pnpm preview            # 本地预览 dist（注意：没有反代，/api 会 404，见 FAQ）
```

---

## 4. 目录结构（Project Structure）

```
agent-flow-admin/
├── index.html                  # 单页入口
├── vite.config.ts              # Vite 配置（仅 vue 插件 + @ 别名，无 dev proxy）
├── nginx.conf                  # 生产 nginx：gzip / SPA fallback / /api 反代（关缓冲支持 SSE）
├── Dockerfile                  # 两阶段：node 构建 → nginx 运行
├── .env.development            # 开发环境变量（绝对地址指向本地后端）
├── .env.production             # 生产环境变量（baseURL 留空 = 同源）
└── src/
    ├── main.ts                 # 应用入口：Element Plus、i18n、router、pinia
    ├── App.vue
    ├── api/                    # 接口层：request.ts（axios 实例）/ auth / chat / knowledge / expense / dashboard
    ├── composables/
    │   └── useWorkflowStream.ts  # SSE 连接、断线补偿、耗时与 run_metrics 解析
    ├── stores/user.ts          # 用户信息、角色、token
    ├── router/index.ts         # 路由表、懒加载与预取、角色守卫
    ├── layout/MainLayout.vue   # 侧边栏 + 顶栏 + 内容区
    ├── view/
    │   ├── login.vue
    │   ├── ai-chat.vue         # 对话主界面（最复杂的页面）
    │   ├── dashboard/          # employee.vue / admin.vue
    │   ├── expense/            # my-claims / pending-approvals / PreReviewDrawer / DecideDialog
    │   └── knowledge/          # index / detail / document + 各类弹窗
    ├── components/             # 通用组件：删除会话、退出登录、表格滑动
    ├── locales/                # zh-CN.ts / en-US.ts，文案集中管理
    ├── utils/                  # markdown 渲染、复制剪贴板
    ├── mock/                   # 开发用假数据（仅知识库模块）
    └── style/                  # 全局样式与主题变量
```

**约定**：页面只做展示与交互，网络请求一律走 `src/api/*`；跨页面复用的流式逻辑放 `composables/`；文案不硬编码在模板里，统一进 `locales/`。

---

## 5. 环境变量配置（.env）

前端只有**一个**变量，但它是构建期注入的，最容易踩坑。

| 变量 | 开发（`.env.development`） | 生产（`.env.production`） |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:18082` | **留空** |

**为什么生产要留空**：留空时 axios 的 `baseURL` 为空字符串，请求变成相对路径，浏览器自动补上当前页面的协议+域名+端口（即 `http://服务器IP`），再由 nginx 的 `location /api/` 转发进 Docker 内网的 `api:8000`。同源，无需 CORS。

```
浏览器 http://服务器IP/
  └─ JS 里 baseURL="" → GET /api/v1/...
       └─ nginx :80  location /api/  →  proxy_pass http://api:8000
            └─ FastAPI /api/v1/...（Docker DNS 解析服务名 api）
```

**三个必须知道的点**：

1. **必须带 `VITE_` 前缀**，否则 Vite 不会注入到客户端代码。
2. **值在 `vite build` 时被替换成字符串字面量**，不是运行时读取。改了 `.env.production` 必须重新构建镜像：`docker compose up -d --build web`。
3. **生产别填 `http://服务器IP:8000`**。compose 里 api 只绑 `127.0.0.1:8000`，公网访问不到，还会引入跨域问题。

---

## 6. 常见问题（FAQ / 避坑指南）

| 现象 | 原因与处理 |
| --- | --- |
| 页面能开，但所有接口 404 | `VITE_API_BASE_URL` 在生产被打成了绝对地址，或 nginx 没配 `/api/` 反代。检查 `dist` 里是否残留 `127.0.0.1` |
| 刷新任意路由变 404 | SPA 需要回落到 `index.html`，`nginx.conf` 已有 `try_files $uri $uri/ /index.html`。若自行部署，记得抄这段 |
| 对话内容最后一次性蹦出来 | nginx 缓冲了 SSE。`/api/` 段必须 `proxy_buffering off` + `proxy_cache off` + `gzip off`，`proxy_read_timeout` 调到 600s（配置已内置） |
| 上传大附件报 413 | nginx `client_max_body_size` 默认 1MB，已放宽到 100m；后端业务限制 10MB，超限会返回业务错误 |
| 本地 `pnpm preview` 接口全 404 | `preview` 只起静态服务，没有反代。验证生产行为请用 Docker 起 nginx，或在 `vite.config.ts` 里临时加 `server.proxy` |
| 改了接口地址不生效 | 构建期注入。重新 `pnpm build` / 重建镜像，并强制刷新（`Ctrl+Shift+R`）清掉旧 JS |
| 登录后立刻被踢回登录页 | token 过期或角色缓存不一致。`router` 守卫会在 `beforeEach` 重新拉 `/api/v1/auth/me` 纠正角色 |
| TypeScript 构建报错但 dev 正常 | dev 不做类型检查，`pnpm build` 会先跑 `vue-tsc -b`。按报错修类型，别用 `any` 糊过去 |
| 页面文案显示成 key（如 `claims.title`） | i18n 键缺失或重复定义（对象字面量后写覆盖前写）。`locales/zh-CN.ts` 与 `en-US.ts` 需同步补键 |
| Node 版本报错 / 安装失败 | 需 Node 22、pnpm 9。`corepack enable && corepack prepare pnpm@9 --activate` |
| `pnpm install` 锁文件不一致 | CI/镜像里用 `--frozen-lockfile`；本地升级依赖后要提交新的 `pnpm-lock.yaml` |
| 浏览器缓存了旧页面 | 带 hash 的静态资源缓存 30 天没问题，`index.html` 建议在网关层加 `Cache-Control: no-cache`，否则发版后用户可能拿到旧入口 |

---

## 7. 许可证与免责声明

本项目为**内部业务系统**，未附开源许可证，版权归作者所有。未经授权不得对外分发、商用或二次销售。

- 仓库内不含任何生产密钥；`.env.production` 留空是刻意设计，请勿填入内网地址。
- 界面中的 AI 输出（含预审结论）仅为辅助信息，最终审批与合规判断由使用者负责。
- 如需开源，请在仓库根目录补充 `LICENSE`（推荐 MIT）并同步修改本节。
