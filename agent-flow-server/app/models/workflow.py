# workflow_runs / run_steps 表模型
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
from app.utils.datetime_helper import utc_now
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 如果你的 Base 定义在其他文件，请修改这里的导入路径。
from app.core.base import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.expense_claim import ExpenseClaim,BusinessTask

class WorkflowRunStatus(str, Enum):
    """定义工作流运行记录的全部合法状态。"""

    PENDING = "pending" # 已创建，等待后台执行
    RUNNING = "running" # 正在执行
    WAITING_INPUT = "waiting_input" # 等待用户补充信息
    WAITING_CONFIRMATION = "waiting_confirmation" # 等待发起人确认执行
    WAITING_APPROVAL = "waiting_approval" # 等待审批人审批
    SUCCESS = "success" # 工作流执行成功
    FAILED = "failed" # 工作流执行失败
    CANCELLED = "cancelled" # 工作流已取消

class RunStepStatus(str, Enum):
    """定义工作流执行步骤的全部合法状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowRun(Base):
    """一次工作流执行。"""

    __tablename__ = "workflow_runs"

    __table_args__ = (
        Index("ix_workflow_runs_status_started", "status", "started_at"),
        Index("ix_workflow_runs_triggered_by", "triggered_by"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 对外暴露的唯一标识（业务侧不可变），前端/API 一律使用 uid 定位，不暴露自增 id
    uid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="对外暴露的工作流运行唯一标识",
    )
    claim_id: Mapped[int | None] = mapped_column(
        ForeignKey("expense_claims.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    triggered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trigger_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # running / success / failed / waiting_approval / cancelled
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped["ExpenseClaim | None"] = relationship(
        back_populates="workflow_runs"
    )

    business_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    business_task: Mapped["BusinessTask | None"] = relationship(
        "BusinessTask",
        back_populates="workflow_runs",
    )

    agent: Mapped["Agent | None"] = relationship(back_populates="workflow_runs")

    steps: Mapped[list["RunStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
        order_by="RunStep.id"
    )


class RunStep(Base):
    """工作流内的单个执行步骤。"""

    __tablename__ = "run_steps"

    __table_args__ = (Index("ix_run_steps_run_id", "run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    run: Mapped["WorkflowRun"] = relationship(back_populates="steps")