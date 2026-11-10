"""报销单详情查询节点。"""

from typing import Any

from sqlalchemy import select

from app.agent_graph.schemas.intents import BusinessQueryParams
from app.agent_graph.state import AgentState
from app.core import database
from app.core.exceptions import BizException
from app.models import User
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.services.expense_claim_service import ExpenseClaimService
from app.utils.logger import logger
from app.utils.task_ui import _build_expense_claim_detail_payload

STATUS_LABELS = {
    "draft": "草稿",
    "needs_info": "待补充材料",
    "pending_approval": "待审批",
    "processing": "处理中",
    "approved": "已通过",
    "rejected": "已驳回",
    "completed": "已完成",
    "failed": "处理失败",
}


def _format_value(value: Any, default: str = "暂无") -> str:
    """格式化展示值。"""
    if value is None or value == "":
        return default
    return str(value)


async def handle_expense_detail(state: AgentState) -> dict[str, Any]:
    """查询单笔报销单详情。"""

    user_id = state.get("user_id")

    if user_id is None:
        logger.error("报销单详情查询失败：AgentState 缺少 user_id")
        return {
            "answer": "无法获取当前用户身份，请重新登录后再试。"
        }

    # 1. 解析查询参数
    try:
        raw_params = state.get("query_params") or {}
        params = BusinessQueryParams.model_validate(raw_params)
    except Exception:
        logger.exception("报销单详情查询参数解析失败")
        return {
            "answer": "报销单查询条件不正确，请重新描述你的查询需求。"
        }

    claim_no = (params.claim_no or "").strip()

    # 2. 缺少报销单号时追问
    if not claim_no:
        return {
            "answer": (
                "你想查询哪一笔报销单的详情？"
                "请提供报销单号，例如：查看报销单 BX20261106001 的详情。"
            )
        }

    if database.async_session is None:
        logger.error("报销单详情查询失败：数据库 Session 未初始化")
        return {
            "answer": "当前系统数据库服务尚未就绪，请稍后再试。"
        }

    try:
        async with database.async_session() as session:
            # 3. 获取当前用户
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

            # 4. 复用现有 Service 查询详情
            repository = ExpenseClaimRepository(session)
            service = ExpenseClaimService(repository)

            try:
                claim = await service.get_claim_detail(
                    user=user,
                    claim_no=claim_no,
                )
            except BizException as exc:
                # 单据不存在 / 无权查看属于预期内的业务结果，直接给出提示。
                return {
                    "answer": exc.msg
                }

        # 5. 生成回答
        return {
            "answer": f"已为你查询到报销单 {claim_no} 的详情。",
            "ui_payload": _build_expense_claim_detail_payload(claim),
        }

    except BizException as exc:
        return {
            "answer": exc.msg
        }

    except Exception:
        logger.exception(
            "报销单详情查询异常，claim_no=%s",
            claim_no,
        )
        return {
            "answer": "查询报销单详情时发生异常，请稍后重试。"
        }