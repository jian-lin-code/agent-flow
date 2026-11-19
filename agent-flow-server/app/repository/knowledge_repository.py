
from typing import Any

from sqlalchemy import delete, func, or_, select, true, update, text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.models.knowledge import (
    Document,
    DocumentChunk,
    KnowledgeBase,
    KnowledgeBasePermission, DocumentStatus,
)
from app.models.user import User
from app.utils.logger import logger


class KnowledgeRepository:
    """知识库、文档及文档分块的数据访问层。"""

    def __init__(self, session: AsyncSession):
        """初始化 Repository，接收当前请求或任务使用的数据库会话。"""
        self.session = session

    # ==================== 知识库相关 ====================

    async def create_knowledge_base(
        self,
        kb: KnowledgeBase,
    ) -> KnowledgeBase:
        """创建知识库，提交事务并刷新数据库生成的字段。"""
        self.session.add(kb)
        await self.session.commit()
        await self.session.refresh(kb)
        return kb

    async def get_by_name(
        self,
        name: str,
    ) -> KnowledgeBase | None:
        """根据知识库名称查询知识库，用于检查名称是否重复。"""
        query = select(KnowledgeBase).where(
            KnowledgeBase.name == name
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_knowledge_base(
        self,
        kb_id: int,
    ) -> KnowledgeBase | None:
        """根据数据库主键查询知识库。"""
        query = select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_knowledge_base_by_uid(
        self,
        kb_uid: str,
    ) -> KnowledgeBase | None:
        """根据对外使用的知识库 UID 查询知识库。"""
        query = select(KnowledgeBase).where(
            KnowledgeBase.uid == kb_uid
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_kb_permission(
        self,
        knowledge_base_id: int,
        user_id: int,
    ) -> KnowledgeBasePermission | None:
        """查询指定用户对指定知识库的授权记录。"""
        query = select(KnowledgeBasePermission).where(
            KnowledgeBasePermission.knowledge_base_id == knowledge_base_id,
            KnowledgeBasePermission.user_id == user_id,
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_user_kb_permissions(
        self,
        user_id: int,
    ) -> dict[int, str]:
        """批量查询用户对所有知识库的授权：返回 {知识库 ID: read|manage}。"""
        query = select(
            KnowledgeBasePermission.knowledge_base_id,
            KnowledgeBasePermission.permission,
        ).where(KnowledgeBasePermission.user_id == user_id)

        rows = (await self.session.execute(query)).all()
        return {kb_id: permission for kb_id, permission in rows}


    # 在用户有权访问的全部知识库中执行混合检索
    async def search_similar_child_chunks(
            self,
            query_embedding: list[float],
            query: str,
            user_id: int,
            user_role: str,
            top_k: int = 30,
    ) -> list[dict]:
        """
        混合检索：向量 + 全文（基于 RRF 融合）
        """
        top_k = max(1, min(top_k, 100))

        # RRF 融合时，每路取更多的候选集（比如 60）
        candidate_limit = max(60, top_k * 3)

        # 基础条件（向量路与全文路共用）
        # status 兼容历史数据：早期入库写的是枚举 name（'INDEXED'），现在写 value（'indexed'），
        # 统一按 lower() 比较，避免存量文档被整表过滤掉。
        base_where = """
            dc.is_parent = false
            AND lower(d.status) = 'indexed'
        """

        # 向量路必须要有向量；全文路只要有 fts，不要求 embedding
        vector_where = f"{base_where} AND dc.embedding IS NOT NULL"
        text_where = f"{base_where} AND dc.fts IS NOT NULL"

        # 如果是 employee，把权限判断加进 SQL
        permission_where = ""
        query_params = {
            "embedding": query_embedding,
            "query": query,
            "limit": candidate_limit,
            "top_k": top_k,
        }

        if user_role == "employee":
            permission_where = """
            AND (
                kb.visibility = 'shared'
                OR kb.created_by_user_id = :user_id
                OR EXISTS (
                    SELECT 1 FROM knowledge_base_permissions p
                    WHERE p.knowledge_base_id = kb.id
                    AND p.user_id = :user_id
                )
            )
            """
            query_params["user_id"] = user_id

        # 构造双路召回 + RRF 融合的纯 SQL
        #
        # 全文路的 tsquery 用「OR 语义」而非常见的 AND / 短语语义：
        # plainto_tsquery 产出 'a' & 'b' & 'c'，要求同一块同时包含全部词，
        # 一个自然语言问句切出七八个词后几乎不可能命中；改成 'a' | 'b' | 'c' 后
        # 任一关键词命中即可召回，再由 ts_rank_cd 按命中密度排序。
        # 纯标点等无法分词的情况会得到空 tsquery，NULLIF 置空后全文路整体跳过。
        # MATERIALIZED 是为了让两路候选集只算一次（计数与反查都要用）。
        sql = text(f"""
            WITH q AS MATERIALIZED (
                SELECT CAST(
                    NULLIF(
                        replace(
                            CAST(plainto_tsquery('public.chinese', :query) AS text),
                            ' & ', ' | '
                        ),
                        ''
                    ) AS tsquery
                ) AS tsq
            ),
            vector_search AS MATERIALIZED (
                SELECT dc.id, ROW_NUMBER() OVER (ORDER BY dc.embedding <=> :embedding) AS rank
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                WHERE {vector_where} {permission_where}
                ORDER BY dc.embedding <=> :embedding
                LIMIT :limit
            ),
            text_search AS MATERIALIZED (
                SELECT dc.id, ROW_NUMBER() OVER (
                    ORDER BY ts_rank_cd(dc.fts, q.tsq) DESC
                ) AS rank
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                CROSS JOIN q
                WHERE {text_where}
                  AND q.tsq IS NOT NULL
                  AND dc.fts @@ q.tsq
                  {permission_where}
                ORDER BY ts_rank_cd(dc.fts, q.tsq) DESC
                LIMIT :limit
            ),
            fused AS (
                SELECT
                    COALESCE(v.id, t.id) AS chunk_id,
                    -- RRF 公式：1 / (k + rank)，k 取 60
                    COALESCE(1.0 / (60 + v.rank), 0.0)
                        + COALESCE(1.0 / (60 + t.rank), 0.0) AS rrf_score
                FROM vector_search v
                FULL OUTER JOIN text_search t ON v.id = t.id
                ORDER BY rrf_score DESC
                LIMIT :top_k
            )
            SELECT
                f.chunk_id,
                f.rrf_score,
                -- 真实的向量余弦相似度，供上层做阈值判断；
                -- 不能用 rrf_score 冒充 similarity（量级只有 0~0.033）。
                COALESCE(1 - (dc.embedding <=> :embedding), 0) AS vector_similarity,
                (SELECT count(*) FROM vector_search) AS vector_hits,
                (SELECT count(*) FROM text_search) AS text_hits,
                d.title AS document_title,
                kb.id AS knowledge_base_id,
                kb.uid AS knowledge_base_uid,
                kb.name AS knowledge_base_name
            FROM fused f
            JOIN document_chunks dc ON dc.id = f.chunk_id
            JOIN documents d ON d.id = dc.document_id
            JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
            ORDER BY f.rrf_score DESC;
        """).bindparams(bindparam("embedding", type_=Vector(settings.EMBEDDING_DIMENSION)))

        # 执行原生 SQL
        result = await self.session.execute(sql, query_params)
        rows = result.all()

        if rows:
            logger.info(
                "混合检索完成：query=%r vector_hits=%d text_hits=%d fused=%d",
                query, rows[0].vector_hits, rows[0].text_hits, len(rows),
            )
        else:
            # 两路都没结果时，把分词结果打出来，避免下次还要连库排查。
            # 这里打印的是实际参与检索的 OR 版 tsquery（与主查询保持一致）。
            tsq = (
                await self.session.execute(
                    text(
                        "SELECT CAST(NULLIF(replace("
                        "CAST(plainto_tsquery('public.chinese', :q) AS text),"
                        " ' & ', ' | '), '') AS text) AS tsq"
                    ),
                    {"q": query},
                )
            ).scalar_one_or_none()
            logger.warning(
                "混合检索无结果：query=%r tsquery=%r vector_hits=0 text_hits=0 "
                "（tsquery 为空说明问题被分词器过滤干净；否则检查文档是否已索引）",
                query, tsq,
            )

        # 提取 chunk_id 列表和命中的知识库
        chunk_ids = [row.chunk_id for row in rows]
        hit_kb_ids = sorted({row.knowledge_base_id for row in rows})

        if hit_kb_ids:
            await self.increment_retrieval_counts(hit_kb_ids)

        # 去库中捞取完整的 ORM 对象（保持返回值结构一致）
        chunk_map = {}
        if chunk_ids:
            chunk_stmt = select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
            chunk_result = await self.session.execute(chunk_stmt)
            chunk_map = {c.id: c for c in chunk_result.scalars().all()}

        # 组装返回结果
        final_results = []
        for row in rows:
            # chunk 理论上一定存在（fused 由 chunk id 反查而来），
            # 但并发删除时可能已被清理，交给上层按 None 过滤
            chunk = chunk_map.get(row.chunk_id)
            if chunk is None:
                continue

            final_results.append({
                "chunk": chunk,
                "document_title": row.document_title,
                "knowledge_base_uid": row.knowledge_base_uid,
                "knowledge_base_name": row.knowledge_base_name,
                "rrf_score": float(row.rrf_score),
                # 相似度保留向量余弦值（0~1），不要用 RRF 分数冒充
                "similarity": float(row.vector_similarity),
            })

        return final_results

    async def increment_retrieval_counts(self, kb_ids: list[int]) -> None:
        """批量自增知识库检索调用频次并提交事务。"""
        await self.session.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id.in_(kb_ids))
            .values(retrieval_count=KnowledgeBase.retrieval_count + 1)
        )
        await self.session.commit()

    async def get_kb_stats(self, kb_id: int) -> dict:
        """统计知识库的文档数、分块数与物理占用（文档文件大小之和）。"""
        doc_stats = await self.session.execute(
            select(
                func.count(Document.id),
                func.coalesce(func.sum(Document.file_size), 0),
            ).where(Document.knowledge_base_id == kb_id)
        )
        document_count, storage_bytes = doc_stats.one()

        chunk_stats = await self.session.execute(
            select(func.count(DocumentChunk.id))
            .select_from(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.knowledge_base_id == kb_id)
        )
        chunk_count = chunk_stats.scalar_one()

        return {
            "document_count": int(document_count),
            "chunk_count": int(chunk_count),
            "storage_bytes": int(storage_bytes),
        }

    async def get_kb_overview(self, user_id: int, user_role: str) -> dict:
        """知识库总览统计（当前用户可见范围内）：

        - 知识库数量 / 文档总数 / 已索引 / 处理中
        - 每个知识库的文档计数（列表页"文档数"列）
        - 检索调用频次合计
        - 最近解析的文档动态（供右侧栏展示）
        """
        # 可见范围与列表页保持一致：admin 全量；employee 只看共享/自建/被授权
        if user_role == "admin":
            visible = true()
        else:
            permission_exists = (
                select(KnowledgeBasePermission.knowledge_base_id)
                .where(
                    KnowledgeBasePermission.knowledge_base_id == KnowledgeBase.id,
                    KnowledgeBasePermission.user_id == user_id,
                )
                .exists()
            )
            visible = or_(
                KnowledgeBase.visibility == "shared",
                KnowledgeBase.created_by_user_id == user_id,
                permission_exists,
            )

        # 每个知识库的文档计数（含状态分布），左连接保证空知识库也出现在结果里
        doc_stmt = (
            select(
                KnowledgeBase.id,
                KnowledgeBase.uid,
                KnowledgeBase.retrieval_count,
                func.count(Document.id).label("total"),
                func.count(Document.id)
                .filter(Document.status == DocumentStatus.INDEXED)
                .label("indexed"),
                func.count(Document.id)
                .filter(
                    Document.status.notin_([DocumentStatus.INDEXED, DocumentStatus.FAILED])
                )
                .label("processing"),
            )
            .join(Document, Document.knowledge_base_id == KnowledgeBase.id, isouter=True)
            .where(visible)
            .group_by(KnowledgeBase.id)
        )
        doc_rows = (await self.session.execute(doc_stmt)).all()

        kb_doc_counts = [
            {
                "kb_uid": row.uid,
                "total": int(row.total),
                "indexed": int(row.indexed),
                "processing": int(row.processing),
            }
            for row in doc_rows
        ]

        # 最近解析的文档动态（去 failed 噪音？不，失败也展示，方便发现解析问题）
        recent_stmt = (
            select(
                Document.uid,
                Document.title,
                Document.status,
                Document.created_at,
                KnowledgeBase.name.label("kb_name"),
            )
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(visible)
            .order_by(Document.created_at.desc())
            .limit(5)
        )
        recent_rows = (await self.session.execute(recent_stmt)).all()
        recent_documents = [
            {
                "uid": row.uid,
                "title": row.title,
                "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                "kb_name": row.kb_name,
                "created_at": row.created_at,
            }
            for row in recent_rows
        ]

        return {
            "kb_count": len(kb_doc_counts),
            "total_docs": sum(item["total"] for item in kb_doc_counts),
            "indexed_docs": sum(item["indexed"] for item in kb_doc_counts),
            "processing_docs": sum(item["processing"] for item in kb_doc_counts),
            "total_retrievals": sum(int(row.retrieval_count or 0) for row in doc_rows),
            "kb_doc_counts": kb_doc_counts,
            "recent_documents": recent_documents,
        }

    # 根据子切片关联的父切片 ID 批量查询父切片
    async def get_document_uid_map(
        self,
        document_ids: list[int],
    ) -> dict[int, str]:
        """批量获取文档 uid，供引用来源跳转到原文使用。

        Args:
            document_ids: 文档主键列表。

        Returns:
            {文档主键: 文档 uid} 映射，缺失的 id 不会出现在结果中。
        """

        ids = list(dict.fromkeys(document_ids))

        if not ids:
            return {}

        stmt = select(Document.id, Document.uid).where(Document.id.in_(ids))

        rows = await self.session.execute(stmt)

        return {row[0]: row[1] for row in rows.all()}

    async def get_parent_chunks_by_ids(
        self,
        parent_ids: list[int],
        user_id: int,
        user_role: str,
    ) -> list[DocumentChunk]:
        """
        批量获取父切片。

        权限规则与向量检索保持一致：
        1. admin 可以查询全部父切片。
        2. employee 只能查询有权访问的知识库中的父切片。
        3. 未知角色不允许查询。
        """

        # 去重，避免重复查询相同父切片
        parent_ids = list(dict.fromkeys(parent_ids))

        # 构建父切片查询
        stmt = (
            select(DocumentChunk)
            .join(
                Document,
                Document.id == DocumentChunk.document_id,
            )
            .join(
                KnowledgeBase,
                KnowledgeBase.id == Document.knowledge_base_id,
            )
            .where(
                DocumentChunk.id.in_(parent_ids),
                DocumentChunk.is_parent.is_(True),
                Document.status == DocumentStatus.INDEXED,
            )
        )

        # employee 需要再次校验父切片所属知识库的访问权限
        if user_role == "employee":
            permission_exists = (
                select(KnowledgeBasePermission.knowledge_base_id)
                .where(
                    KnowledgeBasePermission.knowledge_base_id
                    == KnowledgeBase.id,
                    KnowledgeBasePermission.user_id == user_id,
                )
                .exists()
            )

            stmt = stmt.where(
                or_(
                    KnowledgeBase.visibility == "shared",
                    KnowledgeBase.created_by_user_id == user_id,
                    permission_exists,
                )
            )

        # 执行查询并返回父切片 ORM 对象
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ==================== 知识库授权管理 ====================

    async def list_kb_permissions(
        self,
        knowledge_base_id: int,
    ) -> list[KnowledgeBasePermission]:
        """查询指定知识库的全部授权记录，并预加载被授权人与授权人。"""
        query = (
            select(KnowledgeBasePermission)
            .options(
                selectinload(KnowledgeBasePermission.user),
                selectinload(KnowledgeBasePermission.granted_by),
            )
            .where(
                KnowledgeBasePermission.knowledge_base_id == knowledge_base_id
            )
            .order_by(
                KnowledgeBasePermission.created_at.asc(),
                KnowledgeBasePermission.id.asc(),
            )
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def upsert_kb_permission(
        self,
        knowledge_base_id: int,
        user_id: int,
        permission: str,
        granted_by_user_id: int | None,
    ) -> KnowledgeBasePermission:
        """新增或更新授权记录，返回最新的授权记录。"""
        record = await self.get_user_kb_permission(
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
        )

        if record is None:
            record = KnowledgeBasePermission(
                knowledge_base_id=knowledge_base_id,
                user_id=user_id,
                permission=permission,
                granted_by_user_id=granted_by_user_id,
            )
            self.session.add(record)
        else:
            record.permission = permission
            record.granted_by_user_id = granted_by_user_id

        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def delete_kb_permission(
        self,
        knowledge_base_id: int,
        user_id: int,
    ) -> bool:
        """删除授权记录，返回是否存在被删除的记录。"""
        record = await self.get_user_kb_permission(
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
        )

        if record is None:
            return False

        await self.session.delete(record)
        await self.session.commit()
        return True

    async def get_user_by_uid(
        self,
        user_uid: str,
    ) -> User | None:
        """根据用户对外 UID 查询用户。"""
        query = select(User).where(User.uid == user_uid)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def search_users(
        self,
        keyword: str | None,
        limit: int = 20,
    ) -> list[User]:
        """按账号 / 昵称模糊搜索启用中的用户，供授权选择使用。"""
        query = select(User).where(User.is_active.is_(True))

        if keyword and keyword.strip():
            like = f"%{keyword.strip()}%"
            query = query.where(
                or_(User.username.ilike(like), User.nickname.ilike(like))
            )

        query = query.order_by(User.id.asc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_accessible_knowledge_bases(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> list[KnowledgeBase]:
        """分页查询普通用户可访问的知识库。"""
        # 查询当前用户获得授权的知识库 ID
        permission_subquery = select(
            KnowledgeBasePermission.knowledge_base_id
        ).where(
            KnowledgeBasePermission.user_id == user_id
        )

        query = (
            select(KnowledgeBase)
            .where(
                or_(
                    # 企业共享知识库
                    KnowledgeBase.visibility == "shared",

                    # 用户自己创建的私有知识库
                    KnowledgeBase.created_by_user_id == user_id,

                    # 用户被授权访问的知识库
                    KnowledgeBase.id.in_(permission_subquery),
                )
            )
            .order_by(
                KnowledgeBase.updated_at.desc(),
                KnowledgeBase.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_accessible_knowledge_bases(
        self,
        user_id: int,
    ) -> int:
        """统计普通用户有权访问的知识库数量。"""
        # 查询当前用户获得授权的知识库 ID
        permission_subquery = select(
            KnowledgeBasePermission.knowledge_base_id
        ).where(
            KnowledgeBasePermission.user_id == user_id
        )

        query = (
            select(func.count())
            .select_from(KnowledgeBase)
            .where(
                or_(
                    KnowledgeBase.visibility == "shared",
                    KnowledgeBase.created_by_user_id == user_id,
                    KnowledgeBase.id.in_(permission_subquery),
                )
            )
        )

        result = await self.session.execute(query)
        return result.scalar_one()

    async def count_knowledge_bases(self) -> int:
        """统计数据库中全部知识库数量。"""
        query = select(func.count()).select_from(KnowledgeBase)
        result = await self.session.execute(query)
        return result.scalar_one()

    async def list_knowledge_bases(
        self,
        offset: int,
        limit: int,
    ) -> list[KnowledgeBase]:
        """分页查询全部知识库，供 admin 使用。"""
        query = (
            select(KnowledgeBase)
            .order_by(
                KnowledgeBase.updated_at.desc(),
                KnowledgeBase.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_knowledge_base(
        self,
        kb: KnowledgeBase,
    ) -> KnowledgeBase:
        """保存知识库更新，并刷新 ORM 对象。"""
        await self.session.commit()
        await self.session.refresh(kb)
        return kb

    async def delete_knowledge_base(
        self,
        kb: KnowledgeBase,
    ) -> None:
        """删除知识库并提交事务。"""
        await self.session.delete(kb)
        await self.session.commit()

    # ==================== 文档相关 ====================

    async def create_document(
        self,
        document: Document,
    ) -> Document:
        """创建文档记录，提交事务并刷新数据库生成的字段。"""
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def get_document(
        self,
        document_id: int,
    ) -> Document | None:
        """根据数据库主键查询文档，并预加载所属知识库。"""
        query = (
            select(Document)
            .options(selectinload(Document.knowledge_base))
            .where(Document.id == document_id)
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_document_by_uid(
        self,
        document_uid: str,
    ) -> Document | None:
        """根据对外使用的文档 UID 查询文档，并预加载所属知识库。"""
        query = (
            select(Document)
            .options(selectinload(Document.knowledge_base))
            .where(Document.uid == document_uid)
        )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        kb_id: int,
        offset: int,
        limit: int,
    ) -> list[Document]:
        """分页查询指定知识库中的文档，并预加载所属知识库。"""
        query = (
            select(Document)
            .options(selectinload(Document.knowledge_base))
            .where(Document.knowledge_base_id == kb_id)
            .order_by(Document.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_documents(
        self,
        kb_id: int,
    ) -> int:
        """统计指定知识库中的文档数量。"""
        query = (
            select(func.count())
            .select_from(Document)
            .where(Document.knowledge_base_id == kb_id)
        )

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update_document(
        self,
        document: Document,
    ) -> Document:
        """保存文档更新，并刷新 ORM 对象。"""
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def delete_document(
        self,
        document: Document,
    ) -> None:
        """删除文档记录并提交事务。"""
        await self.session.delete(document)
        await self.session.commit()

    # ==================== 文档分块相关 ====================

    async def delete_document_chunks(
        self,
        document_id: int,
    ) -> int:
        """删除指定文档的全部切块，返回删除数量。

        重新处理（reprocess）时必须先清掉旧切块：save_parent_child_chunks 只做追加，
        不清空会让同一次解析的结果落两份，检索时出现重复命中、chunk 数翻倍。
        """
        result = await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def save_parent_child_chunks(
        self,
        document_id: int,
        parents: list[dict[str, Any]],
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        保存父子切块，并将子切块的临时父 ID 映射为数据库 ID。

        不在此方法中 commit，由 Worker 统一管理事务。
        """
        # 临时父切块 ID -> 数据库父切块 ID
        parent_id_map: dict[Any, int] = {}

        try:
            # 1. 创建父切块 ORM 对象
            parent_models = [
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                    embedding=None,
                    extra_meta=chunk.get("metadata") or {},
                    is_parent=True,
                    parent_chunk_id=None,
                    source_start_line=chunk.get("source_start_line"),
                    source_end_line=chunk.get("source_end_line"),
                )
                for chunk in parents
            ]

            # 2. 批量插入父切块
            self.session.add_all(parent_models)
            await self.session.flush()

            # 3. 建立临时 ID 与数据库 ID 的映射
            for source, model in zip(parents, parent_models):
                temp_id = source.get("tmp_id")

                if temp_id is not None:
                    parent_id_map[temp_id] = model.id

            # 4. 创建子切块，并绑定数据库中的父切块 ID
            child_models = []

            for chunk in children:
                temp_parent_id = chunk.get("parent_id")
                db_parent_id = parent_id_map.get(temp_parent_id)

                if temp_parent_id is not None and db_parent_id is None:
                    raise ValueError(
                        f"找不到子切块对应的父切块：{temp_parent_id}"
                    )

                child_models.append(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_index=chunk["chunk_index"],
                        content=chunk["content"],
                        embedding=None,
                        extra_meta=chunk.get("metadata") or {},
                        is_parent=False,
                        parent_chunk_id=db_parent_id,
                        source_start_line=chunk.get("source_start_line"),
                        source_end_line=chunk.get("source_end_line"),
                    )
                )

            # 5. 批量插入子切块
            self.session.add_all(child_models)
            await self.session.flush()

            return {
                "parent_models": parent_models,
                "child_models": child_models,
            }

        except Exception:
            await self.session.rollback()
            raise

    async def bulk_update_embeddings(
        self,
        chunks_with_vectors: list[tuple[int, list[float]]],
    ) -> None:
        """批量更新文档切块的向量数据，不主动提交事务。"""
        if not chunks_with_vectors:
            return

        # 构建批量更新映射
        update_mappings = [
            {
                "id": chunk_id,
                "embedding": vector,
            }
            for chunk_id, vector in chunks_with_vectors
        ]

        # 使用 SQLAlchemy ORM 批量更新
        await self.session.execute(
            update(DocumentChunk),
            update_mappings,
        )

        # 保留外层事务控制权
        await self.session.flush()

    async def replace_chunks(
        self,
        document_id: int,
        chunks: list[DocumentChunk],
    ) -> None:
        """删除指定文档的旧切块，并批量保存新切块。"""
        await self.session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        )

        self.session.add_all(chunks)
        await self.session.commit()

    async def get_chunk_counts(
        self,
        document_id: int,
    ) -> tuple[int, int]:
        """统计指定文档的切块总数和已生成向量的切块数量。"""
        query = select(
            func.count(DocumentChunk.id),
            func.count(DocumentChunk.embedding),
        ).where(
            DocumentChunk.document_id == document_id
        )

        result = await self.session.execute(query)
        total, vectorized = result.one()

        return int(total), int(vectorized)

    async def list_chunks(
        self,
        document_id: int,
    ) -> list[DocumentChunk]:
        """查询指定文档的全部切块，并按照切块索引排序。"""
        query = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())
