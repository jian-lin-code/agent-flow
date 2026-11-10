"""拒绝恢复报销任务节点。"""

from typing import Any

from app.agent_graph.state import AgentState
from app.services.business_task_service import BusinessTaskService
from app.utils.logger import logger


async def handle_reject_resume(
    state: AgentState,
) -> dict[str, Any]:
    """用户拒绝恢复时，清除待恢复状态，不修改原任务。"""

    # 优先从会话上下文读取（与 confirm_resume 保持一致），
    # state 中的 pending_resume_task_uid 作为兜底。
    agent_context = state.get("agent_context") or {}
    pending_action = agent_context.get("pending_action") or {}
    pending_uid = (
        pending_action.get("business_task_uid")
        if isinstance(pending_action, dict)
        else None
    ) or state.get("pending_resume_task_uid")

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    if pending_uid and user_id is not None and conversation_id is not None:
        try:
            await BusinessTaskService().clear_pending_resume(
                user_id=user_id,
                conversation_id=conversation_id,
            )
        except Exception:
            logger.exception("清除待恢复状态失败，conversation_id=%s", conversation_id)

    # 即使上下文缺失，也直接给出「不恢复」的确认回复：
    # 用户明确表达了拒绝，回复「没有等待确认恢复的任务」只会让人困惑。
    return {
        "answer": (
            "好的，本次不恢复之前的报销申请。"
            "原来的报销草稿仍然保留，没有被删除或修改。"
            "如果之后想继续办理，可以再告诉我「继续刚才的报销」。"
        ),
        "pending_resume_task_uid": None,
        "pending_resume_cleared": bool(pending_uid),
    }