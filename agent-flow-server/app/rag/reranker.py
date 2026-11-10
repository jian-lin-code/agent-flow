import json

import httpx

from app.core.config import settings
from app.utils.logger import logger


class KnowledgeReranker:
    """知识库候选切片重排序器。"""

    def __init__(self):
        """初始化 Reranker 配置。"""
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.RERANK_API_BASE.rstrip("/")
        self.model = settings.RERANK_MODEL_NAME
        self.timeout = 60.0

    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_n: int = 5,
    ) -> list[dict]:
        if not query.strip() or not candidates:
            return []

        top_n = max(1, min(top_n, len(candidates)))

        documents = []
        for candidate in candidates:
            chunk = candidate["chunk"]
            content = getattr(chunk, "content", None)

            if not isinstance(content, str) or not content.strip():
                raise ValueError("Reranker 候选切片缺少有效的 content 字段")

            documents.append(content)

        # 兼容端点使用扁平结构，不传 instruct
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 关键：手动序列化并保留中文，避免 httpx 将中文转义为 \uXXXX
                response = await client.post(
                    f"{self.base_url}/reranks",
                    headers=headers,
                    content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                )

                if response.status_code != 200:
                    logger.error(f"Rerank API 返回 {response.status_code}: {response.text}")

                response.raise_for_status()
                result = response.json()

            ranked_results = result.get("results", [])

            if not isinstance(ranked_results, list):
                raise ValueError("Reranker 返回结果格式错误")

            reranked_candidates = []
            for item in ranked_results:
                index = item.get("index")
                score = item.get("relevance_score")

                if not isinstance(index, int):
                    raise ValueError("Reranker 返回了无效的文档索引")

                if index < 0 or index >= len(candidates):
                    raise ValueError("Reranker 返回的文档索引越界")

                if score is None:
                    raise ValueError("Reranker 未返回相关性分数")

                candidate = dict(candidates[index])
                candidate["rerank_score"] = float(score)
                reranked_candidates.append(candidate)
            #
            # logger.info(
            #     "知识库重排序完成，"
            #     f"reranked_candidates_len={len(reranked_candidates)}, "
            #     f"reranked_candidates={reranked_candidates}"
            # )
            return reranked_candidates

        except Exception:
            logger.exception("知识库 Reranker 调用失败")
            raise