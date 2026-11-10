import enum
from datetime import datetime
from typing import Dict, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    # 可见范围：private 受限空间（默认，仅创建者与被授权成员）/ shared 公开空间（全员可读）
    visibility: Literal["shared", "private"] = "private"


class KnowledgeBaseUpdateRequest(KnowledgeBaseCreateRequest):
    pass


class KnowledgeBaseResponse(BaseModel):
    uid: str
    name: str
    description: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    # 知识库类型：shared（企业共享）/ private（私有）
    visibility: str = "private"
    # 当前登录用户对该知识库的有效权限：read / manage（无权限的库不会出现在列表中）
    permission: str | None = None
    # 知识检索调用频次
    retrieval_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class KnowledgeBaseStatsResponse(BaseModel):
    """知识库统计信息，用于删除等高危操作前的数据盘点。"""

    uid: str
    name: str
    # 包含文档数
    document_count: int
    # 向量切片总数
    chunk_count: int
    # 知识检索调用频次
    retrieval_count: int
    # 文档物理占用（字节，文档文件大小之和）
    storage_bytes: int


class KbDocCount(BaseModel):
    """单个知识库的文档计数（总/已索引/处理中）。"""

    kb_uid: str
    total: int
    indexed: int
    processing: int


class RecentDocumentItem(BaseModel):
    """最近解析的文档动态（供知识库页右侧栏展示）。"""

    uid: str
    title: str
    status: str
    kb_name: str
    created_at: datetime


class KnowledgeOverviewResponse(BaseModel):
    """知识库总览统计（当前用户可见范围内聚合）。"""

    kb_count: int
    total_docs: int
    indexed_docs: int
    processing_docs: int
    # 检索调用频次合计
    total_retrievals: int
    kb_doc_counts: list[KbDocCount]
    recent_documents: list[RecentDocumentItem]


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseResponse]
    total: int


class KnowledgeBasePermissionGrantRequest(BaseModel):
    """为指定用户授予知识库权限。"""

    user_uid: str = Field(min_length=1, max_length=36)
    # read 只读 / manage 可管理
    permission: Literal["read", "manage"] = "read"


class KnowledgeBasePermissionItem(BaseModel):
    """单条知识库授权记录（含被授权用户信息）。"""

    user_uid: str
    username: str
    nickname: str | None = None
    role: str
    # read 只读 / manage 可管理
    permission: str
    # 授权操作人显示名
    granted_by: str | None = None
    created_at: datetime


class KnowledgeBasePermissionListResponse(BaseModel):
    items: list[KnowledgeBasePermissionItem]
    total: int


class KnowledgeUserCandidate(BaseModel):
    """可被授权的用户候选项，用于前端搜索选择。"""

    uid: str
    username: str
    nickname: str | None = None
    role: str


class DocumentResponse(BaseModel):
    uid: str
    knowledge_base_uid: str | None = None
    title: str
    access_url:str | None = None
    # 源文件直链（docx 的 access_url 会指向解析后的 md，下载原文件用这个）
    source_url: str | None = None
    storage_path: str | None = None
    content_type: str | None = None
    file_size: int | None = None
    status: str
    error_message: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    stage_records:list[Dict[str, Any]] | None
    process_logs: list[Dict[str, Any]]

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


class DocumentProgressEvent(BaseModel):
    document_uid: str | None
    message: str
    timestamp:str
    status: str | None = None
    # 当前所处阶段（与 status 一致，单独下发便于前端把日志分组）
    stage: str | None = None
    # 当前阶段进度百分比 0-100，未知时为 None
    progress: int | None = None
    # 日志级别：info / success / warn / error
    level: str = "info"
    chunk_count: int | None = None
    vectorized_count: int | None = None
    stage_records:list[Dict[str, Any]] | None



class DocumentChunkResponse(BaseModel):
    id: int
    chunk_index: int
    content: str
    has_embedding: bool
    extra_meta: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


