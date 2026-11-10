from functools import lru_cache
from typing import List

from langchain_openai import OpenAIEmbeddings
from app.core.config import settings
from app.utils.logger import logger
from app.events.document_progress import emit

from typing import Any


def build_embedding_text(
    content: str,
    metadata: dict[str, Any] | None,
) -> str:
    """根据切块元数据构建带有章节上下文的 Embedding 文本。

    Args:
        content: 切块原始正文。
        metadata: 切块元数据，可能包含 heading_path 和 embedding_segments。

    Returns:
        拼接标题上下文后的 Embedding 文本。
    """
    if not metadata:
        return content

    segments = metadata.get("embedding_segments")

    # 优先使用 embedding_segments，支持一个块包含多个章节内容。
    if segments:
        parts = []

        for segment in segments:
            segment_content = segment.get("content", "").strip()
            heading_path = segment.get("heading_path") or []

            if not segment_content:
                continue

            heading = " > ".join(
                str(item).strip()
                for item in heading_path
                if item
            )

            if heading:
                parts.append(
                    f"所属章节：{heading}\n\n{segment_content}"
                )
            else:
                parts.append(segment_content)

        if parts:
            return "\n\n".join(parts)

    # 兼容没有 embedding_segments 的旧数据。
    heading_path = metadata.get("heading_path") or []

    if heading_path:
        heading = " > ".join(
            str(item).strip()
            for item in heading_path
            if item
        )

        if heading:
            return f"所属章节：{heading}\n\n{content}"

    return content



class EmbeddingService:
    """文本向量化服务（单例）"""

    def __init__(self):
        # 1. 初始化 OpenAI 兼容的 Embedding 客户端（阿里云百炼）
        self.embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL_NAME,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            # 百炼的 text-embedding-v4 如果遇到超长文本或超大批次会自动重试
            max_retries=settings.LLM_MAX_RETRIES,
            # 是否将向量归一化（部分检索算法需要，pgvector 的余弦距离不需要），默认 False
            check_embedding_ctx_length=False
        )
        self.dimension = settings.EMBEDDING_DIMENSION
        logger.info(f"[Embedding] 服务已初始化，模型: {settings.EMBEDDING_MODEL_NAME}，维度: {self.dimension}")

    async def embed_query(
            self,
            text: str,
            *,
            ctx: dict | None = None
    ) -> List[float]:
        """单条文本向量化（用于用户搜索提问时）"""
        if ctx is not None:
            await emit("[向量化] 正在进行查询文本向量化...", ctx=ctx)

        try:
            return await self.embeddings.aembed_query(text)
        except Exception as e:
            logger.error(f"[Embedding] 单条文本向量化失败: {e}")
            if ctx is not None:
                await emit(f"[向量化] 查询文本向量化失败：{e}", ctx=ctx)
            raise e

    async def embed_documents(
            self,
            texts: List[str],
            batch_size: int = 10,
            *,
            ctx: dict | None = None
    ) -> List[List[float]]:
        """
        批量文本向量化（用于文档入库时）
        :param texts: 文本列表
        :param batch_size: 批次大小（阿里云百炼单次请求最多支持 10 条）
        :param ctx: 上下文，用于日志推送
        :return: 向量列表
        """
        if not texts:
            return []

        all_vectors = []
        total = len(texts)

        if ctx is not None:
            await emit(
                f"[向量化] 开始调用模型生成向量 (共 {total} 条文本，分 {(total + batch_size - 1) // batch_size} 批处理)",
                ctx=ctx
            )

        # 分批处理，防止超出 API 的单次请求限制
        for i in range(0, total, batch_size):
            batch_texts = texts[i:i + batch_size]
            current_batch_count = min(i + batch_size, total)

            logger.debug(f"[Embedding] 正在向量化批次: {i + 1} - {current_batch_count} / {total}")

            if ctx is not None:
                await emit(
                    f"[向量化] 正在生成向量 (进度: {i + 1}-{current_batch_count} / {total})",
                    ctx=ctx
                )

            try:
                vectors = await self.embeddings.aembed_documents(batch_texts)
                all_vectors.extend(vectors)
            except Exception as e:
                logger.error(f"[Embedding] 批次向量化失败 (索引 {i} - {i + batch_size}): {e}")
                if ctx is not None:
                    await emit(
                        f"[向量化] 向量生成失败 (批次索引 {i}-{i + batch_size})：{e}",
                        ctx=ctx
                    )
                raise e

        if ctx is not None:
            await emit(
                f"[向量化] 向量生成完成，共生成 {total} 条向量",
                ctx=ctx
            )

        return all_vectors



@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """获取向量化服务的单例"""
    return EmbeddingService()