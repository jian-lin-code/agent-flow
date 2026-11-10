"""加载当前会话可操作的业务任务上下文。"""
from app.agent_graph.state import AgentState
from typing import Any
from sqlalchemy import select
from app.core import database
from app.models.business_task import BusinessTask, BusinessTaskStatus
from app.models.conversation import Conversation
from app.utils.logger import logger
from app.models.user import User

OPERABLE_STATUSES = (
    BusinessTaskStatus.COLLECTING.value,
    BusinessTaskStatus.WAITING_CONFIRMATION.value,
)


def _to_task_dict(task: BusinessTask) -> dict[str, Any]:
    return {
        "uid": task.uid,
        "title": task.title,
        "task_type": task.task_type,
        "status": task.status,
        "missing_fields": task.missing_fields or [],
        "draft_data": dict(task.draft_data or {}),
    }

async def load_business_task_context(
    state: AgentState,
) -> dict[str, Any]:
    """加载当前用户在当前会话中的任务列表及活动任务 UID。"""

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")
    current_message = state.get("current_message")
    workflow_run_uid = state.get("workflow_run_uid")
    pending_resume_task_uid = None

    if current_message is None:
        raise RuntimeError("缺少用户 message")

    if user_id is None:
        raise RuntimeError("加载业务任务上下文失败：缺少 user_id。")

    if conversation_id is None:
        raise RuntimeError("加载业务任务上下文失败：缺少 conversation_id。")

    if not workflow_run_uid:
        raise ValueError("缺少 workflow_run_uid")

    session_factory = database.async_session

    if session_factory is None:
        raise RuntimeError("数据库尚未初始化。")

    async with session_factory() as session:
        # 先验证会话归属，并读取活动任务 UID。
        conversation_result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conversation = conversation_result.scalar_one_or_none()

        if conversation is None:
            raise RuntimeError("会话不存在，或不属于当前用户。")

        # 查询当前用户的真实角色，供后续 Agent 节点执行权限判断
        user_result = await session.execute(
            select(User.role).where(
                User.id == user_id,
            )
        )
        user_role = user_result.scalar_one_or_none()

        if user_role not in {"employee", "admin"}:
            raise RuntimeError(
                f"当前用户不存在或角色无效：user_id={user_id}, role={user_role}"
            )

        # 只返回当前用户、当前会话中仍然可操作的任务。
        result = await session.execute(
            select(BusinessTask)
            .where(
                BusinessTask.created_by == user_id,
                BusinessTask.conversation_id == conversation_id,
                BusinessTask.status.in_(OPERABLE_STATUSES),
                BusinessTask.claim_id.is_(None),
            )
            .order_by(BusinessTask.created_at.desc())
        )

        tasks = result.scalars().all()
        business_tasks = [_to_task_dict(task) for task in tasks]
        active_business_task_uid = conversation.active_business_task_uid

        # 会话上下文里可能挂着「等待确认恢复」的任务，读取出来供
        # classify_intent / reject_resume 判断，避免该状态丢失后回复
        # 「当前没有等待确认恢复的报销任务」。
        agent_context = conversation.agent_context or {}
        if not isinstance(agent_context, dict):
            agent_context = {}

        pending_action = agent_context.get("pending_action") or {}
        if isinstance(pending_action, dict) and pending_action.get("type") == "resume_business_task":
            pending_resume_task_uid = pending_action.get("business_task_uid")

        logger.info("pending_resume_task_uid:%s", pending_resume_task_uid)

        return {
            "business_tasks": business_tasks,
            "active_business_task_uid": active_business_task_uid,
            "agent_context": agent_context,
            "pending_resume_task_uid": pending_resume_task_uid,
            "user_role": user_role,
        }