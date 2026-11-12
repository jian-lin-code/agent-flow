
import asyncio
import io
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import UploadFile

from app.core.exceptions import BizException, ErrorCode
from app.events.document_progress import progress_broker
from app.models import User
from app.models.knowledge import Document, KnowledgeBase, DocumentStatus
from app.repository.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge import (
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBasePermissionGrantRequest,
    KnowledgeBasePermissionItem,
    KnowledgeBasePermissionListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseStatsResponse,
    KnowledgeOverviewResponse,
    KnowledgeBaseUpdateRequest,
    KnowledgeUserCandidate,
)
from app.utils.minio_client import build_object_url, get_minio_storage, parsed_md_object_name
from app.utils.cache import get_document_cache
from app.utils.datetime_helper import get_beijing_now_str
from app.utils.logger import logger

# 解析产物有效字符数低于该值时，认为 MinerU 没提出可用内容（空文档 / 扫描件 OCR 失败），
# 预览回退到原文件，避免给用户展示一页残缺的 md。
MIN_PARSED_MARKDOWN_CHARS = 100


def _has_enough_text(markdown: str) -> bool:
    """判断解析产物是否具备可预览的有效内容（忽略空白与 Markdown 标记）。"""
    visible = re.sub(r"[\s#>*_`|~\-\[\]()]+", "", markdown)

    return len(visible) >= MIN_PARSED_MARKDOWN_CHARS


class KnowledgeService:
    """知识库及知识文档业务服务。"""

    def __init__(self, repository: KnowledgeRepository):
        """初始化知识库服务及其依赖。"""
        self.repository = repository
        self.SUPPORTED_SUFFIXES = {"pdf", "docx", "md", "txt"}
        self.minio_client = get_minio_storage()
        self.local_cache = get_document_cache()

    # ==================== 知识库管理 ====================

    async def create_knowledge_base(
        self,
        data: KnowledgeBaseCreateRequest,
        current_user: User,
    ) -> KnowledgeBaseResponse:
        """创建私有知识库，并记录创建者的用户主键。"""
        name = data.name.strip()

        if not name:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="知识库名称不能为空",
            )

        if await self.repository.get_by_name(name):
            raise BizException(
                code=ErrorCode.CONFLICT,
                msg=f"知识库「{name}」已存在",
            )

        kb = KnowledgeBase(
            name=name,
            description=data.description.strip() if data.description else None,
            created_by=current_user.nickname or current_user.username,
            created_by_user_id=current_user.id,
            # private 受限空间（默认）/ shared 公开空间（全员可读，创建者保留管理权）
            visibility=data.visibility,
        )

        kb = await self.repository.create_knowledge_base(kb)

        # 创建者自动成为所有者，拥有 manage 权限
        return KnowledgeBaseResponse.model_validate(kb).model_copy(
            update={"permission": "manage"}
        )

    async def get_knowledge_overview(
        self,
        current_user: User,
    ) -> KnowledgeOverviewResponse:
        """知识库总览统计：当前用户可见范围内的文档/索引/检索频次聚合与最近解析动态。"""
        data = await self.repository.get_kb_overview(
            user_id=current_user.id,
            user_role=current_user.role,
        )
        return KnowledgeOverviewResponse(
            kb_count=data["kb_count"],
            total_docs=data["total_docs"],
            indexed_docs=data["indexed_docs"],
            processing_docs=data["processing_docs"],
            total_retrievals=data["total_retrievals"],
            kb_doc_counts=data["kb_doc_counts"],
            recent_documents=data["recent_documents"],
        )

    async def list_knowledge_bases(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> KnowledgeBaseListResponse:
        """分页查询当前用户有权访问的知识库。"""
        offset = (page - 1) * page_size

        if current_user.role == "admin":
            # admin 可以查看全部知识库，且全部拥有 manage 权限
            total = await self.repository.count_knowledge_bases()

            items = await self.repository.list_knowledge_bases(
                offset,
                page_size,
            )
            granted: dict[int, str] | None = {}
        else:
            # employee 只能查看共享、自己创建或被授权的知识库
            total = await self.repository.count_accessible_knowledge_bases(
                user_id=current_user.id,
            )

            items = await self.repository.list_accessible_knowledge_bases(
                user_id=current_user.id,
                offset=offset,
                limit=page_size,
            )
            # 一次查出该用户全部授权，避免逐条查询
            granted = await self.repository.list_user_kb_permissions(
                user_id=current_user.id,
            )

        return KnowledgeBaseListResponse(
            items=[
                await self._kb_response(
                    knowledge_base=item,
                    current_user=current_user,
                    granted=granted,
                )
                for item in items
            ],
            total=total,
        )

    async def get_knowledge_base(
        self,
        kb_uid: str,
        current_user: User,
    ) -> KnowledgeBaseResponse:
        """获取指定知识库详情，并检查读取权限。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="read",
        )

        return await self._kb_response(knowledge_base=kb, current_user=current_user)

    async def update_knowledge_base(
        self,
        kb_uid: str,
        data: KnowledgeBaseUpdateRequest,
        current_user: User,
    ) -> KnowledgeBaseResponse:
        """更新知识库信息，并检查管理权限。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="manage",
        )

        name = data.name.strip()

        if not name:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="知识库名称不能为空",
            )

        existing = await self.repository.get_by_name(name)

        if existing is not None and existing.id != kb.id:
            raise BizException(
                code=ErrorCode.CONFLICT,
                msg=f"知识库「{name}」已存在",
            )

        kb.name = name
        kb.description = (
            data.description.strip()
            if data.description
            else None
        )

        kb = await self.repository.update_knowledge_base(kb)

        # 能走到这里的用户必然拥有 manage 权限
        return KnowledgeBaseResponse.model_validate(kb).model_copy(
            update={"permission": "manage"}
        )

    async def delete_knowledge_base(
        self,
        kb_uid: str,
        current_user: User,
    ) -> None:
        """删除知识库及其关联文档，并检查管理权限。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="manage",
        )

        await self.repository.delete_knowledge_base(kb)

    async def get_knowledge_base_stats(
        self,
        kb_uid: str,
        current_user: User,
    ) -> KnowledgeBaseStatsResponse:
        """获取知识库统计信息（文档数/分块数/检索调用频次/物理占用），需读取权限。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="read",
        )

        stats = await self.repository.get_kb_stats(kb.id)

        return KnowledgeBaseStatsResponse(
            uid=kb.uid,
            name=kb.name,
            document_count=stats["document_count"],
            chunk_count=stats["chunk_count"],
            retrieval_count=kb.retrieval_count,
            storage_bytes=stats["storage_bytes"],
        )

    # ==================== 授权管理 ====================

    def _user_display_name(self, user: User | None) -> str | None:
        """返回用户显示名：优先昵称，其次账号。"""
        if user is None:
            return None

        return user.nickname or user.username

    def _permission_item(self, record) -> KnowledgeBasePermissionItem:
        """将授权记录 ORM 对象转换为响应项。"""
        user = record.user

        return KnowledgeBasePermissionItem(
            user_uid=user.uid,
            username=user.username,
            nickname=user.nickname,
            role=user.role,
            permission=record.permission,
            granted_by=self._user_display_name(record.granted_by),
            created_at=record.created_at,
        )

    async def list_permissions(
        self,
        kb_uid: str,
        current_user: User,
    ) -> KnowledgeBasePermissionListResponse:
        """获取知识库授权列表，仅管理者可见。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="manage",
        )

        records = await self.repository.list_kb_permissions(kb.id)

        # 用户可能已被删除（外键级联会一并删除授权），这里做一次防御性过滤
        items = [
            self._permission_item(record)
            for record in records
            if record.user is not None
        ]

        return KnowledgeBasePermissionListResponse(
            items=items,
            total=len(items),
        )

    async def grant_permission(
        self,
        kb_uid: str,
        data: KnowledgeBasePermissionGrantRequest,
        current_user: User,
    ) -> KnowledgeBasePermissionItem:
        """为用户授予知识库权限；已存在授权时更新权限级别。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="manage",
        )

        # 共享知识库对所有员工可读，单独授权没有意义（也无法提权到 manage）
        if kb.visibility == "shared":
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="企业共享知识库对全员可读，无需单独授权",
            )

        user = await self.repository.get_user_by_uid(data.user_uid)

        if user is None:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="用户不存在",
            )

        if not user.is_active:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="该用户已停用，无法授权",
            )

        if user.id == kb.created_by_user_id:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="知识库创建者默认拥有管理权限，无需重复授权",
            )

        if user.id == current_user.id:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="无需为当前操作人授权",
            )

        record = await self.repository.upsert_kb_permission(
            knowledge_base_id=kb.id,
            user_id=user.id,
            permission=data.permission,
            granted_by_user_id=current_user.id,
        )

        return KnowledgeBasePermissionItem(
            user_uid=user.uid,
            username=user.username,
            nickname=user.nickname,
            role=user.role,
            permission=record.permission,
            granted_by=self._user_display_name(current_user),
            created_at=record.created_at,
        )

    async def revoke_permission(
        self,
        kb_uid: str,
        user_uid: str,
        current_user: User,
    ) -> None:
        """撤销用户对知识库的授权。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="manage",
        )

        user = await self.repository.get_user_by_uid(user_uid)

        if user is None:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="用户不存在",
            )

        if user.id == kb.created_by_user_id:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="知识库创建者的管理权限不可撤销",
            )

        deleted = await self.repository.delete_kb_permission(
            knowledge_base_id=kb.id,
            user_id=user.id,
        )

        if not deleted:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="该用户未被授权访问此知识库",
            )

    async def search_permission_candidates(
        self,
        kb_uid: str,
        current_user: User,
        keyword: str | None = None,
    ) -> list[KnowledgeUserCandidate]:
        """搜索可被授权的用户，仅管理者可用。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="manage",
        )

        users = await self.repository.search_users(keyword)

        return [
            KnowledgeUserCandidate(
                uid=user.uid,
                username=user.username,
                nickname=user.nickname,
                role=user.role,
            )
            for user in users
            # 创建者天然拥有管理权限，无需出现在候选列表中
            if user.id != kb.created_by_user_id
        ]

    async def search_grantable_users(
        self,
        keyword: str | None = None,
    ) -> list[KnowledgeUserCandidate]:
        """搜索可授权用户（创建知识库时预选成员，此时知识库尚不存在）。"""
        users = await self.repository.search_users(keyword)

        return [
            KnowledgeUserCandidate(
                uid=user.uid,
                username=user.username,
                nickname=user.nickname,
                role=user.role,
            )
            for user in users
        ]

    # ==================== 文档管理 ====================

    def _safe_filename(self, filename: str) -> str:
        """提取安全文件名并校验文件后缀。"""
        # 同时兼容 Windows 和 Linux 风格的路径分隔符
        filename = (filename or "document").replace("\\", "/")
        name = PurePosixPath(filename).name

        suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""

        if suffix not in self.SUPPORTED_SUFFIXES:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="仅支持 PDF、DOCX、MD、TXT 文件",
            )

        stem_part = name.rsplit(".", 1)[0] if "." in name else name

        bad_chars = r'\/:*?"<>|'
        stem_part = stem_part.replace(" ", "").replace("　", "")

        for char in bad_chars:
            stem_part = stem_part.replace(char, "")

        if suffix:
            safe_name = f"{stem_part}.{suffix}"
        else:
            safe_name = stem_part

        return safe_name

    async def upload_document(
        self,
        kb_uid: str,
        file: UploadFile,
        current_user: User,
    ) -> Document:
        """向指定知识库上传文档，并检查知识库管理权限。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="manage",
        )

        filename = self._safe_filename(file.filename)

        content = await file.read()

        if not content:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="上传文件不能为空",
            )

        # MinIO 对象路径使用对外 uid，不暴露数据库自增 id
        object_name = (
            f"knowledge/{kb.uid}/"
            f"{datetime.now(timezone.utc):%Y/%m}/"
            f"{uuid4().hex}_{filename}"
        )

        # 上传 MinIO
        try:
            await self.minio_client.upload(
                object_name,
                content,
                file.content_type,
            )
        except Exception as exc:
            raise BizException(
                code=ErrorCode.INTERNAL_ERROR,
                msg=f"MinIO 上传失败：{exc}",
            ) from exc

        # 供前端访问的 URL
        access_url = build_object_url(object_name)

        document = Document(
            knowledge_base_id=kb.id,
            title=filename,
            access_url=access_url,
            storage_path=object_name,
            content_type=file.content_type,
            file_size=len(content),
            status=DocumentStatus.PENDING.value,
            created_by=current_user.nickname or current_user.username,
            stage_records=[
                {
                    "stage": DocumentStatus.PENDING.value,
                    "finished_at": get_beijing_now_str(),
                }
            ],
        )

        document = await self.repository.create_document(document)

        # 写入本地缓存，供后续文档处理任务使用
        await self.local_cache.write(
            document.uid,
            filename,
            content,
        )

        # 返回 ORM 模型，路由需要内部 id 用于 ARQ 入队
        # 前端响应仍然不暴露数据库自增 id
        return document

    async def list_documents(
        self,
        kb_uid: str,
        current_user: User,
        page: int = 1,
        page_size: int = 100,
    ) -> DocumentListResponse:
        """分页查询指定知识库中的文档，并检查读取权限。"""
        kb = await self._get_kb(kb_uid)

        await self._check_kb_permission(
            knowledge_base=kb,
            current_user=current_user,
            required="read",
        )

        offset = (page - 1) * page_size

        items = await self.repository.list_documents(
            kb.id,
            offset,
            page_size,
        )

        total = await self.repository.count_documents(kb.id)

        return DocumentListResponse(
            items=[
                await self._document_response(item)
                for item in items
            ],
            total=total,
        )

    async def get_document(
        self,
        document_uid: str,
        current_user: User,
    ) -> DocumentResponse:
        """获取指定文档详情，并检查所属知识库的读取权限。"""
        document = await self._get_document(document_uid)

        await self._check_kb_permission(
            knowledge_base=document.knowledge_base,
            current_user=current_user,
            required="read",
        )

        return await self._document_response(document)

    # ==================== 文档预览 ====================

    async def get_document_preview(
        self,
        document_uid: str,
        current_user: User,
    ) -> dict:
        """返回文档预览内容，并按格式选择渲染方式。

        - docx：优先渲染 MinerU 产出的 Markdown，未解析完成时回退 mammoth 转 HTML；
        - pdf ：优先渲染同一份 Markdown（与切片行号同源），解析缺失时回退原生 PDF；
        - md/txt：下发纯文本，前端用 marked 渲染；
        - 其他格式：返回 none，前端展示"暂不支持预览"并引导下载。
        """
        document = await self._get_document(document_uid)
        await self._check_kb_permission(
            knowledge_base=document.knowledge_base,
            current_user=current_user,
            required="read",
        )
        suffix = PurePosixPath(document.title or "").suffix.lower()

        if suffix == ".pdf":
            # 预览必须与切片同源：切片的行号记的是 MinerU 产出的 md，只有渲染 md
            # 用户才能顺着一句引用定位到原文。原 PDF 仍通过 source_url 提供下载/查看。
            markdown = await self._read_parsed_markdown(document)
            if markdown and _has_enough_text(markdown):
                return {"kind": "markdown", "content": markdown}
            # 尚未解析完成，或 OCR 几乎没提出内容（扫描件失败 / 空文档）：回退原生 PDF
            response = await self._document_response(document)
            return {"kind": "pdf", "url": response.source_url or response.access_url}

        if suffix in {".md", ".txt"}:
            content = await self._read_document_text(document)
            if content is None:
                return {"kind": "none", "reason": "源文件读取失败"}
            return {"kind": "markdown", "content": content}

        if suffix == ".docx":
            # 优先使用 worker 解析时落库的 Markdown（MinerU 产物，排版最还原）
            markdown = await self._read_parsed_markdown(document)
            if markdown:
                return {"kind": "markdown", "content": markdown}
            # 尚未解析完成时回退到 mammoth 转 HTML
            html = await self._render_docx_html(document)
            if html is None:
                return {"kind": "none", "reason": "文档解析失败，请下载后查看"}
            return {"kind": "html", "html": html}

        return {"kind": "none", "reason": f"暂不支持预览 {suffix or '该格式'}"}

    async def _read_document_text(self, document: Document) -> str | None:
        data = await self._read_document_bytes(document)
        if data is None:
            return None
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    async def _read_document_bytes(self, document: Document) -> bytes | None:
        if not document.storage_path:
            return None
        try:
            return await self.minio_client.download(document.storage_path)
        except Exception as exc:
            logger.warning("读取文档源文件失败 %s: %s", document.uid, exc)
            return None

    async def _read_parsed_markdown(self, document: Document) -> str | None:
        """读取解析产物 Markdown（worker 上传到对象存储，docx/pdf 的 access_url 指向它）。"""
        try:
            data = await self.minio_client.download(parsed_md_object_name(document.uid))
        except Exception:
            return None
        if not data:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")

    async def _render_docx_html(self, document: Document) -> str | None:
        """把 docx 渲染为 HTML，结果按（uid + 更新时间）缓存 1 小时。

        未索引的文档也会被预览，转换一次的成本（几十到几百毫秒）不必每次重付。
        """
        cache_key = f"doc_preview:{document.uid}:{int(document.updated_at.timestamp())}"
        redis = progress_broker.redis
        try:
            cached = await redis.get(cache_key)
            if cached:
                return cached
        except Exception:
            pass

        data = await self._read_document_bytes(document)
        if not data:
            return None

        try:
            html = await asyncio.to_thread(self._docx_bytes_to_html, data)
        except Exception as exc:
            logger.warning("docx 转 HTML 失败 %s: %s", document.uid, exc)
            return None

        try:
            await redis.set(cache_key, html, ex=3600)
        except Exception:
            pass
        return html

    @staticmethod
    def _docx_bytes_to_html(data: bytes) -> str:
        """docx -> HTML。mammoth 会把图片内联成 data URI，无需再走对象存储。"""
        import mammoth

        with io.BytesIO(data) as buffer:
            result = mammoth.convert_to_html(buffer)
        messages = [f"{m.type}: {m.message}" for m in result.messages[:5]]
        if messages:
            logger.debug("docx 转换提示 %s", messages)
        return KnowledgeService._sanitize_html(result.value)

    @staticmethod
    def _sanitize_html(html_text: str) -> str:
        """docx 里可能夹带脚本/事件属性，渲染前做一次白名单式清理。"""
        cleaned = re.sub(
            r"<(script|style|iframe|object|embed)\b[^>]*>.*?</\1>",
            "",
            html_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(
            r"<(script|style|iframe|object|embed)\b[^>]*/?>",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2",
            r"\1=\2#\2",
            cleaned,
            flags=re.IGNORECASE,
        )
        return cleaned

    async def list_chunks(
        self,
        document_uid: str,
        current_user: User,
    ) -> list[DocumentChunkResponse]:
        """查询指定文档的文本分块，并检查读取权限。"""
        document = await self._get_document(document_uid)

        await self._check_kb_permission(
            knowledge_base=document.knowledge_base,
            current_user=current_user,
            required="read",
        )

        chunks = await self.repository.list_chunks(document.id)

        return [
            DocumentChunkResponse(
                id=chunk.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                has_embedding=chunk.embedding is not None,
                extra_meta=chunk.extra_meta,
                created_at=chunk.created_at,
            )
            for chunk in chunks
            if chunk.is_parent is not True
        ]

    async def reprocess_document(
        self,
        document_uid: str,
        current_user: User,
    ) -> Document:
        """重新处理指定文档：重置处理状态，并检查所属知识库的管理权限。

        返回 ORM 对象（路由层需要内部自增 id 投递 ARQ 任务），
        响应组装由路由层调用 document_response 完成。
        """
        document = await self._get_document(document_uid)

        await self._check_kb_permission(
            knowledge_base=document.knowledge_base,
            current_user=current_user,
            required="manage",
        )

        document.status = DocumentStatus.PENDING.value
        document.error_message = None
        document.process_logs = []
        document.stage_records = []


        return await self.repository.update_document(document)

    async def document_response(self, document: Document) -> DocumentResponse:
        """公开的文档响应组装（供路由层在投递任务后返回响应）。"""
        return await self._document_response(document)

    async def delete_document(
        self,
        document_uid: str,
        current_user: User,
    ) -> None:
        """删除指定文档及其 MinIO 对象，并检查管理权限。"""
        document = await self._get_document(document_uid)

        await self._check_kb_permission(
            knowledge_base=document.knowledge_base,
            current_user=current_user,
            required="manage",
        )

        if document.storage_path:
            try:
                await self.minio_client.remove(document.storage_path)
            except Exception:
                # MinIO 删除失败不影响数据库删除流程，沿用原有行为
                pass

        # Word 解析产物 md 与源文件一起清理，避免对象存储残留
        try:
            await self.minio_client.remove(parsed_md_object_name(document.uid))
        except Exception:
            pass

        await self.repository.delete_document(document)

    # ==================== 权限检查 ====================

    def _effective_permission(
        self,
        knowledge_base: KnowledgeBase,
        current_user: User,
        granted: dict[int, str] | None = None,
    ) -> str | None:
        """计算当前用户对知识库的有效权限（read / manage / None）。

        granted 传入批量授权映射时直接查表，避免列表场景的 N+1 查询。
        """
        # admin 拥有全局管理权限
        if current_user.role == "admin":
            return "manage"

        # 企业共享知识库：employee 只读
        if knowledge_base.visibility == "shared":
            return "read"

        # 私有知识库创建者即所有者
        if knowledge_base.created_by_user_id == current_user.id:
            return "manage"

        if granted is not None:
            return granted.get(knowledge_base.id)

        return None

    async def _kb_response(
        self,
        knowledge_base: KnowledgeBase,
        current_user: User,
        granted: dict[int, str] | None = None,
    ) -> KnowledgeBaseResponse:
        """组装知识库响应，附带当前用户的有效权限。"""
        permission = self._effective_permission(
            knowledge_base=knowledge_base,
            current_user=current_user,
            granted=granted,
        )

        # 未传入批量映射时，单独查询一次授权记录
        if permission is None and granted is None:
            record = await self.repository.get_user_kb_permission(
                knowledge_base_id=knowledge_base.id,
                user_id=current_user.id,
            )
            permission = record.permission if record is not None else None

        return KnowledgeBaseResponse.model_validate(knowledge_base).model_copy(
            update={"permission": permission}
        )

    async def _check_kb_permission(
        self,
        knowledge_base: KnowledgeBase,
        current_user: User,
        required: str = "read",
    ) -> None:
        """检查用户是否具有指定知识库的读取或管理权限。"""
        if required not in {"read", "manage"}:
            raise ValueError(f"Unsupported permission: {required}")

        # admin 拥有所有知识库的全局管理权限
        if current_user.role == "admin":
            return

        # 共享知识库对 employee 开放读取，但不开放管理
        if knowledge_base.visibility == "shared":
            if required == "read":
                return

            raise BizException(
                code=ErrorCode.FORBIDDEN,
                msg="无权管理企业共享知识库",
            )

        # 私有知识库创建者默认拥有管理权限
        if knowledge_base.created_by_user_id == current_user.id:
            return

        # 查询当前用户的授权记录
        permission = await self.repository.get_user_kb_permission(
            knowledge_base_id=knowledge_base.id,
            user_id=current_user.id,
        )

        if permission is None:
            raise BizException(
                code=ErrorCode.FORBIDDEN,
                msg="无权访问该知识库",
            )

        # manage 权限同时包含 read
        if permission.permission == "manage":
            return

        # read 权限只允许读取操作
        if required == "read" and permission.permission == "read":
            return

        raise BizException(
            code=ErrorCode.FORBIDDEN,
            msg="当前知识库授权权限不足",
        )

    # ==================== 内部查询与响应组装 ====================

    async def _get_kb(self, kb_uid: str) -> KnowledgeBase:
        """根据知识库 UID 获取知识库，不存在时抛出异常。"""
        kb = await self.repository.get_knowledge_base_by_uid(kb_uid)

        if kb is None:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="知识库不存在",
            )

        return kb

    async def _get_document(self, document_uid: str) -> Document:
        """根据文档 UID 获取文档，不存在时抛出异常。"""
        document = await self.repository.get_document_by_uid(document_uid)

        if document is None:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="文档不存在",
            )

        return document

    async def _document_response(
        self,
        document: Document,
    ) -> DocumentResponse:
        """将文档 ORM 对象转换为前端响应，并补充分块统计信息。"""
        total, vectorized = await self.repository.get_chunk_counts(
            document.id,
        )

        response = DocumentResponse.model_validate(document)
        response.knowledge_base_uid = document.knowledge_base.uid
        # 源文件直链：docx/pdf 的 access_url 已被替换为解析后的 md，下载源文件仍走 storage_path
        response.source_url = (
            build_object_url(document.storage_path) if document.storage_path else None
        )

        return response.model_copy(
            update={
                "chunk_count": total,
                "vectorized_count": vectorized,
            }
        )
