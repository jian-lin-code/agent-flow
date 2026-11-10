# approval_records / audit_logs 表模型
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from app.utils.datetime_helper import utc_now
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 如果你的 Base 定义在其他文件，请修改这里的导入路径。
from app.core.base import Base

if TYPE_CHECKING:
    from app.models.expense_claim import ExpenseClaim


class ApprovalRecord(Base):
    """审批任务与处理记录。"""

    __tablename__ = "approval_records"

    __table_args__ = (
        Index("ix_approval_records_approver_status", "approver_id", "status"),
        Index("ix_approval_records_claim_id", "claim_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # pending / approved / rejected
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    claim: Mapped["ExpenseClaim"] = relationship(back_populates="approvals")