"""知识库检索节点。"""

import re
from typing import Any

from app.agent_graph.state import AgentState
from app.core import database
from app.rag.context_builder import KnowledgeContextBuilder
from app.rag.reranker import KnowledgeReranker
from app.rag.retriever import KnowledgeRetriever
from app.repository.knowledge_repository import KnowledgeRepository
from app.services.retrieval_service import KnowledgeRetrievalService
from app.utils.logger import logger

# 引用定位锚点长度：取父切片正文开头这些字符，供前端在渲染后的文档中定位命中段落。
ANCHOR_TEXT_LEN = 60
# 锚点短于该长度时不做定位（信息量太低，容易误匹配），交给章节标题兜底。
ANCHOR_MIN_CHARS = 8
# 父块正文里的表格占位符（切分器写进去的，不是原文，不能当锚点）。
_TABLE_PLACEHOLDER_PATTERN = re.compile(r"\[\[AF_TABLE_[a-fA-F0-9]+\]\]")
# 父块正文里的表格占位说明（切分器写进去的，不是原文，不能当锚点）。
_TABLE_NOTE_PATTERN = re.compile(r"\[表格内容已单独建立检索切片[^\]]*\]")
# Markdown 标记：渲染后会被 HTML 标签吃掉，留在锚点里会导致前端匹配不上。
_MARKDOWN_MARKS_PATTERN = re.compile(r"[#>*`~|]+")


def _heading_path_of(chunk: Any) -> list[str]:
    """从切片元数据中取出标题路径。

    切分器对单标题切片写 ``heading_path``、对跨章节切片写 ``heading_paths``，
    两种存法都要兼容，否则引用位置会退化成一个孤立行号。
    """

    extra_meta = getattr(chunk, "extra_meta", None)

    if not isinstance(extra_meta, dict):
        return []

    path = extra_meta.get("heading_path")

    if isinstance(path, list) and path:
        return [str(item) for item in path]

    paths = extra_meta.get("heading_paths")

    if isinstance(paths, list) and paths and isinstance(paths[0], list):
        return [str(item) for item in paths[0]]

    return []


def _anchor_text_of(chunk: Any) -> str:
    """取切片正文开头的有效字符，作为前端定位原文的锚点。"""

    content = (getattr(chunk, "content", "") or "").strip()

    if not content:
        return ""

    # 去掉表格占位符与占位说明：它们不在正文里，留着会干扰前端匹配
    content = _TABLE_PLACEHOLDER_PATTERN.sub(" ", content)
    content = _TABLE_NOTE_PATTERN.sub(" ", content)
    content = _MARKDOWN_MARKS_PATTERN.sub("", content)
    content = re.sub(r"\s+", " ", content).strip()

    if len(content) < ANCHOR_MIN_CHARS:
        return ""

    return content[:ANCHOR_TEXT_LEN]


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

        # 引用定位信息：章节路径用于展示位置，anchor_text 用于前端在正文中定位
        "heading_path": _heading_path_of(parent_chunk),
        "anchor_text": _anchor_text_of(parent_chunk),

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
        # top_k 是「融合后交给 reranker 的候选数」，取 20 而不是 10：
        # 两路各召回 60 条后 RRF 融合，只留 10 条给 reranker 挑选的余地太小；
        # min_rerank_score 从 0.7 下调到 0.5，0.7 会把「相关但表述不同」的段落直接判死。
        result = await retrieval_service.retrieve(
            query=query,
            user_id=user_id,
            user_role=user_role,
            top_k=20,
            top_n=5,
            max_contexts=3,
            min_rerank_score=0.5
        )

        # 将 ORM 对象转换为普通字典
        knowledge_contexts = [
            serialized
            for context in result["contexts"]
            if (
                serialized := _serialize_knowledge_context(context)
            )
        ]

        # 补齐文档 uid：前端引用卡片跳转原文时用 uid 作为路由参数，内部 id 不外露
        uid_map = await repository.get_document_uid_map(
            [
                context["document_id"]
                for context in knowledge_contexts
                if context.get("document_id") is not None
            ]
        )

        for context in knowledge_contexts:
            context["document_uid"] = uid_map.get(context.get("document_id"))

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