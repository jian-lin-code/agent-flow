"""报销单相关 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.core.response import UnifiedResponseRoute
from app.api.dependencies import get_expense_pre_review_service
from app.models import User
from app.services.expense_pre_review_service import ExpensePreReviewService

# User 和 get_current_user 的导入路径沿用你现有附件上传路由

router = APIRouter(
    prefix="/expense-claims",
    tags=["expense-claims"],
    route_class=UnifiedResponseRoute,
)


@router.get(
    "/{claim_id}/pre-reviews/latest",
    summary="获取报销单最新 AI 初审结果",
)
async def get_latest_expense_pre_review(
    claim_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ExpensePreReviewService,
        Depends(get_expense_pre_review_service),
    ],
):
    return await service.get_latest_review(
        claim_id=claim_id,
        user=current_user,
    )


@router.post(
    "/{claim_id}/pre-reviews/retry",
    summary="重新触发报销单 AI 初审（初审失败后重试）",
)
async def retry_expense_pre_review(
    claim_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ExpensePreReviewService,
        Depends(get_expense_pre_review_service),
    ],
):
    return await service.retry_review(
        claim_id=claim_id,
        user=current_user,
    )