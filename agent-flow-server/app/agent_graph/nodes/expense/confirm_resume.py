"""确认恢复报销任务节点。"""

from typing import Any

from app.agent_graph.nodes.expense.provide_information import (
    _build_task_ui_payload,
)
from app.agent_graph.state import AgentState
from app.services.business_task_service import BusinessTaskService


async def handle_confirm_resume(
    state: AgentState,
) -> dict[str, Any]:
    """用户确认恢复后，创建新的 BusinessTask 并激活它。"""


    agent_context = state.get("agent_context") or {}
    pending_action = agent_context.get("pending_action") or {}
    source_task_uid = pending_action.get("business_task_uid")
    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    if not source_task_uid:
        return {
            "answer": (
                "当前没有等待恢复确认的报销任务。"
                "你可以告诉我想继续哪一笔报销。"
            ),
            "pending_resume_task_uid": None,
        }

    if user_id is None or conversation_id is None:
        return {
            "answer": "缺少用户或会话信息，暂时无法恢复报销任务。",
            "pending_resume_task_uid": source_task_uid,
        }

    business_service = BusinessTaskService()

    try:
        result = await business_service.restore_cancelled_business_task(
            source_task_uid=source_task_uid,
            user_id=user_id,
            conversation_id=conversation_id,
        )
    except (RuntimeError, ValueError) as exc:
        return {
            "answer": (
                f"{str(exc)}\n\n"
                "原报销任务没有被修改，你可以检查当前任务后再试。"
            ),
            "pending_resume_task_uid": None,
        }

    selected_task = result.get("selected_business_task")

    if not selected_task:
        return {
            "answer": (
                "恢复操作已返回，但没有获取到新任务信息。"
                "请刷新任务列表确认当前状态。"
            ),
            "pending_resume_task_uid": None,
        }

    status = selected_task.get("status")

    if status not in ("collecting", "waiting_confirmation"):
        return {
            "answer": (
                "这笔报销任务之前已经恢复过，但当前状态为"
                f"「{status}」，不能直接继续办理。"
                "请查看任务列表中的最新状态。"
            ),
            "selected_business_task": selected_task,
            "ui_payload": _build_task_ui_payload(selected_task),
            "pending_resume_task_uid": None,
        }

    display = selected_task.get("display") or {}
    total_amount = display.get("total_amount", "0.00")
    item_count = display.get("item_count", 0)
    missing_fields = selected_task.get("missing_fields") or []
    expense_summary = display.get("expense_summary",[])

    if result.get("already_restored"):
        answer = "这笔报销任务之前已经恢复，无需重复创建。"
    else:
        answer = "已成功恢复之前取消的报销草稿。"

    answer += (
        f"\n\n报销任务：{selected_task.get('title') or '报销申请'}"
        f"\n当前金额：{total_amount} 元"
        f"\n费用明细：{item_count} 条"
    )
    # 将缺失字段按照费用明细 ID 分组。
    missing_fields_by_item: dict[str, list[str]] = {}
    field_labels = {
        "category": "费用类别",
        "amount": "费用金额",
        "expense_date": "费用日期",
        "invoice": "发票"
    }

    if missing_fields:
        for field in missing_fields:
            parts = field.split(".")

            if len(parts) == 3 and parts[0] == "expense_items":
                item_id = parts[1]
                field_name = parts[2]

                missing_fields_by_item.setdefault(
                    item_id, []
                ).append(field_name)

        for item in expense_summary:
            item_id = str(item.get("id"))

            missing_for_item = missing_fields_by_item.get(
                item_id, []
            )

            if not missing_for_item:
                continue

            labels = [
                field_labels.get(field, field)
                for field in missing_for_item
            ]

            answer += (
                f"\n- {item.get('category') or '未分类费用'}"
                f"：还需要补充{'、'.join(labels)}"
            )

        if "expense_items" in missing_fields:
            answer += "\n请至少提供一笔费用明细。"

    else:
        answer += (
            "\n\n报销信息已经完整，请核对费用明细。"
            "确认无误后回复「确认提交」，我再为你创建正式报销单。"
        )

    return {
        "answer": answer,
        "selected_business_task": selected_task,
        "active_business_task_uid": selected_task.get("uid"),
        "pending_resume_task_uid": None,
        "ui_payload": _build_task_ui_payload(selected_task),
    }