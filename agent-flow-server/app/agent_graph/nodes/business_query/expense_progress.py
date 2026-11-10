# 报销审批进度

"""报销审批进度查询节点。"""

from typing import Any

from sqlalchemy import select

from app.agent_graph.schemas.intents import BusinessQueryParams
from app.agent_graph.state import AgentState
from app.core import database
from app.core.exceptions import BizException
from app.models.user import User
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.services.expense_claim_service import ExpenseClaimService
from app.utils.task_ui import _build_expense_progress_payload


async def handle_expense_progress(state: AgentState) -> dict[str, Any]:
    """查询报销单当前状态及审批进度。"""

    query_params = BusinessQueryParams.model_validate(
        state.get("query_params") or {}
    )

    claim_no = query_params.claim_no

    if not claim_no or not claim_no.strip():
        return {
            "answer": "请提供报销单号，我才能帮你查询审批进度。"
        }

    user_id = state.get("user_id")

    if user_id is None:
        return {
            "answer": "暂时无法确认当前用户身份，请重新登录后再查询。"
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
                "answer": "当前用户不存在或账号已停用，请重新登录后再试。"
            }

        repository = ExpenseClaimRepository(session)
        service = ExpenseClaimService(repository)

        # 复用详情查询：权限校验和审批记录查询都由现有 Service 负责。
        try:
            claim = await service.get_claim_detail(
                user=user,
                claim_no=claim_no,
            )
        except BizException as exc:
            return {"answer": exc.msg}

    return {
        "answer": f"已为你查询到报销单 {claim_no} 的审批进度。",
        "ui_payload": _build_expense_progress_payload(claim),
    }