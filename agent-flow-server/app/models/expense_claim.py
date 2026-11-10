from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING
from app.utils.datetime_helper import utc_now
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 如果你的 Base 定义在其他文件，请修改这里的导入路径。
from app.core.base import Base

if TYPE_CHECKING:
    from app.models.approval import ApprovalRecord
    from app.models.workflow import WorkflowRun
    from app.models.expense_pre_review import ExpensePreReview

class ExpenseClaimStatus(str, Enum):
    """报销单状态枚举"""

    DRAFT = "draft"  # 草稿（用户还在填写）
    NEEDS_INFO = "needs_info"  # 需要补充材料（如发票缺失、被退回）
    PENDING_APPROVAL = "pending_approval"  # 待审批（已提交，等待财务/主管审批）
    PROCESSING = "processing"  # 处理中（审批已通过，打款/财务系统中）
    APPROVED = "approved"  # 已通过（审批完成，等待打款或已打款）
    REJECTED = "rejected"  # 已驳回
    COMPLETED = "completed"  # 已完成（流程全部走完，资金已到账）
    FAILED = "failed"  # 异常/失败（打款失败、系统异常等）


class ExpenseClaim(Base):
    """报销申请主表。"""

    __tablename__ = "expense_claims"

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_expense_claims_amount"),
        Index("ix_expense_claims_applicant_created", "applicant_id", "created_at"),
        Index("ix_expense_claims_status", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    claim_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    applicant_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    # draft / pending_approval / needs_info / approved /
    # rejected / processing / completed / failed
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    items: Mapped[list["ExpenseItem"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["ApprovalRecord"]] = relationship(
        back_populates="claim"
    )
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="claim"
    )
    pre_reviews: Mapped[list["ExpensePreReview"]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ExpensePreReview.created_at.desc()",
    )


class ExpenseItem(Base):
    """报销明细，例如交通费、住宿费和餐费。"""

    __tablename__ = "expense_items"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_expense_items_amount"),
        Index("ix_expense_items_claim_id", "claim_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False
    )

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    expense_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="expense_item",
    )
    claim: Mapped["ExpenseClaim"] = relationship(back_populates="items")


class Attachment(Base):
    """报销附件元数据。实际文件保存在文件存储中。"""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expense_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("expense_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expense_item: Mapped["ExpenseItem | None"] = relationship(
        back_populates="attachments",
    )
    claim: Mapped["ExpenseClaim"] = relationship(back_populates="attachments")


