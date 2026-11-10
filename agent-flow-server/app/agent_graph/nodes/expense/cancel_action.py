"""报销取消操作节点。"""

from typing import Any

from app.agent_graph.nodes.expense.provide_information import (
    _build_task_ui_payload,
)
from app.agent_graph.state import AgentState
from app.services.business_task_service import BusinessTaskService


async def _build_failure_result(
    answer: str,
    selected_task: dict[str, Any] | None,
    *,
    user_id: int | None = None,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    """构造取消失败时的响应。"""

    # state 里的任务可能是旧快照或缺少 display 的极简数据，
    # 失败时优先从数据库重新获取经 Service 包装的最新任务，避免前端卡片数据丢失。
    if (
        selected_task
        and selected_task.get("uid")
        and user_id is not None
        and conversation_id is not None
    ):
        try:
            latest_task = await BusinessTaskService().get_task_response(
                task_uid=str(selected_task["uid"]),
                user_id=user_id,
                conversation_id=conversation_id,
            )

            if latest_task is not None:
                selected_task = latest_task
        except (RuntimeError, ValueError):
            pass

    return {
        "answer": answer,
        "selected_business_task": selected_task,
        "ui_payload": _build_task_ui_payload(selected_task),
    }


async def handle_cancel_action(
    state: AgentState,
) -> dict[str, Any]:
    """处理用户取消报销草稿的操作。"""

    selected_task = state.get("selected_business_task")
    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    # 当前没有选中的业务任务。
    if not selected_task:
        return _build_failure_result(
            "当前没有需要取消的报销任务，请先选择报销任务。",
            None,
        )

    task_uid = selected_task.get("uid")

    if not task_uid:
        return await _build_failure_result(
            "报销任务标识缺失，请重新选择报销任务。",
            selected_task,
            user_id=user_id,
            conversation_id=conversation_id,
        )

    if user_id is None or conversation_id is None:
        return await _build_failure_result(
            "缺少用户或会话信息，暂时无法取消报销申请。",
            selected_task,
        )

    business_service = BusinessTaskService()

    try:
        result = await business_service.cancel_business_task(
            task_uid=task_uid,
            user_id=user_id,
            conversation_id=conversation_id,
        )

    except (RuntimeError, ValueError) as exc:
        return await _build_failure_result(
            str(exc),
            selected_task,
            user_id=user_id,
            conversation_id=conversation_id,
        )

    latest_task = result.get("selected_business_task")

    if not latest_task:
        return await _build_failure_result(
            "取消操作已返回结果，但未获取到最新任务状态。"
            "请刷新任务信息后确认取消结果。",
            selected_task,
            user_id=user_id,
            conversation_id=conversation_id,
        )

    if not result.get("cancelled"):
        return _build_failure_result(
            "报销取消操作未成功，请刷新任务信息后重试。",
            latest_task,
        )

    if result.get("already_cancelled"):
        answer = (
            "这笔报销申请之前已经取消，无需重复操作。"
        )
    else:
        answer = (
            "已成功取消这笔报销申请。\n\n"
            "原报销草稿和费用明细已保留，"
            "你可以在需要时重新发起报销。"
        )

    return {
        "answer": answer,
        "selected_business_task": latest_task,
        "ui_payload": _build_task_ui_payload(latest_task),
    }