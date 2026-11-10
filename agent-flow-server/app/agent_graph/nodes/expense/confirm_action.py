
"""报销确认操作节点。"""

from typing import Any

from app.agent_graph.nodes.expense.provide_information import (
    _build_task_ui_payload,
)
from app.agent_graph.state import AgentState
from app.services.business_task_service import BusinessTaskService

# 缺失字段 → 用户可读文案
MISSING_FIELD_LABELS = {
    "category": "费用类别",
    "amount": "金额",
    "expense_date": "费用日期",
    "invoice": "发票",
}


def _format_missing_fields(task: dict[str, Any]) -> list[str]:
    """把 missing_fields 明细转换成「第 N 条 交通费：金额、发票」这类可读文案。"""
    missing_fields = task.get("missing_fields") or []
    if not missing_fields:
        return []

    summary = (task.get("display") or {}).get("expense_summary") or []
    item_index = {
        str(item.get("id")): index
        for index, item in enumerate(summary, start=1)
        if item.get("id")
    }
    item_category = {
        str(item.get("id")): (item.get("category") or "未分类费用")
        for item in summary
        if item.get("id")
    }

    grouped: dict[str, list[str]] = {}

    for field in missing_fields:
        parts = str(field).split(".")

        if len(parts) == 3 and parts[0] == "expense_items":
            item_id, field_name = parts[1], parts[2]
            grouped.setdefault(item_id, []).append(
                MISSING_FIELD_LABELS.get(field_name, field_name)
            )

    lines: list[str] = []

    for item_id, labels in grouped.items():
        index = item_index.get(item_id)
        category = item_category.get(item_id, "未分类费用")
        prefix = f"第 {index} 条「{category}」" if index else f"「{category}」"
        lines.append(f"{prefix}：缺少{'、'.join(dict.fromkeys(labels))}")

    if "expense_items" in missing_fields:
        lines.append("还没有任何费用明细")

    # 兜底：出现了未识别的字段格式时，原样透出，避免提示为空。
    if not lines:
        lines.append("、".join(str(f) for f in missing_fields))

    return lines


# 构造确认失败时使用的节点返回结果，保留当前任务卡片。
async def _build_failure_result(
    answer: str,
    selected_task: dict[str, Any] | None,
    *,
    user_id: int | None = None,
    conversation_id: int | None = None,
) -> dict[str, Any]:
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


# 确认报销草稿，创建正式报销单。
async def handle_confirm_action(
    state: AgentState,
) -> dict[str, Any]:
    selected_task = state.get("selected_business_task")
    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    # 1. 检查必要上下文
    if not selected_task:
        return _build_failure_result(
            "当前没有确定需要提交的报销任务，请先选择报销任务。",
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
            "缺少用户或会话信息，暂时无法提交报销申请。",
            selected_task,
        )

    redis = state.get("redis", None)
    # 2. 调用 Service 创建正式报销单
    business_service = BusinessTaskService(redis=redis)

    # 2.1 提交前先看最新缺失字段：直接把「缺什么」告诉用户，
    #     而不是笼统地回复「尚未完成信息收集」。
    try:
        latest_snapshot = await business_service.get_task_response(
            task_uid=task_uid,
            user_id=user_id,
            conversation_id=conversation_id,
        )
    except (RuntimeError, ValueError):
        latest_snapshot = None

    if latest_snapshot and latest_snapshot.get("missing_fields"):
        missing_lines = _format_missing_fields(latest_snapshot)
        return await _build_failure_result(
            (
                "报销信息还不完整，暂时不能提交：\n"
                + "\n".join(f"- {line}" for line in missing_lines)
                + "\n\n补充完成后回复「确认提交」即可。"
            ),
            latest_snapshot,
            user_id=user_id,
            conversation_id=conversation_id,
        )

    try:
        result = await business_service.confirm_business_task(
            task_uid=task_uid,
            user_id=user_id,
            conversation_id=conversation_id,
        )
    except (RuntimeError, ValueError) as exc:
        return await _build_failure_result(
            (
                f"{str(exc)}\n\n"
                "请检查报销信息，确认无误后再重新提交。"
            ),
            selected_task,
            user_id=user_id,
            conversation_id=conversation_id,
        )

    # 3. 获取 Service 返回的最新任务对象
    latest_task = result.get("selected_business_task")

    if not latest_task:
        # Service 已经执行成功但没有返回任务对象时，
        # 不应该自行假设数据库状态已经同步。
        # 保留原任务，并明确提示用户。
        return await _build_failure_result(
            (
                "报销确认操作已返回结果，但未获取到最新任务状态。"
                "请刷新任务信息后确认提交结果，避免重复操作。"
            ),
            selected_task,
            user_id=user_id,
            conversation_id=conversation_id,
        )

    # 4. 检查正式报销单必要信息
    claim_no = result.get("claim_no")
    claim_id = result.get("claim_id")
    total_amount = result.get("total_amount")
    description = result.get("description")
    item_count = result.get("item_count")

    if not claim_id or not claim_no:
        return {
            "answer": (
                "报销确认操作未返回完整的报销单信息。"
                "请刷新任务信息，确认报销单是否已经创建。"
            ),
            "selected_business_task": latest_task,
            "ui_payload": _build_task_ui_payload(latest_task),
        }

    # 5. 根据 Service 返回结果组织回复
    if result.get("already_confirmed"):
        answer = (
            "这笔报销申请之前已经提交成功，无需重复提交。\n\n"
        )
    else:
        answer = "报销申请已确认并成功提交！\n\n"

    answer += (
        f"[报销单号] {claim_no}\n"
        f"[报销金额] {total_amount} 元\n"
        f"[报销描述] {description or '无'}\n"
        f"[当前状态] 待审批"
    )

    if item_count is not None:
        answer += f"\n[费用明细] {item_count} 条"

    # 6. 使用 Service 返回的最新任务对象生成 UI 数据
    return {
        "answer": answer,
        "selected_business_task": latest_task,
        "ui_payload": _build_task_ui_payload(latest_task),
    }
