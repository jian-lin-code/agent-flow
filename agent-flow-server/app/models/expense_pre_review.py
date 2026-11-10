"""报销单 AI 初审记录模型。"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.utils.datetime_helper import utc_now

if TYPE_CHECKING:
    from app.models.expense_claim import ExpenseClaim


class PreReviewStatus(str, Enum):
    """AI 初审任务的执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PreReviewResult(str, Enum):
    """AI 初审的业务结论"""
    PASS = "pass"
    FAIL = "fail"
    MANUAL_REVIEW = "manual_review"


class ExpensePreReview(Base):
    """报销单 AI 初审记录。"""

    __tablename__ = "expense_pre_reviews"
    __table_args__ = (
        Index("ix_expense_pre_reviews_claim_created", "claim_id", "created_at"),
        Index("ix_expense_pre_reviews_status", "status"),
        # 如果前端经常查“哪些报销单被拦截了”，可以加个 result 的索引
        Index("ix_expense_pre_reviews_result", "result"),
    )

    # --- 主键与关联 ---
    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    claim_id: Mapped[int] = mapped_column(ForeignKey("expense_claims.id", ondelete="CASCADE"))

    # --- 状态与结果 ---
    status: Mapped[str] = mapped_column(String(32), default=PreReviewStatus.PENDING.value)

    # 业务结论 (pass / fail / manual_review)
    result: Mapped[str | None] = mapped_column(String(32))

    # 风险等级 (high / medium / low / none) —— 新增字段
    risk_level: Mapped[str | None] = mapped_column(String(16))

    # 初审意见的简短总结
    summary: Mapped[str | None] = mapped_column(Text)

    # JSON 存：problems 数组、evidence 证据链、extracted_data 提取明细等
    result_data: Mapped[dict | None] = mapped_column(JSON)

    # --- 追踪与记录 ---
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    # --- 时间戳 ---
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    claim: Mapped["ExpenseClaim"] = relationship(back_populates="pre_reviews")