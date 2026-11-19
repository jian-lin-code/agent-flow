"""知识库向量检索器。"""

from typing import Any

from app.rag.embedding import get_embedding_service
from app.repository.knowledge_repository import KnowledgeRepository
from app.utils.logger import logger


class KnowledgeRetriever:
    """负责将用户问题转换为向量并执行知识库向量召回。"""

    def __init__(self, repository: KnowledgeRepository):
        # 知识库 Repository
        self.repository = repository

        # 获取项目已有的 Embedding 服务
        self.embedding_service = get_embedding_service()

    # 将用户问题转换为向量，并检索相似子切片
    async def retrieve(
        self,
        query: str,
        user_id: int,
        user_role: str,
        top_k: int = 30,
        ctx: Any = None,
    ) -> list[dict[str, Any]]:
        """
        执行知识库向量召回。

        Args:
            query: 用户当前问题。
            user_id: 当前用户数据库 ID。
            user_role: 当前用户角色。
            top_k: 最大召回数量。
            ctx: 可选的上下文，传递给 Embedding 服务。

        Returns:
            相似子切片列表，包含 chunk、文档信息及相似度。
        """
        # 将用户问题转换为向量
        query_embedding = await self.embedding_service.embed_query(
            query,
            ctx=ctx,
        )

        if not query_embedding:
            logger.warning("知识检索失败：Embedding 未返回有效向量")
            return []

        # 在用户有权限访问的知识库中执行向量召回
        candidates = await self.repository.search_similar_child_chunks(
            query_embedding=query_embedding,
            query=query,
            user_id=user_id,
            user_role=user_role,
            top_k=top_k,
        )

        # logger.info(
        #     f"知识库向量召回完成：candidates_len={len(candidates)}, "
        #     f"知识库向量召回完成：candidates={candidates}, "
        # )


        return candidates