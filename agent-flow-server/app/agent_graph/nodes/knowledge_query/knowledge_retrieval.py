"""知识库检索节点。"""

from typing import Any

from app.agent_graph.state import AgentState
from app.core import database
from app.rag.context_builder import KnowledgeContextBuilder
from app.rag.reranker import KnowledgeReranker
from app.rag.retriever import KnowledgeRetriever
from app.repository.knowledge_repository import KnowledgeRepository
from app.services.retrieval_service import KnowledgeRetrievalService
from app.utils.logger import logger


# 将检索上下文中的 ORM 对象转换为普通字典
def _serialize_knowledge_context(
    context: dict[str, Any],
) -> dict[str, Any]:
    """将父切片和子切片转换为可持久化的知识上下文。"""

    parent_chunk = context.get("chunk")

    child_chunks = context.get("child_chunks") or []

    matched_table_chunks = context.get("matched_table_chunks") or []

    if parent_chunk is None:
        return {}

    # 获取第一个命中的子切片，兼容旧字段
    first_child_chunk = (
        child_chunks[0]
        if child_chunks
        else context.get("child_chunk")
    )

    return {
        # 最终上下文：父切片正文 + 命中的表格内容
        "content": context.get("content") or parent_chunk.content,

        # 文档来源信息
        "document_id": parent_chunk.document_id,
        "document_title": context.get("document_title"),
        "knowledge_base_uid": context.get("knowledge_base_uid"),
        "knowledge_base_name": context.get("knowledge_base_name"),

        # 父切片信息
        "parent_chunk_id": parent_chunk.id,
        "parent_chunk_index": parent_chunk.chunk_index,
        "source_start_line": parent_chunk.source_start_line,
        "source_end_line": parent_chunk.source_end_line,

        # 第一个命中的子切片，兼容原有数据结构
        "child_chunk_id": (
            first_child_chunk.id
            if first_child_chunk
            else None
        ),
        "child_chunk_index": (
            first_child_chunk.chunk_index
            if first_child_chunk
            else None
        ),

        # 所有命中的子切片 ID
        "child_chunk_ids": [
            chunk.id
            for chunk in child_chunks
        ],

        # 所有命中的表格切片 ID
        "matched_table_chunk_ids": [
            chunk.id
            for chunk in matched_table_chunks
        ],

        # 检索和重排序分数
        "similarity": context.get("similarity"),
        "distance": context.get("distance"),
        "rerank_score": context.get(
            "rerank_score",
            context.get("score"),
        ),
    }


# 执行知识库检索，并将检索上下文写入 AgentState
async def handle_knowledge_query(state: AgentState) -> dict[str, Any]:
    """
    调用知识库检索服务，执行向量召回、重排序和父切片上下文构建。

    将最终上下文转换为普通字典，避免 ORM 对象进入 LangGraph State。
    """
    query = (state.get("current_message") or "").strip()
    user_id = state.get("user_id")
    user_role = state.get("user_role")

    if not query:
        return {
            "knowledge_contexts": [],
            "knowledge_candidate_count": 0,
            "knowledge_reranked_count": 0,
            "knowledge_retrieval_completed": True,
        }

    if user_id is None:
        raise RuntimeError("知识库检索失败：缺少 user_id。")

    if user_role not in {"employee", "admin"}:
        raise RuntimeError("知识库检索失败：用户角色无效。")

    # 获取数据库 Session 工厂
    session_factory = database.async_session

    if session_factory is None:
        raise RuntimeError("知识库检索失败：数据库尚未初始化。")

    logger.info(
        f"开始知识库检索：user_id={user_id}, "
        f"user_role={user_role}, query={query[:100]}"
    )

    # 创建数据库 Session，并组装检索服务
    async with session_factory() as session:
        repository = KnowledgeRepository(session)

        retriever = KnowledgeRetriever(repository)
        reranker = KnowledgeReranker()
        context_builder = KnowledgeContextBuilder(repository)

        retrieval_service = KnowledgeRetrievalService(
            retriever=retriever,
            reranker=reranker,
            context_builder=context_builder,
        )

        # 执行完整知识库检索
        result = await retrieval_service.retrieve(
            query=query,
            user_id=user_id,
            user_role=user_role,
            top_k=10,
            top_n=5,
            max_contexts=3,
            min_rerank_score=0.7
        )

        # 将 ORM 对象转换为普通字典
        knowledge_contexts = [
            serialized
            for context in result["contexts"]
            if (
                serialized := _serialize_knowledge_context(context)
            )
        ]

        candidate_count = result["candidate_count"]
        reranked_count = result["reranked_count"]

    # logger.info(
    #     f"知识库检索完成：user_id={user_id}, "
    #     f"candidate_count={candidate_count}, "
    #     f"reranked_count={reranked_count}, "
    #     f"context_count={len(knowledge_contexts)}"
    # )

    # 将检索结果写入 LangGraph State
    return {
        "knowledge_contexts": knowledge_contexts,
        "knowledge_candidate_count": candidate_count,
        "knowledge_reranked_count": reranked_count,
        "knowledge_retrieval_completed": True,
    }