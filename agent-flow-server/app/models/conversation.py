# conversations / messages 表模型（AI 对话会话与消息）
import uuid
from datetime import datetime, timezone
from typing import Any

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
from app.core.base import Base
from app.utils.datetime_helper import utc_now


class Conversation(Base):
    """AI 对话会话。"""

    __tablename__ = "conversations"

    __table_args__ = (
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 对外暴露的唯一标识（业务侧不可变），前端/API 一律使用 uid 定位，不暴露自增 id
    uid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="对外暴露的会话唯一标识",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新对话")

    active_business_task_uid: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="当前会话正在操作的业务任务 UID",
    )

    """ 当前设计
    "agent_context": {
        "pending_action": {
            "type": "resume_business_task",
            "business_task_uid": "xxxxxxxx"
        },
        "business_query": {
            "query_type": "expense_list",
            "query_params": {
                "time_expression": "上个月",
                "statuses": ["approved"],
                "expense_category": "差旅费",
                "page": 1,
                "page_size": 20
                }
            }
        }
    """
    agent_context: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
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

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="Message.created_at"
    )


class Message(Base):
    """单条聊天消息。"""

    __tablename__ = "messages"

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    Index(
        "ix_messages_conversation_id_id",
        "conversation_id",
        "id",
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 对外暴露的唯一标识（业务侧不可变），前端/API 一律使用 uid 定位，不暴露自增 id
    uid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="对外暴露的消息唯一标识",
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    # user / assistant / tool
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    input_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="AI回复消耗的输入Token数",
    )

    output_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="AI回复消耗的输出Token数",
    )

    total_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="AI回复消耗的总Token数",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")



