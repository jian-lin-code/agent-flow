# 报销统计

"""报销统计查询节点。"""

from typing import Any

from sqlalchemy import select

from app.agent_graph.schemas.intents import BusinessQueryParams
from app.agent_graph.state import AgentState
from app.core import database
from app.models.user import User
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.services.expense_claim_service import ExpenseClaimService
from app.utils.task_ui import _build_expense_statistics_payload
from app.utils.time_parser import resolve_time_expression


async def handle_expense_statistics(state: AgentState) -> dict[str, Any]:
    """处理报销统计查询。"""

    query_params = BusinessQueryParams.model_validate(
        state.get("query_params") or {}
    )

    # 解析用户明确表达的时间范围。
    time_expression = query_params.time_expression
    time_range = resolve_time_expression(time_expression)

    if not time_range.recognized:
        return {
            "answer": (
                f"暂时无法识别“{time_expression}”这个时间范围。"
                "你可以尝试使用“今天”“上个月”“今年”或“最近 30 天”等表达。"
            ),
            "ui_payload": None,
        }

    user_id = state.get("user_id")
    if not user_id:
        return {
            "answer": "无法获取当前用户信息，请重新登录后再试。",
            "ui_payload": None,
        }

    async with database.async_session() as session:
        user_result = await session.execute(
            select(User).where(
                User.id == user_id,
                User.is_active.is_(True),
            )
        )
        user = user_result.scalar_one_or_none()

        if user is None:
            return {
                "answer": "当前用户不存在或账号已停用，无法查询报销统计。",
                "ui_payload": None,
            }

        repository = ExpenseClaimRepository(session)
        service = ExpenseClaimService(repository)

        result = await service.get_expense_statistics(
            user=user,
            date_from=time_range.date_from,
            date_to=time_range.date_to,
        )

    ui_payload = _build_expense_statistics_payload(result)

    # 生成简洁的自然语言摘要；详细统计数据交给前端 Payload 展示。
    total = result["total"]

    if time_range.date_from and time_range.date_to:
        period_text = (
            f"{time_range.date_from.isoformat()} 至 "
            f"{time_range.date_to.isoformat()}"
        )
    elif time_range.date_from:
        period_text = f"{time_range.date_from.isoformat()} 之后"
    elif time_range.date_to:
        period_text = f"{time_range.date_to.isoformat()} 之前"
    else:
        period_text = "全部时间"

    if total == 0:
        answer = f"查询了{period_text}的报销数据，目前没有符合条件的报销记录。"
    else:
        answer = (
            f"已为你统计{period_text}的报销数据，"
            f"共找到 {total} 笔报销记录。详细金额、状态分布和费用类别统计如下。"
        )

    return {
        "answer": answer,
        "ui_payload": ui_payload,
    }