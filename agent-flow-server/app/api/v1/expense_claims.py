"""报销单相关 API。

- 普通用户：我的申请列表 / 统计 / 详情
- 管理员（admin）：待我审批列表 / 审批决策
- AI 预审最新结果查询见 expense_pre_review.py（同前缀路由）
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_expense_claim_service
from app.core.deps import get_current_user
from app.core.response import UnifiedResponseRoute
from app.models import User
from app.schemas.approval import ApprovalDecisionRequest
from app.services.expense_claim_service import ExpenseClaimService

router = APIRouter(
    prefix="/expense-claims",
    tags=["expense-claims"],
    route_class=UnifiedResponseRoute,
)


@router.get("", summary="我的申请列表（连表最新 AI 预审结果）")
async def list_my_expense_claims(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ExpenseClaimService, Depends(get_expense_claim_service)],
    status: Annotated[str | None, Query(description="按单据状态过滤，如 pending_approval")] = None,
    keyword: Annotated[str | None, Query(description="关键词：报销单号 / 标题", max_length=64)] = None,
    date_from: Annotated[datetime | None, Query(description="提交时间起始（含当天）")] = None,
    date_to: Annotated[datetime | None, Query(description="提交时间截止（含当天）")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return await service.list_my_claims(
        user_id=current_user.id, status=status, keyword=keyword,
        date_from=date_from, date_to=date_to,
        page=page, page_size=page_size,
    )


@router.get("/stats", summary="报销单统计（进行中/已完成/异常/本月累计；默认管理员为全局统计，scope=mine 强制按本人申请统计）")
async def get_my_expense_claim_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ExpenseClaimService, Depends(get_expense_claim_service)],
    scope: Annotated[str | None, Query(pattern="^(mine)$", description="mine=按当前用户提交的申请统计（我的申请页口径）")] = None,
):
    return await service.get_claim_stats(user=current_user, scope=scope)


@router.get("/pending-approvals", summary="报销单列表（管理员，全部状态，连表最新预审与申请人）")
async def list_pending_approvals(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ExpenseClaimService, Depends(get_expense_claim_service)],
    status: Annotated[str | None, Query(description="可选状态过滤，不传返回全部状态")] = None,
    keyword: Annotated[str | None, Query(description="关键词：单号 / 标题 / 申请人", max_length=64)] = None,
    date_from: Annotated[datetime | None, Query(description="提交时间起始（含当天）")] = None,
    date_to: Annotated[datetime | None, Query(description="提交时间截止（含当天）")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return await service.list_pending_approvals(
        user=current_user, status=status, keyword=keyword,
        date_from=date_from, date_to=date_to,
        page=page, page_size=page_size,
    )


@router.get("/{claim_no}", summary="报销单详情（按 claim_no 查询，含费用明细、附件、最新预审）")
async def get_expense_claim_detail(
    claim_no: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ExpenseClaimService, Depends(get_expense_claim_service)],
):
    return await service.get_claim_detail(user=current_user, claim_no=claim_no)


@router.post("/{claim_no}/approval", summary="审批决策（通过/驳回，按 claim_no 定位单据）")
async def decide_expense_claim_approval(
    claim_no: str,
    request: ApprovalDecisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ExpenseClaimService, Depends(get_expense_claim_service)],
):
    return await service.decide_approval(
        user=current_user,
        claim_no=claim_no,
        decision=request.decision.value,
        comment=request.comment,
    )
