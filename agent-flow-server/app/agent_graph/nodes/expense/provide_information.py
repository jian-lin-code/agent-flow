
"""报销信息补充节点。"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.agent_graph.prompt_manager import render_prompt
from app.agent_graph.schemas.expense_extraction import ExpenseExtractionResult
from app.agent_graph.state import AgentState
from app.agent_graph.token_usage import (
    accumulate_token_usage,
    create_usage_callback,
    get_token_usage,
)
from app.core.config import settings
from app.core.handlers import logger
from app.services.business_task_service import BusinessTaskService
from app.utils.datetime_helper import get_beijing_now_str
from app.utils.llm import get_llm_model
from app.utils.task_ui import _build_task_ui_payload
# 取出当前活动任务的已有费用明细，仅保留匹配 update 所需的字段。
# 注入 prompt 的已有明细字段，避免上下文过长。
EXISTING_ITEM_FIELDS = ("id", "category", "amount", "expense_date")
MAX_EXISTING_ITEMS = 10
def _collect_existing_expense_items(state: AgentState) -> list[dict[str, Any]]:
    """取出当前活动任务的已有费用明细，仅保留匹配 update 所需的字段。"""
    active_task_uid = state.get("active_business_task_uid")
    if not active_task_uid:
        return []

    for task in state.get("business_tasks") or []:
        if task.get("uid") != active_task_uid:
            continue

        draft_data = task.get("draft_data") or {}
        expense_items = draft_data.get("expense_items") or []
        if not isinstance(expense_items, list):
            return []

        return [
            {field: item.get(field) for field in EXISTING_ITEM_FIELDS}
            for item in expense_items
            if isinstance(item, dict) and item.get("id")
        ]
    return []

# 安全转换金额，缺失或非法值返回 None。
def _to_decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


# 格式化费用金额，兼容尚未填写金额的明细。
def _format_expense_amount(value: Any) -> str:
    amount = _to_decimal_or_none(value)

    if amount is None:
        return "待补充"

    return f"{amount:.2f} 元"

# 将数据库任务快照转换为统一任务对象，优先复用 Service 已序列化的数据。
def _build_selected_task_from_snapshot(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    selected_task = snapshot.get("selected_business_task")

    if selected_task:
        return dict(selected_task)

    # 兼容尚未返回 selected_business_task 的旧快照结构。
    return {
        "uid": snapshot["uid"],
        "title": snapshot["title"],
        "task_type": snapshot["task_type"],
        "status": snapshot["status"],
        "missing_fields": snapshot.get("missing_fields") or [],
        "draft_data": snapshot.get("draft_data") or {},
    }

# 提取用户补充的报销信息，并新增或更新费用明细。
async def handle_provide_information(
    state: AgentState,
) -> dict[str, Any]:
    current_message = (state.get("current_message") or "").strip()
    selected_task = state.get("selected_business_task")
    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")


    # 1. 检查必要上下文
    if not selected_task:
        return {
            "answer": "暂时没有确定需要补充信息的业务任务，请先选择任务。",
            "selected_business_task": None,
            "ui_payload": None,
        }

    task_uid = selected_task.get("uid")

    if not task_uid:
        return {
            "answer": "业务任务标识缺失，请重新选择任务。",
            "selected_business_task": selected_task,
            "ui_payload": _build_task_ui_payload(selected_task),
        }

    trigger_message_uid = state.get("trigger_message_uid")
    business_service = BusinessTaskService()

    # 2. 读取当前报销草稿，并检查消息幂等性
    try:
        snapshot = await business_service.get_task_snapshot(
            task_uid=task_uid,
            user_id=user_id,
            conversation_id=conversation_id,
            trigger_message_uid=trigger_message_uid,
        )
    except RuntimeError:
        return {
            "answer": (
                "报销任务不存在、不属于当前会话，"
                "或当前状态不允许补充信息。"
            ),
            "selected_business_task": selected_task,
            "ui_payload": _build_task_ui_payload(selected_task),
        }

    # 使用数据库最新快照，不依赖进入节点时的旧任务状态。
    snapshot_task = _build_selected_task_from_snapshot(snapshot)

    if snapshot.get("already_processed"):
        return {
            "selected_business_task": snapshot_task,
            "ui_payload": _build_task_ui_payload(snapshot_task),
            "answer": "这条消息已经处理过了",
        }

    # 获取专门的抽取模型，默认可以用你配的 LLM_DEFAULT_MODEL，建议配个 LLM_EXTRACT_MODEL
    model_name = getattr(settings, "LLM_EXTRACT_MODEL", settings.LLM_DEFAULT_MODEL)
    existing_items = _collect_existing_expense_items(state)
    usage_callback = create_usage_callback()
    system_prompt = render_prompt(
        "expense/extract_expense_items.j2",
        current_date=get_beijing_now_str(),
        existing_items_json=json.dumps(existing_items, ensure_ascii=False, indent=2),
        allow_update=bool(existing_items),
        current_message=current_message
    )
    # 标准模型路径：保留 with_structured_output
    structured_llm = get_llm_model(model_name=model_name, temp=0).with_structured_output(
        ExpenseExtractionResult, method="json_schema"
    )
    # 模型输出可能违反 Schema 约束（例如金额为负数、"-500 元"）。
    # 这类可预期的校验失败必须转成正常回复，不能让整个工作流 failed。
    try:
        result: ExpenseExtractionResult = await structured_llm.ainvoke(
            [SystemMessage(content=system_prompt),], config={"callbacks": [usage_callback]}
        )
    except ValidationError as exc:
        logger.warning("费用信息抽取结果校验失败：%s | message=%s", exc, current_message)
        return {
            "selected_business_task": snapshot_task,
            "ui_payload": _build_task_ui_payload(snapshot_task),
            "answer": (
                "我识别到了费用信息，但金额或日期不符合要求"
                "（金额必须是大于 0 的数字，日期需形如 2026-11-08）。\n\n"
                "请确认后重新发送一次，例如「昨天打车 120 元」。"
            ),
        }
    except Exception:
        logger.exception("费用信息抽取失败，message=%s", current_message)
        return {
            "selected_business_task": snapshot_task,
            "ui_payload": _build_task_ui_payload(snapshot_task),
            "answer": (
                "我暂时没能解析这条费用信息，"
                "请按「日期 + 费用类别 + 金额」的方式再说一次，例如「昨天打车 120 元」。"
            ),
        }
    usage = get_token_usage(usage_callback)

    operations = [operation.model_dump() for operation in result.operations]
    clarification = result.clarification

    # 5. 没有操作时，向用户澄清，不修改业务数据。
    if not operations:
        answer = (
            (clarification if clarification else None)
            or "请提供费用信息，我这边帮您登记"
        )

        return {
            "selected_business_task": snapshot_task,
            "ui_payload": _build_task_ui_payload(snapshot_task),
            "answer": answer,
        }

    # 6. 调用 Service 原子执行新增和更新操作。
    try:
        save_result = await business_service.apply_expense_operations(
            task_uid=task_uid,
            user_id=user_id,
            conversation_id=conversation_id,
            trigger_message_uid=trigger_message_uid,
            operations=operations,
        )
    except (RuntimeError, ValueError) as exc:
        return {
            "selected_business_task": snapshot_task,
            "ui_payload": _build_task_ui_payload(snapshot_task),
            "answer": (
                f"{str(exc)}\n\n"
                "请确认费用信息后再试一次。"
            ),
        }

    # 7. 处理并发情况下的重复消息。
    if save_result["already_processed"]:
        latest_task = (
            save_result.get("selected_business_task") or snapshot_task
        )

        return {
            "selected_business_task": latest_task,
            "ui_payload": _build_task_ui_payload(latest_task),
            "answer": "这条消息已经处理过了，无需重复提交。",
        }

    # 8. 获取 Service 返回的最新数据。
    added_items = save_result.get("added_items") or []
    updated_items = save_result.get("updated_items") or []
    merged_items = save_result.get("merged_items") or []
    deleted_items = save_result.get("deleted_items") or []
    expense_items = save_result.get("expense_items") or []


    # 必须使用 Service 返回的最新任务快照，不要继续使用旧任务状态。
    selected_business_task = (
        save_result.get("selected_business_task") or snapshot_task
    )

    total_amount = (
        _to_decimal_or_none(save_result.get("total_amount"))
        or Decimal("0.00")
    )

    # 9. 计算本次新增金额。
    # 新增明细允许金额暂缺，因此不能直接 Decimal(item["amount"])。
    added_amount = sum(
        (
            amount
            for item in added_items
            if (
                amount := _to_decimal_or_none(item.get("amount"))
            ) is not None
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))

    answer_parts: list[str] = []

    if added_items:
        answer_parts.append(
            f"已新增 {len(added_items)} 条费用明细，"
            f"本次新增金额：{added_amount:.2f} 元。"
        )

    if updated_items:
        answer_parts.append(
            f"已更新 {len(updated_items)} 条已有费用明细。"
        )
    if merged_items:
        answer_parts.append(
            f"已把信息补充到已有的 {len(merged_items)} 条费用明细（未重复新增）。"
        )
    if deleted_items:
        answer_parts.append(
            f"已删除 {len(deleted_items)} 条费用明细。"
        )
    if not answer_parts:
        answer_parts.append("已更新报销草稿。")

    answer = "\n".join(answer_parts)

    # 10. 展示当前完整费用明细。
    answer += (
        f"\n\n当前累计报销金额：{total_amount:.2f} 元\n\n"
        "目前记录的费用：\n"
    )

    for index, item in enumerate(expense_items, start=1):
        category = item.get("category") or "未分类费用"
        amount_text = _format_expense_amount(item.get("amount"))

        answer += f"{index}. {category}：{amount_text}"

        if item.get("description"):
            answer += f"（{item['description']}）"

        expense_date = item.get("expense_date")

        if expense_date:
            answer += f"，日期：{expense_date}"
        else:
            answer += "，日期：待补充"

        answer += "\n"

    # 11. 根据最新任务状态生成后续引导。
    task_status = selected_business_task.get("status")
    missing_fields = selected_business_task.get("missing_fields") or []

    if task_status == "waiting_confirmation":
        answer += (
            "\n费用信息已经完整，请核对以上报销明细。\n"
            "如果确认无误，请回复「确认提交」；"
            "如果需要修改，请直接告诉我。"
        )
    else:
        answer += "\n还有部分必填信息需要补充。"

        # 将缺失字段按照费用明细 ID 分组。
        missing_fields_by_item: dict[str, list[str]] = {}

        for field in missing_fields:
            parts = field.split(".")

            if len(parts) == 3 and parts[0] == "expense_items":
                item_id = parts[1]
                field_name = parts[2]

                missing_fields_by_item.setdefault(
                    item_id, []
                ).append(field_name)

        field_labels = {
            "category": "费用类别",
            "amount": "费用金额",
            "expense_date": "费用日期",
            "invoice": "发票"
        }

        for item in expense_items:
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

        answer += "\n\n你可以继续补充费用类别、金额和日期。"

    return {
        "selected_business_task": selected_business_task,
        "ui_payload": _build_task_ui_payload(selected_business_task),
        "answer": answer,
        **accumulate_token_usage(state, usage),
    }
