import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, cast
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_graph.step_names import get_step_display_name
from app.core import database
from app.events.chat_progress import (
    ChatProgressEvent,
    ChatProgressScope,
    emit,
)
from app.models.workflow import (
    RunStep,
    RunStepStatus,
    WorkflowRun,
)
from app.utils.datetime_helper import utc_now
from app.utils.logger import logger

NodeFunction = Callable[
    [dict[str, Any]],
    Awaitable[dict[str, Any]],
]

async def mark_step_failed(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    step_id: int,
    error_message: str,
) -> None:
    """将指定步骤标记为 FAILED。"""

    async with session_factory() as session:
        step = await session.get(RunStep, step_id)

        if step is None:
            return

        # 避免覆盖已经完成的步骤状态
        if step.status != RunStepStatus.RUNNING.value:
            return

        step.status = RunStepStatus.FAILED.value
        step.error_message = error_message[:2000]
        step.finished_at = utc_now()

        await session.commit()


def with_step_tracking(
    step_name: str,
    node_func: NodeFunction,
) -> NodeFunction:
    """
    为 LangGraph 节点增加统一的执行生命周期管理。

    负责：
    1. 创建 RunStep
    2. 推送节点开始通知
    3. 执行实际节点
    4. 节点异常时更新 Step 状态
    5. 将 step_id 随节点结果返回给 Worker

    Step 成功状态由 chat_task.py 在收到 astream 更新后处理。
    """

    async def wrapped_node(
        state: dict[str, Any],
    ) -> dict[str, Any]:

        workflow_run_uid = state.get("workflow_run_uid")

        if not workflow_run_uid:
            raise ValueError(
                f"节点 {step_name} 缺少 workflow_run_uid"
            )

        session_factory = cast(
            async_sessionmaker[AsyncSession],
            database.async_session,
        )

        # 1. 创建 RunStep
        async with session_factory() as session:
            result = await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.uid == workflow_run_uid
                )
            )
            workflow_run = result.scalar_one_or_none()

            if workflow_run is None:
                raise ValueError(
                    f"WorkflowRun 不存在: {workflow_run_uid}"
                )

            step = RunStep(
                run_id=workflow_run.id,
                step_name=step_name,
                status=RunStepStatus.RUNNING.value,
                input_data={
                    "workflow_run_uid": workflow_run_uid,
                },
                started_at=utc_now(),
            )

            session.add(step)
            await session.flush()

            step_id = step.id

            await session.commit()

        try:
            # 2. 推送节点开始通知
            await emit(
                f"开始执行：{step_name}",
                run_uid=workflow_run_uid,
                event=ChatProgressEvent.STEP_STARTED,
                status=RunStepStatus.RUNNING.value,
                scope=ChatProgressScope.STEP,
                step_name=step_name,
                step_key=step_name,
                display_name=get_step_display_name(step_name)
            )

            # 3. 执行实际节点业务逻辑
            node_result = await node_func(state)

            if not isinstance(node_result, dict):
                raise TypeError(
                    f"节点 {step_name} 必须返回 dict"
                )

            # 4. 将 step_id 作为内部元数据返回给 Worker
            return {
                **node_result,
                "_step_id": step_id,
            }


        except asyncio.CancelledError:
            error_message = "节点执行被取消或工作流超时。"
            try:
                # 给取消清理留出有限时间
                async with asyncio.timeout(5):
                    await mark_step_failed(
                        session_factory=session_factory,
                        step_id=step_id,
                        error_message=error_message,
                    )
            except Exception:

                logger.exception(
                    "节点取消后的 RunStep 清理失败："
                    "step_name=%s step_id=%s",
                    step_name,
                    step_id,
                )
            # 不能吞掉取消信号
            raise


        except Exception as exc:

            try:

                await mark_step_failed(

                    session_factory=session_factory,

                    step_id=step_id,

                    error_message=str(exc),

                )


            except Exception:

                logger.exception(

                    "节点异常后的 RunStep 更新失败："

                    "step_name=%s step_id=%s",

                    step_name,

                    step_id,

                )

            await emit(

                f"节点执行失败：{step_name}",

                run_uid=workflow_run_uid,

                event=ChatProgressEvent.PROGRESS,

                status=RunStepStatus.FAILED.value,

                scope=ChatProgressScope.STEP,

                step_name=step_name,

                step_key=step_name,

                display_name=get_step_display_name(step_name),

                error_message=str(exc)[:2000],

            )

            raise

    return wrapped_node