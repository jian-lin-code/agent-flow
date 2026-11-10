# knowledge_bases / documents / document_chunks 表模型（知识库、文档与分块）
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text, Boolean
)
from sqlalchemy import Enum as PGEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pgvector.sqlalchemy import VECTOR  # pgvector 向量列类型，对应 PostgreSQL 的 vector
from sqlalchemy.sql.schema import CheckConstraint, UniqueConstraint
from app.core.base import Base
from app.utils.datetime_helper import utc_now
from app.models.user import User
# 文档状态
class DocumentStatus(str, Enum):
    PENDING = "pending"        # 已上传
    PARSING = "parsing"        # 解析中
    CHUNKING = "chunking"      # 分块中
    EMBEDDING = "embedding"    # 向量化
    INDEXED = "indexed"        # 已索引
    FAILED = "failed"          # 失败

class KnowledgeBase(Base):
    """知识库，一组相关文档的集合。"""

    __tablename__ = "knowledge_bases"

    __table_args__ = (
        Index("ix_knowledge_bases_created_by", "created_by"),
        Index("ix_knowledge_bases_created_by_user_id", "created_by_user_id"),
        Index("ix_knowledge_bases_visibility", "visibility"),
        CheckConstraint(
            "visibility IN ('shared', 'private')",
            name="ck_knowledge_bases_visibility",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 对外暴露的唯一标识（业务侧不可变），前端/API 一律使用 uid 定位，不暴露自增 id
    uid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="对外暴露的知识库唯一标识",
    )
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 创建者昵称：保留创建时的显示名，不与用户表建立外键关系.
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 创建者真实用户 ID，用于权限判断
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="知识库创建者用户 ID",
    )

    # 知识库可见范围：shared / private
    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="private",
        server_default="private",
        comment="知识库可见范围：shared/private",
    )

    # 知识检索调用频次：每次知识检索命中该库时自增
    retrieval_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="知识检索调用频次",
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

    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )

    permissions: Mapped[list["KnowledgeBasePermission"]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )


class Document(Base):
    """知识库内的一个文档。实际文件保存在文件存储中，本表保存元数据。"""

    __tablename__ = "documents"

    __table_args__ = (
        Index("ix_documents_knowledge_base_id", "knowledge_base_id"),
        Index("ix_documents_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 对外暴露的唯一标识（业务侧不可变），前端/API 一律使用 uid 定位，不暴露自增 id
    uid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="对外暴露的文档唯一标识",
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # 存储系统的内部路径（如 MinIO 的 Object Key: knowledge/...）
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # 前端可直接访问的完整 HTTP URL
    access_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # pending / parsing / chunking / embedding / indexed / failed
    status: Mapped[DocumentStatus] = mapped_column(
        PGEnum(DocumentStatus, native_enum=False, length=32),
        nullable=False,
        default=DocumentStatus.PENDING
    )

    stage_records: Mapped[list[dict]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        comment="各阶段完成记录，包含阶段名+完成时间"
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 👇 新增：存储处理日志
    process_logs: Mapped[list[dict]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
        comment="完整的处理过程日志，包含时间、状态和消息"
    )

    # 创建者昵称：保留创建时的显示名，不与用户表建立外键关系.
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        back_populates="documents"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index"
    )


class DocumentChunk(Base):
    """文档父子切片，子切片用于向量检索。"""

    __tablename__ = "document_chunks"

    __table_args__ = (
        Index(
            "ix_document_chunks_document_index",
            "document_id",
            "chunk_index",
        ),
        Index(
            "ix_document_chunks_parent_chunk_id",
            "parent_chunk_id",
        ),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={
                "m": 16,
                "ef_construction": 64,
            },
            postgresql_ops={
                "embedding": "vector_cosine_ops",
            },
        ),
        CheckConstraint(
            "parent_chunk_id IS NULL OR parent_chunk_id <> id",
            name="ck_document_chunks_no_self_parent",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 当前记录是否为父切片
    is_parent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # 子切片关联的数据库父切片 ID。
    # 父切片自身的 parent_chunk_id 为 NULL。
    parent_chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "document_chunks.id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # 1024 维向量。父切片通常为 NULL，子切片生成向量后写入。
    embedding: Mapped[list[float] | None] = mapped_column(
        VECTOR(1024),
        nullable=True,
    )

    # 保存切片器返回的 metadata 字典
    extra_meta: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # 可选：保留原始文档的行号信息
    source_start_line: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    source_end_line: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    document: Mapped["Document"] = relationship(
        back_populates="chunks",
    )

    # 当前切片的父切片
    parent_chunk: Mapped["DocumentChunk | None"] = relationship(
        back_populates="child_chunks",
        remote_side="DocumentChunk.id",
        foreign_keys=[parent_chunk_id],
    )

    # 当前父切片所包含的子切片
    child_chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="parent_chunk",
        foreign_keys=[parent_chunk_id],
        cascade="all, delete-orphan",
    )


class KnowledgeBasePermission(Base):
    """知识库用户授权记录。"""

    __tablename__ = "knowledge_base_permissions"

    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "user_id",
            name="uq_kb_permission_user",
        ),
        Index(
            "ix_kb_permissions_user_id",
            "user_id",
        ),
        CheckConstraint(
            "permission IN ('read', 'manage')",
            name="ck_kb_permission_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    permission: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="read",
        server_default="read",
        comment="授权类型：read/manage",
    )

    granted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="授权操作人用户 ID",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        back_populates="permissions",
    )

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
    )

    granted_by: Mapped["User | None"] = relationship(
        foreign_keys=[granted_by_user_id],
    )

