from typing import Any

from app.rag.context_builder import KnowledgeContextBuilder
from app.rag.reranker import KnowledgeReranker
from app.rag.retriever import KnowledgeRetriever
from app.utils.logger import logger
from math import isfinite

class KnowledgeRetrievalService:
    """知识库检索服务，统一协调召回、重排序和上下文构建。"""

    def __init__(
        self,
        retriever: KnowledgeRetriever,
        reranker: KnowledgeReranker,
        context_builder: KnowledgeContextBuilder,
    ):
        self.retriever = retriever
        self.reranker = reranker
        self.context_builder = context_builder

    # 执行完整的知识库检索流程
    async def retrieve(
        self,
        query: str,
        user_id: int,
        user_role: str,
        top_k: int = 30,
        top_n: int = 10,
        max_contexts: int = 5,
        min_rerank_score=0.5,
        ctx: Any = None,
    ) -> dict:
        """
        执行知识库检索。

        Args:
            query: 用户当前问题。
            user_id: 当前用户数据库 ID。
            user_role: 当前用户角色，employee 或 admin。
            top_k: 向量检索召回数量。
            top_n: Reranker 重排序后保留的候选数量。
            max_contexts: 最终上下文最大父切片数量。
            ctx: 可选的任务上下文，例如 ARQ 上下文。

        Returns:
            包含检索问题、候选数量和最终上下文的字典。
        """
        # 限制检索参数，避免异常的大数量请求
        top_k = max(1, min(top_k, 100))
        top_n = max(1, min(top_n, top_k))
        max_contexts = max(1, min(max_contexts, 20))

        # 第一步：执行向量检索，召回相关子切片
        candidates = await self.retriever.retrieve(
            query=query,
            user_id=user_id,
            user_role=user_role,
            top_k=top_k,
            ctx=ctx,
        )

        # 没有召回结果时，不再调用 Reranker
        if not candidates:
            return {
                "query": query,
                "candidate_count": 0,
                "reranked_count": 0,
                "contexts": [],
            }

        # 第二步：使用 Reranker 对候选子切片重新排序
        reranked_candidates = await self.reranker.rerank(
            query=query,
            candidates=candidates,
            top_n=top_n,
        )

        # Reranker 没有返回结果时，最终上下文为空
        if not reranked_candidates:
            return {
                "query": query,
                "candidate_count": len(candidates),
                "reranked_count": 0,
                "contexts": [],
            }

        # 第三阶段：根据 Reranker 相关性分数过滤低分候选
        filtered_candidates = []

        for candidate in reranked_candidates:
            score = candidate.get("rerank_score")

            if score is None:
                continue

            score = float(score)

            if not isfinite(score):
                continue

            if score >= min_rerank_score:
                filtered_candidates.append(candidate)

        filtered_count = len(filtered_candidates)

        # logger.info(
        #     "知识库相关性过滤完成："
        #     f"threshold={min_rerank_score}, "
        #     f"reranked_count={len(reranked_candidates)}, "
        #     f"filtered_count={filtered_count}, "
        #     f"rejected_count={len(reranked_candidates) - filtered_count}"
        # )

        # 第三步：根据重排序结果获取父切片并构建上下文
        contexts = await self.context_builder.build(
            reranked_candidates=filtered_candidates,
            user_id=user_id,
            user_role=user_role,
            max_contexts=max_contexts,
        )
        logger.info(f'父切片数据 加上子切片为表格的数据：{contexts}')
        # 返回完整检索结果
        return {
            "query": query,
            "candidate_count": len(candidates),
            "reranked_count": len(reranked_candidates),
            "contexts": contexts,
        }