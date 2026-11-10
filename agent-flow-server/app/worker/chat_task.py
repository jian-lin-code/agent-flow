"""AgentFlow 聊天工作流的 ARQ 后台任务。"""
import asyncio
from typing import Any, cast

from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_graph.state import AgentState
from app.agent_graph.step_names import get_step_display_name
from app.agent_graph.workflow import build_agent_graph
from app.core import database
from app.core.config import settings
from app.events.chat_progress import (
    ChatProgressEvent,
    ChatProgressScope,
    emit,
)
from app.models.conversation import Conversation, Message
from app.models.workflow import (
    RunStep,
    RunStepStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from app.utils.datetime_helper import utc_now
from app.utils.logger import logger




async def fail_running_steps(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    workflow_run_uid: str,
    error_message: str,
) -> None:
    """将指定工作流中所有仍在运行的步骤标记为失败。"""

    async with session_factory() as session:
        result = await session.execute(
            select(WorkflowRun.id).where(
                WorkflowRun.uid == workflow_run_uid
            )
        )
        run_id = result.scalar_one_or_none()

        if run_id is None:
            return

        steps_result = await session.execute(
            select(RunStep).where(
                RunStep.run_id == run_id,
                RunStep.status == RunStepStatus.RUNNING.value,
            )
        )

        steps = steps_result.scalars().all()

        for step in steps:
            step.status = RunStepStatus.FAILED.value
            step.error_message = error_message
            step.finished_at = utc_now()

        await session.commit()


async def complete_run_step(
    session_factory: async_sessionmaker[AsyncSession],
    step_id: int,
    output_data: dict[str, Any],
) -> None:
    async with session_factory() as session:
        result = await session.execute(
            select(RunStep).where(RunStep.id == step_id)
        )
        step = result.scalar_one_or_none()

        if step is None:
            raise ValueError(f"RunStep 不存在: {step_id}")

        if step.status != RunStepStatus.RUNNING.value:
            raise RuntimeError(
                f"RunStep 状态异常，无法标记成功："
                f"step_id={step_id}, status={step.status}"
            )

        step.status = RunStepStatus.SUCCESS.value
        step.output_data = output_data
        step.finished_at = utc_now()

        await session.commit()



async def fail_run_step(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    step_id: int,
    error_message: str,
) -> None:
    """将正在执行的步骤更新为 FAILED。"""
    async with session_factory() as session:
        step = await session.get(RunStep, step_id)

        if step is None:
            return

        if step.status != RunStepStatus.RUNNING.value:
            return

        step.status = RunStepStatus.FAILED.value
        step.finished_at = utc_now()
        step.error_message = error_message

        await session.commit()


async def process_chat_workflow(
    ctx: dict[str, Any],
    workflow_run_uid: str,
) -> None:
    """执行聊天工作流，持久化执行步骤和 AI 回复，并推送进度。"""

    session_factory = cast(
        async_sessionmaker[AsyncSession],
        database.async_session,
    )

    run_uid = workflow_run_uid
    run_id: int | None = None
    active_step_id: int | None = None

    conversation_id: int | None = None
    trigger_message_uid: str | None = None
    user_content: str | None = None
    user_id: int | None = None

    history: list[dict[str, str]] = []
    # 失败兜底里也要能读到已产出的指标，先给一个安全的初始值。
    final_state: dict[str, Any] = {}
    redis = ctx["redis"]

    try:
        # --------------------------------------------------
        # 第一阶段：读取工作流、触发消息和历史消息
        # --------------------------------------------------
        async with session_factory() as session:
            result = await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.uid == workflow_run_uid
                )
            )
            run = result.scalar_one_or_none()

            if run is None:
                logger.error(
                    "工作流运行记录不存在：run_uid=%s",
                    workflow_run_uid,
                )
                return

            run_uid = run.uid
            run_id = run.id
            user_id = run.triggered_by

            # 避免重复执行已经开始或已经结束的任务
            if run.status != WorkflowRunStatus.PENDING.value:
                logger.info(
                    "跳过非 pending 的工作流：uid=%s status=%s",
                    run.uid,
                    run.status,
                )
                return

            if user_id is None:
                raise RuntimeError("工作流缺少发起用户信息。")

            if run.trigger_message_id is None:
                run.status = WorkflowRunStatus.FAILED.value
                run.finished_at = utc_now()
                run.error_message = "工作流缺少触发消息。"
                await session.commit()

                await emit(
                    "工作流缺少触发消息，无法继续执行",
                    run_uid=run_uid,
                    ctx=ctx,
                    event=ChatProgressEvent.RUN_FAILED,
                    status=WorkflowRunStatus.FAILED.value,
                    scope=ChatProgressScope.RUN,
                    error_message="未找到触发消息，请重新发起请求。",
                )
                return

            user_message = await session.get(
                Message,
                run.trigger_message_id,
            )

            if user_message is None:
                run.status = WorkflowRunStatus.FAILED.value
                run.finished_at = utc_now()
                run.error_message = "找不到触发工作流的用户消息。"
                await session.commit()

                await emit(
                    "找不到触发工作流的用户消息",
                    run_uid=run_uid,
                    ctx=ctx,
                    event=ChatProgressEvent.RUN_FAILED,
                    status=WorkflowRunStatus.FAILED.value,
                    scope=ChatProgressScope.RUN,
                    error_message="未找到本次请求的消息，请重新发起请求。",
                )
                return

            conversation_id = run.conversation_id
            user_message_id = user_message.id
            trigger_message_uid = user_message.uid
            user_content = user_message.content
            action = None
            selected_task_uid = None

            if user_message.extra_data:
                action = user_message.extra_data.get("action")
                selected_task_uid = user_message.extra_data.get("selected_task_uid")

            if not user_content or not user_content.strip():
                run.status = WorkflowRunStatus.FAILED.value
                run.finished_at = utc_now()
                run.error_message = "用户消息内容为空。"
                await session.commit()

                await emit(
                    "用户消息内容为空，无法继续执行",
                    run_uid=run_uid,
                    ctx=ctx,
                    event=ChatProgressEvent.RUN_FAILED,
                    status=WorkflowRunStatus.FAILED.value,
                    scope=ChatProgressScope.RUN,
                    error_message="消息内容为空，请重新发送。",
                )
                return

            # 查询当前消息之前的历史消息
            history_result = await session.execute(
                select(Message.role, Message.content)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.id < user_message_id,
                    Message.role.in_(["user", "assistant"]),
                    Message.content.is_not(None),
                )
                .order_by(Message.id.desc())
                .limit(10)
            )

            # SQL 先取最新的 20 条，倒序结果需要反转为时间正序
            history = [
                {
                    "role": role,
                    "content": content,
                }
                for role, content in reversed(history_result.all())
                if content and content.strip()
            ]

            run.status = WorkflowRunStatus.RUNNING.value
            run.started_at = utc_now()
            run.error_message = None

            await session.commit()

        # --------------------------------------------------
        # 第二阶段：通知工作流开始
        # --------------------------------------------------
        await emit(
            "正在开始处理你的请求",
            run_uid=run_uid,
            ctx=ctx,
            event=ChatProgressEvent.RUN_STARTED,
            status=WorkflowRunStatus.RUNNING.value,
            scope=ChatProgressScope.RUN,
        )

        if run_id is None or conversation_id is None:
            raise RuntimeError("工作流缺少运行记录或会话信息。")

        if user_content is None or trigger_message_uid is None:
            raise RuntimeError("工作流缺少触发消息内容。")

        # --------------------------------------------------
        # 第三阶段：构建并执行 LangGraph
        # --------------------------------------------------
        graph = build_agent_graph()

        initial_state: AgentState = {
            "current_message": user_content,
            "history": history,
            "workflow_run_uid": workflow_run_uid,
            "conversation_id": conversation_id,
            "trigger_message_uid": trigger_message_uid,
            "user_id": user_id,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "llm_calls": 0,
            "selected_task_uid": selected_task_uid,
            "action": action,
            "redis":redis
        }

        final_state = dict(initial_state)

        # 限制整个 LangGraph 工作流的执行时间。
        # 超时后抛出 TimeoutError，由 Worker 的统一异常处理逻辑处理。
        async with asyncio.timeout(240):
            async for update in graph.astream(
                    initial_state,
                    stream_mode="updates",
            ):
                for node_name, node_output in update.items():

                    if not isinstance(node_output, dict):
                        continue

                    # 1. 获取节点包装器创建的 Step ID
                    step_id = node_output.get("_step_id")

                    if step_id is None:
                        raise ValueError(
                            f"节点 {node_name} 没有返回 _step_id"
                        )

                    active_step_id = step_id

                    # 2. 去掉内部元数据
                    output_data = {
                        key: value
                        for key, value in node_output.items()
                        if key != "_step_id"
                    }

                    # 3. 更新 Step 成功状态
                    await complete_run_step(
                        session_factory=session_factory,
                        step_id=step_id,
                        output_data=output_data,
                    )

                    active_step_id = None

                    # 4. 合并节点输出，形成最终 State
                    final_state.update(output_data)

                    # 5. 推送节点完成通知
                    await emit(
                        f"执行完成：{node_name}",
                        run_uid=workflow_run_uid,
                        ctx=ctx,
                        event=ChatProgressEvent.PROGRESS,
                        status=RunStepStatus.SUCCESS.value,
                        scope=ChatProgressScope.STEP,
                        step_name=node_name,
                        step_key=node_name,
                        display_name=get_step_display_name(node_name),
                    )

        # --------------------------------------------------
        # 第四阶段：保存 AI 回复并更新工作流状态
        # --------------------------------------------------
        assistant_content = final_state.get("answer")

        input_tokens = final_state.get("input_tokens", 0)
        output_tokens = final_state.get("output_tokens", 0)
        total_tokens = final_state.get("total_tokens", 0)
        llm_calls = final_state.get("llm_calls", 0)
        rag_hits = final_state.get("knowledge_reranked_count", 0)

        ui_payload = final_state.get("ui_payload")


        # 校验 Token 用量，避免异常类型进入数据库。
        token_usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

        for name, value in token_usage.items():
            if not isinstance(value, int) or value < 0:
                raise ValueError(
                    f"Token 用量字段异常：{name}={value!r}"
                )

        if total_tokens != input_tokens + output_tokens:
            logger.warning(
                "Token 用量总数与输入输出之和不一致："
                "input=%s output=%s total=%s",
                input_tokens,
                output_tokens,
                total_tokens,
            )


        if not isinstance(assistant_content, str) or not assistant_content.strip():
            raise RuntimeError("LangGraph 没有生成有效的 AI 回复。")

        async with session_factory() as session:
            result = await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.uid == workflow_run_uid
                )
            )
            run = result.scalar_one_or_none()

            if run is None:
                raise RuntimeError("执行完成后找不到工作流记录。")

            if run.status != WorkflowRunStatus.RUNNING.value:
                logger.warning(
                    "工作流状态已发生变化，取消结果写入："
                    "run_uid=%s status=%s",
                    run_uid,
                    run.status,
                )
                return

            # 运行指标：全部来自本次真实执行，供前端右侧执行面板展示。
            finished_at = utc_now()
            duration_ms = None
            if run.started_at is not None:
                duration_ms = max(
                    int((finished_at - run.started_at).total_seconds() * 1000),
                    0,
                )

            run_metrics = {
                "engine": settings.LLM_DEFAULT_MODEL,
                "duration_ms": duration_ms,
                "llm_calls": int(llm_calls or 0),
                "rag_hits": int(rag_hits or 0),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }

            # ui_payload 原样保留在顶层，运行指标挂在保留字段下，互不干扰。
            extra_data = dict(ui_payload) if isinstance(ui_payload, dict) else {}
            extra_data["run_metrics"] = run_metrics

            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_content,
                created_at=utc_now(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                extra_data=extra_data,

            )
            session.add(assistant_message)
            await session.flush()

            assistant_message_uid = assistant_message.uid
            assistant_message_content = assistant_message.content

            run.status = WorkflowRunStatus.SUCCESS.value
            run.finished_at = finished_at
            run.error_message = None

            conversation = await session.get(
                Conversation,
                conversation_id,
            )

            if conversation is not None:
                conversation.updated_at = utc_now()

            await session.commit()

        # --------------------------------------------------
        # 第五阶段：通知前端执行完成
        # --------------------------------------------------

        # 先发送已经持久化的完整 AI 消息和 Token 用量。
        await emit(
            "AI 回复已生成",
            run_uid=run_uid,
            ctx=ctx,
            event=ChatProgressEvent.ASSISTANT_MESSAGE,
            status=WorkflowRunStatus.SUCCESS.value,
            scope=ChatProgressScope.MESSAGE,
            message_uid=assistant_message_uid,
            content=assistant_message_content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            extra_data=extra_data,
        )

        # 再通知工作流完成。
        await emit(
            "工作流执行完成",
            run_uid=run_uid,
            ctx=ctx,
            event=ChatProgressEvent.RUN_COMPLETED,
            status=WorkflowRunStatus.SUCCESS.value,
            scope=ChatProgressScope.RUN,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            metrics=run_metrics,
        )

    except asyncio.CancelledError:
        logger.warning(
            "聊天工作流收到取消信号：run_uid=%s",
            workflow_run_uid,
        )

        try:
            async with asyncio.timeout(8):
                should_emit_failure = False

                async with session_factory() as session:
                    result = await session.execute(
                        select(WorkflowRun).where(
                            WorkflowRun.uid == workflow_run_uid
                        )
                    )
                    run = result.scalar_one_or_none()

                    if run is not None and run.status not in (
                            WorkflowRunStatus.SUCCESS.value,
                            WorkflowRunStatus.CANCELLED.value,
                    ):
                        run.status = WorkflowRunStatus.FAILED.value
                        run.finished_at = utc_now()
                        run.error_message = "聊天工作流被取消或超过 Worker 执行时间。"
                        should_emit_failure = True

                    await session.commit()

                if active_step_id is not None:
                    await fail_running_steps(
                        session_factory=session_factory,
                        workflow_run_uid=workflow_run_uid,
                        error_message="聊天工作流被取消或超过 Worker 执行时间。",
                    )

                if should_emit_failure:
                    await emit(
                        "聊天工作流执行超时或被取消",
                        run_uid=run_uid,
                        ctx=ctx,
                        event=ChatProgressEvent.RUN_FAILED,
                        status=WorkflowRunStatus.FAILED.value,
                        scope=ChatProgressScope.RUN,
                        error_message="处理时间过长，请稍后重试。",
                    )

        except Exception:
            logger.exception(
                "聊天工作流取消后的清理操作失败：run_uid=%s",
                workflow_run_uid,
            )
        # 必须重新抛出，不能吞掉 ARQ 的取消信号。
        raise
    except Exception as e:
        logger.exception(
            "聊天工作流执行失败：run_uid=%s",
            workflow_run_uid,
        )
        try:
            should_emit_failure = False
            fallback_message_uid: str | None = None
            failure_metrics: dict[str, Any] | None = None
            # 失败时也要给用户一条可见回复，避免对话里只剩一条提问、刷新后什么都没有。
            fallback_content = (
                "抱歉，这次没能处理成功。\n\n"
                "请把需求再描述一次；如果是费用信息，"
                "可以按「日期 + 费用类别 + 金额」发送，例如「昨天打车 120 元」。"
            )

            async with session_factory() as session:
                result = await session.execute(
                    select(WorkflowRun).where(
                        WorkflowRun.uid == workflow_run_uid
                    )
                )
                run = result.scalar_one_or_none()
                if run is not None and run.status == WorkflowRunStatus.RUNNING.value:
                    run.status = WorkflowRunStatus.FAILED.value
                    run.finished_at = utc_now()
                    run.error_message = f"处理消息失败: {e}"
                    should_emit_failure = True

                    duration_ms = None
                    if run.started_at is not None:
                        duration_ms = max(
                            int(
                                (run.finished_at - run.started_at)
                                .total_seconds() * 1000
                            ),
                            0,
                        )
                    failure_metrics = {
                        "engine": settings.LLM_DEFAULT_MODEL,
                        "duration_ms": duration_ms,
                        "llm_calls": int(final_state.get("llm_calls", 0) or 0),
                        "rag_hits": int(
                            final_state.get("knowledge_reranked_count", 0) or 0
                        ),
                        "input_tokens": int(
                            final_state.get("input_tokens", 0) or 0
                        ),
                        "output_tokens": int(
                            final_state.get("output_tokens", 0) or 0
                        ),
                        "total_tokens": int(
                            final_state.get("total_tokens", 0) or 0
                        ),
                    }

                    if conversation_id is not None:
                        fallback_message = Message(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=fallback_content,
                            created_at=utc_now(),
                            extra_data={"run_metrics": failure_metrics},
                        )
                        session.add(fallback_message)
                        await session.flush()
                        fallback_message_uid = fallback_message.uid

                await session.commit()
            # 先关闭 WorkflowRun 的 Session，再更新 Step
            if active_step_id is not None:
                await fail_running_steps(
                    session_factory=session_factory,
                    workflow_run_uid=workflow_run_uid,
                    error_message=f"处理消息失败: {e}",
                )
            if fallback_message_uid:
                await emit(
                    "已记录失败提示",
                    run_uid=run_uid,
                    ctx=ctx,
                    event=ChatProgressEvent.ASSISTANT_MESSAGE,
                    status=WorkflowRunStatus.FAILED.value,
                    scope=ChatProgressScope.MESSAGE,
                    message_uid=fallback_message_uid,
                    content=fallback_content,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    extra_data=(
                        {"run_metrics": failure_metrics}
                        if failure_metrics
                        else None
                    ),
                )
            if should_emit_failure:
                await emit(
                    f"工作流执行失败{e}",
                    run_uid=run_uid,
                    ctx=ctx,
                    event=ChatProgressEvent.RUN_FAILED,
                    status=WorkflowRunStatus.FAILED.value,
                    scope=ChatProgressScope.RUN,
                    error_message="🐣 系统有点开小差了，请稍后重试",
                    metrics=failure_metrics,
                )
        except Exception:
            logger.exception(
                "保存或发布工作流失败状态时发生异常：run_uid=%s",
                workflow_run_uid,
            )


class WorkerSettings:
    """配置聊天工作流的 ARQ Worker。"""

    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
    )

    functions = [process_chat_workflow]
    queue_name = "agent-flow"
    max_jobs = 4
    max_tries = 1
    job_timeout = 300
    keep_result = 0

    @staticmethod
    async def on_startup(ctx: dict[str, Any]) -> None:
        """初始化聊天 Worker 使用的异步数据库引擎。"""
        database.init_db_engine()

    @staticmethod
    async def on_shutdown(ctx: dict[str, Any]) -> None:
        await database.close_db_engine()