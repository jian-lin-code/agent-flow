## AgentFlow 后端服务

### 一、进程清单（缺一不可）

| 进程 | 启动命令 | 作用 | 缺失后的表现 |
| --- | --- | --- | --- |
| API | `uvicorn main:app --host 0.0.0.0 --port $APP_PORT` | HTTP / SSE 接口 | 全站不可用 |
| chat-worker | `arq app.worker.chat_task.WorkerSettings` | 会话工作流（意图识别、报销办理、查询） | 消息一直排队，无回复 |
| rag-worker | `arq app.worker.rag_task.WorkerSettings` | 知识库文档解析 / 向量化 | 新上传文档一直 indexing |
| review-worker | `arq app.worker.expense_review_task.WorkerSettings` | 报销单 AI 初审 | 新提交单据的预审一直 pending |

> `review-worker` 曾经不在部署清单里，导致"提交了报销却永远没有 AI 初审"。**必须与 API 一起纳入守护。**

### 二、部署方式

#### 1. systemd（生产推荐）

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now agentflow-api agentflow-chat-worker agentflow-rag-worker agentflow-review-worker
```

单元文件默认路径为 `/opt/agentflow/agent-flow-server`、用户 `agentflow`，按实际部署调整。
四个单元均配置 `Restart=always`，进程异常退出 3 秒后自动拉起。

#### 2. 脚本守护（本地 / 容器 / 临时环境）

```bash
uv run python scripts/run_workers.py            # 只守护 3 个 worker
uv run python scripts/run_workers.py --with-api # 同时起 FastAPI
```

任一子进程退出会自动重启；`Ctrl+C` 统一优雅退出。

### 三、卡单告警

```bash
# 建议放到 crontab（每 10 分钟）或 systemd timer / 监控探针
uv run python scripts/check_expense_review_health.py --pending-minutes 10
```

- 退出码 `0` 正常，`1` 发现卡单/失败（触发告警），`2` 执行失败。
- 输出包含：pending 超时单据（多为 review-worker 没启动）、running 僵尸任务、failed 单据。
- `--json` 便于接监控系统。

### 四、第一版意图清单

| 编号 | 意图代码              | 意图名称       | 示例                       |
| ---- | --------------------- | -------------- | -------------------------- |
| 1    | `business_action`     | 发起业务       | 帮我提交一笔差旅报销       |
| 2    | `business_query`      | 查询业务       | 查询我这个月的报销记录     |
| 3    | `knowledge_query`     | 知识问答       | 公司的差旅报销标准是什么？ |
| 4    | `provide_information` | 补充信息       | 报销金额是 860 元          |
| 5    | `confirm_action`      | 确认操作       | 确认提交                   |
| 6    | `cancel_action`       | 取消操作       | 取消刚才的申请             |
| 7    | `small_talk`          | 普通对话       | 你好、谢谢                 |
| 8    | `unknown`             | 未知或无法判断 | 帮我处理一下那个事情       |
