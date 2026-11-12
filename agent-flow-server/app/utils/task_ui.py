"""构造前端使用的业务任务 UI 数据，不暴露草稿详情。"""

from typing import Any
from fastapi.encoders import jsonable_encoder


def _build_task_ui_payload(
    task: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """构造单个业务任务卡片。"""
    if not task:
        return None

    display = task.get("display") or {}

    business_task = {
        "uid": task.get("uid"),
        "title": task.get("title"),
        "task_type": task.get("task_type"),
        "status": task.get("status"),
        "missing_fields": task.get("missing_fields") or [],
        "claim_status": task.get("claim_status"),
        "display": {
            "display_title": display.get("display_title"),
            "total_amount": display.get("total_amount"),
            "currency": display.get("currency"),
            "item_count": display.get("item_count"),
            "expense_summary": display.get("expense_summary") or [],
            "claim_no": display.get("claim_no"),
            "created_at": display.get("created_at"),
        },
    }

    return {
        "ui_type": "business_task",
        "business_task": business_task,
    }



def _build_task_list_ui_payload(
    tasks: list[dict[str, Any]] | None,
    *,
    action: str,
) -> dict[str, Any]:
    """构造多个业务任务的候选列表，并声明前端选择任务时应执行的动作。"""

    allowed_actions = {
        "select_business_task",
        "select_resume_task",
    }

    if action not in allowed_actions:
        raise ValueError(f"不支持的任务选择动作：{action}")

    business_tasks = []

    for task in tasks or []:
        payload = _build_task_ui_payload(task)

        if payload is not None:
            business_tasks.append(payload["business_task"])

    return {
        "ui_type": "business_task_list",
        "action": action,
        "business_tasks": business_tasks,
    }



def _build_expense_claim_list_payload(
    result: dict[str, Any],
) -> dict[str, Any]:
    """构造报销单列表卡片。"""

    # 👇 关键：在提取数据前，先对整个 result 进行一次深度清洗！
    # 它会自动把 datetime 转成 isoformat 字符串，把 Decimal 转成 float 等
    encoded_result = jsonable_encoder(result)

    items = encoded_result.get("items") or []
    total = encoded_result.get("total", 0)
    page = encoded_result.get("page", 1)
    page_size = encoded_result.get("page_size", 20)

    expense_claims = []

    for claim in items:
        # 因为已经经过了 jsonable_encoder，这里的 claim 里面的所有时间都已经变成字符串了
        expense_claims.append({
            "claim_no": claim.get("claim_no"),
            "title": claim.get("title"),
            "description": claim.get("description"),
            "status": claim.get("status"),
            "total_amount": claim.get("total_amount"),
            "currency": claim.get("currency"),
            "item_count": claim.get("item_count", 0),
            "categories": claim.get("categories") or [],
            "descriptions": claim.get("descriptions") or [],
            "submitted_at": claim.get("submitted_at"),
            "created_at": claim.get("created_at"),
            "updated_at": claim.get("updated_at"),
            "pre_review": claim.get("pre_review"),
        })

    total_pages = (
        (total + page_size - 1) // page_size
        if page_size > 0
        else 0
    )

    return {
        "ui_type": "expense_claim_list",
        "expense_claims": expense_claims,
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
    }


def _build_expense_claim_detail_payload(
    result: dict[str, Any],
) -> dict[str, Any]:
    """构造报销单详情卡片。"""

    # 统一处理 datetime、Decimal 等类型
    encoded_result = jsonable_encoder(result)

    return {
        "ui_type": "expense_claim_detail",
        "expense_claim": {
            "id": encoded_result.get("id"),
            "claim_no": encoded_result.get("claim_no"),
            "title": encoded_result.get("title"),
            "description": encoded_result.get("description"),
            "status": encoded_result.get("status"),
            "total_amount": encoded_result.get("total_amount"),
            "currency": encoded_result.get("currency"),
            "item_count": encoded_result.get("item_count", 0),
            "categories": encoded_result.get("categories") or [],
            "descriptions": encoded_result.get("descriptions") or [],
            "submitted_at": encoded_result.get("submitted_at"),
            "created_at": encoded_result.get("created_at"),
            "updated_at": encoded_result.get("updated_at"),

            # 费用明细
            "items": encoded_result.get("items") or [],

            # AI 初审
            "pre_review": encoded_result.get("pre_review"),

            # 人工审批记录
            "approvals": encoded_result.get("approvals") or [],

            # 附件
            "attachments": encoded_result.get("attachments") or [],
        },
    }



def _build_expense_progress_payload(
    result: dict[str, Any],
) -> dict[str, Any]:
    """构造报销审批进度卡片。"""

    encoded_result = jsonable_encoder(result)

    approvals = []

    for approval in encoded_result.get("approvals") or []:
        approver = approval.get("approver") or {}

        approvals.append({
            "id": approval.get("id"),
            "status": approval.get("status"),
            "comment": approval.get("comment"),
            "created_at": approval.get("created_at"),
            "decided_at": approval.get("decided_at"),
            "approver": {
                "username": approver.get("username"),
                "nickname": approver.get("nickname"),
            },
        })

    expense_progress = {
        "claim_no": encoded_result.get("claim_no"),
        "title": encoded_result.get("title"),
        "status": encoded_result.get("status"),
        "total_amount": encoded_result.get("total_amount"),
        "currency": encoded_result.get("currency"),
        "submitted_at": encoded_result.get("submitted_at"),
        "approvals": approvals,
    }

    return {
        "ui_type": "expense_progress",
        "expense_progress": expense_progress,
    }


def _build_expense_approval_history_payload(
    result: dict[str, Any],
) -> dict[str, Any]:
    """构造报销单人工审批历史卡片。"""

    encoded_result = jsonable_encoder(result)

    approvals = []

    for approval in encoded_result.get("approvals") or []:
        approver = approval.get("approver") or {}

        approvals.append({
            "id": approval.get("id"),
            "status": approval.get("status"),
            "comment": approval.get("comment"),
            "created_at": approval.get("created_at"),
            "decided_at": approval.get("decided_at"),
            "approver": {
                "id": approver.get("id"),
                "username": approver.get("username"),
                "nickname": approver.get("nickname"),
            },
        })

    return {
        "ui_type": "expense_approval_history",
        "expense_approval_history": {
            "claim_no": encoded_result.get("claim_no"),
            "title": encoded_result.get("title"),
            "status": encoded_result.get("status"),
            "total_amount": encoded_result.get("total_amount"),
            "currency": encoded_result.get("currency"),
            "approvals": approvals,
        },
    }

def _build_expense_pre_review_payload(
    result: dict[str, Any],
) -> dict[str, Any]:
    """构造报销 AI 初审结果卡片。"""

    encoded_result = jsonable_encoder(result)

    pre_review = encoded_result.get("pre_review")

    if pre_review:
        pre_review = {
            "uid": pre_review.get("uid"),
            "status": pre_review.get("status"),
            "result": pre_review.get("result"),
            "risk_level": pre_review.get("risk_level"),
            "summary": pre_review.get("summary"),
            "result_data": pre_review.get("result_data"),
            "model_name": pre_review.get("model_name"),
            "prompt_version": pre_review.get("prompt_version"),
            "started_at": pre_review.get("started_at"),
            "finished_at": pre_review.get("finished_at"),
            "error_message": pre_review.get("error_message"),
            "created_at": pre_review.get("created_at"),
            "updated_at": pre_review.get("updated_at"),
        }

    return {
        "ui_type": "expense_pre_review",
        "expense_pre_review": {
            "claim_no": encoded_result.get("claim_no"),
            "title": encoded_result.get("title"),
            "status": encoded_result.get("status"),
            "total_amount": encoded_result.get("total_amount"),
            "currency": encoded_result.get("currency"),
            "pre_review": pre_review,
        },
    }


def _build_expense_statistics_payload(
    result: dict[str, Any],
) -> dict[str, Any]:
    """构造报销统计查询的前端展示数据。"""

    encoded_result = jsonable_encoder(result)

    currency_statistics = []
    for item in encoded_result.get("currency_statistics") or []:
        currency_statistics.append({
            "currency": item.get("currency"),
            "claim_count": item.get("claim_count", 0),
            "total_amount": item.get("total_amount", "0.00"),
            "average_amount": item.get("average_amount", "0.00"),
        })

    category_statistics = []
    for item in encoded_result.get("category_statistics") or []:
        category_statistics.append({
            "category": item.get("category"),
            "currency": item.get("currency"),
            "item_count": item.get("item_count", 0),
            "total_amount": item.get("total_amount", "0.00"),
        })

    return {
        "ui_type": "expense_statistics",
        "total": encoded_result.get("total", 0),
        "date_from": encoded_result.get("date_from"),
        "date_to": encoded_result.get("date_to"),
        "status_counts": encoded_result.get("status_counts") or {},
        "currency_statistics": currency_statistics,
        "category_statistics": category_statistics,
    }


def _build_knowledge_sources_payload(
    sources: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """构造知识库问答的参考来源卡片。"""
    if not sources:
        return None

    # 统一处理可能存在的 datetime 等类型（虽然目前都是 str/int，但为了防御性编程加上）
    encoded_sources = jsonable_encoder(sources)

    formatted_sources = []
    for source in encoded_sources:
        start_line = source.get("source_start_line")
        end_line = source.get("source_end_line")

        # 位置优先展示所属小节标题：行号是解析产物 md 的行号，用户在 PDF 里找不到，
        # 只有纯文本文档（没有标题结构）才退回行号兜底。
        heading_path = source.get("heading_path") or []
        section_title = (
            str(heading_path[-1]).strip()
            if isinstance(heading_path, list) and len(heading_path) >= 2
            else ""
        )

        if section_title:
            location = section_title
        elif start_line is not None and end_line is not None:
            location = f"第 {start_line}-{end_line} 行"
        elif start_line is not None:
            location = f"第 {start_line} 行"
        else:
            location = ""

        formatted_sources.append({
            "index": source.get("index"),
            "document_title": source.get("document_title") or "未知文档",
            "knowledge_base_name": source.get("knowledge_base_name") or "未知知识库",
            "location": location,
            # 以下字段供前端「点击引用 → 打开原文 → 定位到命中段落」
            "document_uid": source.get("document_uid"),
            "knowledge_base_uid": source.get("knowledge_base_uid"),
            "anchor_text": source.get("anchor_text") or "",
            "source_start_line": start_line,
            "source_end_line": end_line,
        })

    return {
        "ui_type": "knowledge_sources",
        "knowledge_sources": formatted_sources,
    }