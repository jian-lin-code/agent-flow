# users 表模型
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base import Base

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 对外暴露的唯一标识（业务侧不可变），前端/API 一律使用 uid 定位，不暴露自增 id
    uid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="对外暴露的用户唯一标识",
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="登录账号"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="bcrypt密码哈希"
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="employee", comment="角色：employee/admin"
    )
    nickname: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="显示名"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"


