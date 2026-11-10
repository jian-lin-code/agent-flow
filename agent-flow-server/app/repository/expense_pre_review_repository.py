"""报销单 AI 初审记录 Repository。"""

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense_claim import ExpenseClaim
from app.models.expense_pre_review import ExpensePreReview, PreReviewStatus
from app.utils.datetime_helper import utc_now


class ExpensePreReviewRepository:
    """报销单 AI 初审记录的数据访问层。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, *, claim_id: int, model_name: str | None = None, prompt_version: str | None = None
    ) -> ExpensePreReview:
        """创建一条待执行的初审记录。"""
        review = ExpensePreReview(
            claim_id=claim_id, status=PreReviewStatus.PENDING.value, model_name=model_name, prompt_version=prompt_version
        )
        self.session.add(review)
        await self.session.flush()
        return review

    async def get_by_id(self, review_id: int) -> ExpensePreReview | None:
        """根据数据库主键查询初审记录。"""
        return (await self.session.execute(select(ExpensePreReview).where(ExpensePreReview.id == review_id))).scalar_one_or_none()

    async def get_by_uid(self, review_uid: str) -> ExpensePreReview | None:
        """根据 UID 查询初审记录。"""
        return (await self.session.execute(select(ExpensePreReview).where(ExpensePreReview.uid == review_uid))).scalar_one_or_none()

    async def get_latest_by_claim_id(self, claim_id: int) -> ExpensePreReview | None:
        """查询报销单最近一次初审记录。"""
        stmt = (
            select(ExpensePreReview)
            .where(ExpensePreReview.claim_id == claim_id)
            .order_by(ExpensePreReview.created_at.desc(), ExpensePreReview.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_claim_id(self, claim_id: int) -> list[ExpensePreReview]:
        """查询报销单全部初审历史记录。"""
        stmt = (
            select(ExpensePreReview)
            .where(ExpensePreReview.claim_id == claim_id)
            .order_by(ExpensePreReview.created_at.desc(), ExpensePreReview.id.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_active_by_claim_id(self, claim_id: int) -> ExpensePreReview | None:
        """查询报销单当前正在等待或执行的初审任务。"""
        stmt = (
            select(ExpensePreReview)
            .where(
                ExpensePreReview.claim_id == claim_id,
                ExpensePreReview.status.in_([PreReviewStatus.PENDING.value, PreReviewStatus.RUNNING.value])
            )
            .order_by(ExpensePreReview.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def mark_running(self, review: ExpensePreReview) -> None:
        """标记初审任务开始执行。"""
        review.status, review.started_at, review.finished_at, review.error_message = (
            PreReviewStatus.RUNNING.value, utc_now(), None, None
        )
        await self.session.flush()

    async def mark_completed(
        self,
        review: ExpensePreReview,
        *,
        result: str,
        risk_level: str | None,
        summary: str,
        result_data: dict[str, Any] | None = None,
        model_name: str | None = None
    ) -> None:
        """保存初审结果并标记任务完成。"""
        review.status = PreReviewStatus.COMPLETED.value
        review.result, review.risk_level, review.summary = result, risk_level, summary
        review.result_data, review.finished_at, review.error_message = result_data or {}, utc_now(), None

        if model_name:
            review.model_name = model_name

        await self.session.flush()

    async def mark_failed(self, review: ExpensePreReview, *, error_message: str) -> None:
        """标记初审任务执行失败。"""
        review.status, review.error_message, review.finished_at = (
            PreReviewStatus.FAILED.value, error_message, utc_now()
        )
        await self.session.flush()

    async def update_prompt_version(self, review: ExpensePreReview, *, prompt_version: str) -> None:
        """更新初审提示词版本。"""
        review.prompt_version = prompt_version
        await self.session.flush()

    async def get_claim_for_update(self, claim_id: int) -> ExpenseClaim | None:
        """查询报销单并加行锁，避免并发创建初审任务。"""
        stmt = select(ExpenseClaim).where(ExpenseClaim.id == claim_id).with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_claim_by_id(self, *, claim_id: int, applicant_id: int) -> ExpenseClaim | None:
        """根据报销单 ID 和申请人 ID 查询报销单。"""
        stmt = select(ExpenseClaim).where(ExpenseClaim.id == claim_id, ExpenseClaim.applicant_id == applicant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def commit(self) -> None:
        """提交当前事务。"""
        await self.session.commit()

    async def rollback(self) -> None:
        """回滚当前事务。"""
        await self.session.rollback()