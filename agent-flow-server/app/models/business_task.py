from datetime import datetime
import uuid
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.utils.datetime_helper import utc_now

if TYPE_CHECKING:
    from app.models.expense_claim import ExpenseClaim
    from app.models.workflow import WorkflowRun

class BusinessTaskStatus(str, Enum):
    """业务任务状态。"""
    COLLECTING = "collecting"  # 收集中：任务正在收集所需数据/信息
    WAITING_CONFIRMATION = "waiting_confirmation"  # 待确认：等待用户或系统确认
    PROCESSING = "processing"  # 处理中：任务正在执行
    COMPLETED = "completed"  # 已完成：任务正常结束
    CANCELLED = "cancelled"  # 已取消：任务被主动取消
    FAILED = "failed"  # 已失败：任务执行出错


class BusinessTaskType(str, Enum):
    """业务任务类型。"""
    EXPENSE_REIMBURSEMENT = "expense_reimbursement"

class BusinessTask(Base):
    """会话中的业务任务，用于保存业务办理过程中的草稿。"""
    __tablename__ = "business_tasks"
    __table_args__ = (
        Index(
            "ix_business_tasks_conversation_status",
            "conversation_id",
            "status",
        ),
        Index(
            "ix_business_tasks_created_by",
            "created_by",
        ),
        Index(
            "ix_business_tasks_task_type",
            "task_type",
        ),
    )
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    uid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=BusinessTaskStatus.COLLECTING.value,
        index=True,
    )
    draft_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    missing_fields: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    claim_id: Mapped[int | None] = mapped_column(
        ForeignKey("expense_claims.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    claim: Mapped["ExpenseClaim | None"] = relationship(
        "ExpenseClaim",
        foreign_keys=[claim_id],
    )
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun",
        back_populates="business_task",
    )
    attachments: Mapped[list["BusinessTaskAttachment"]] = relationship(
        "BusinessTaskAttachment",
        back_populates="business_task",
        cascade="all, delete-orphan",
    )

class BusinessTaskAttachment(Base):
    """报销草稿阶段的附件元数据。"""
    __tablename__ = "business_task_attachments"
    __table_args__ = (
        Index(
            "ix_business_task_attachments_task_item",
            "business_task_id",
            "expense_item_uid",
        ),
    )
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    uid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    business_task_id: Mapped[int] = mapped_column(
        ForeignKey("business_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 对应 BusinessTask.draft_data 中 expense_items 的 id
    expense_item_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    content_type: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    business_task: Mapped["BusinessTask"] = relationship(
        "BusinessTask",
        back_populates="attachments",
    )