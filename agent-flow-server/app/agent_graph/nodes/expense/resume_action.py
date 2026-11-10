"""报销恢复操作节点。"""

from typing import Any

import redis

from app.agent_graph.state import AgentState
from app.repository.conversations_repository import ConversationsRepository
from app.services.business_task_service import BusinessTaskService
from app.services.conversations_service import ConversationMessageService
from app.utils.task_ui import _build_task_list_ui_payload, _build_task_ui_payload


async def handle_resume_action(
    state: AgentState,
) -> dict[str, Any]:
    """查询当前会话中已取消的报销任务，供用户选择恢复。"""

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    if user_id is None or conversation_id is None:
        return {
            "answer": "缺少用户或会话信息，暂时无法查询之前的报销任务。",
            "ui_payload": None,
        }

    business_service = BusinessTaskService()
    try:
        tasks = await business_service.list_cancelled_business_tasks(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=5,
            offset=0,
        )
    except (RuntimeError, ValueError) as exc:
        return {
            "answer": f"查询之前的报销任务失败：{exc}",
            "ui_payload": None,
        }

    if not tasks:
        return {
            "answer": (
                "当前会话中没有找到之前取消的报销申请。"
                "如果你想发起一笔新的报销，可以直接告诉我费用信息。"
            ),
            "ui_payload": None,
        }

    if len(tasks) == 1:
        single_task = tasks[0]
        answer = (
            f"找到了 1 笔之前取消的报销申请。"
            "\n是否恢复这笔报销申请并继续办理？"
            "请回复「确认恢复」或「不恢复」。"
            )
        return {
            "answer": answer,
            "ui_payload": _build_task_ui_payload(single_task),
        }

    answer = (
        f"找到了 {len(tasks)} 笔之前取消的报销申请。\n"
        "请从下面的列表中选择你想恢复的报销申请，"
        "我会先展示详情，再让你确认是否恢复。"
    )

    return {
        "answer": answer,
        # 使用独立列表 UI，不改变原单任务卡片结构。
        "ui_payload": _build_task_list_ui_payload(
            tasks,
            action="select_resume_task",
        ),
    }


async def handle_select_resume_task(
    state: AgentState,
) -> dict[str, Any]:
    """处理用户选择某一笔已取消的报销任务。"""

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")
    selected_task_uid = state.get("selected_task_uid")

    if user_id is None or conversation_id is None:
        return {
            "answer": "缺少用户或会话信息，暂时无法选择报销任务。",
            "ui_payload": None,
        }

    if not selected_task_uid:
        return {
            "answer": "没有收到你选择的报销任务，请重新选择。",
            "ui_payload": None,
        }


    business_service = BusinessTaskService()
    try:
        task = await business_service.get_cancelled_business_task(
            task_uid=str(selected_task_uid),
            user_id=user_id,
            conversation_id=conversation_id,
        )


    except (RuntimeError, ValueError):
        return {
            "answer": (
                "这笔报销任务不存在、已不允许恢复，"
                "或者不属于当前会话。请刷新列表后重新选择。"
            ),
            "ui_payload": None,
        }

    display = task.get("display") or {}
    total_amount = display.get("total_amount", "0.00")
    item_count = display.get("item_count", 0)
    expense_summary = display.get("expense_summary") or []

    answer = (
        "你选择了以下报销申请：\n\n"
        f"报销任务：{task.get('title') or '报销申请'}\n"
        f"原报销金额：{total_amount} 元\n"
        f"费用明细：{item_count} 条\n"
    )

    if expense_summary:
        answer += "\n费用摘要：\n"

        for index, item in enumerate(expense_summary, start=1):
            if not isinstance(item, dict):
                continue

            category = item.get("category") or "未分类费用"
            amount = item.get("amount")
            description = item.get("description")

            answer += f"{index}. {category}"

            if amount is not None:
                answer += f"：{amount} 元"

            if description:
                answer += f"（{description}）"

            answer += "\n"

    answer += (
        "\n是否恢复这笔报销申请并继续办理？"
        "请回复「确认恢复」或「不恢复」。"
    )

    return {
        "answer": answer,
        # 继续复用原来的单任务卡片 UI。
        "ui_payload": _build_task_ui_payload(task),
    }