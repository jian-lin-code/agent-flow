"""知识库上下文构建器。"""

from typing import Any

from app.repository.knowledge_repository import KnowledgeRepository


class KnowledgeContextBuilder:
    """将重排序后的子切片转换为 LLM 可使用的上下文。"""

    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    @staticmethod
    def _get_chunk_extra_meta(chunk: Any) -> dict:
        """获取切片元数据。"""
        extra_meta = getattr(chunk, "extra_meta", None)

        return extra_meta if isinstance(extra_meta, dict) else {}

    @classmethod
    def _is_table_chunk(cls, chunk: Any) -> bool:
        """判断子切片是否为表格切片。"""
        extra_meta = cls._get_chunk_extra_meta(chunk)

        return extra_meta.get("type") == "table"

    @classmethod
    def _build_context_content(
        cls,
        parent_content: str,
        matched_table_chunks: list[Any],
    ) -> str:
        """构建最终上下文，将命中的表格内容补充到父切片正文后面。"""

        content_parts = [parent_content.strip()]

        table_contents = []

        for table_chunk in matched_table_chunks:
            table_content = (table_chunk.content or "").strip()

            if not table_content:
                continue

            extra_meta = cls._get_chunk_extra_meta(table_chunk)

            table_id = extra_meta.get("table_id")
            table_part_index = extra_meta.get("table_part_index")

            # 标注表格信息，方便 LLM 理解表格来源和分片关系
            table_title = "检索命中的表格内容"

            if table_id:
                table_title += f"（表格编号：{table_id}）"

            if table_part_index is not None:
                table_title += f"（第 {table_part_index + 1} 部分）"

            table_contents.append(
                f"{table_title}\n{table_content}"
            )

        if table_contents:
            content_parts.append(
                "【检索命中的表格内容】\n"
                + "\n\n".join(table_contents)
            )

        return "\n\n".join(
            part for part in content_parts if part
        )

    async def build(
        self,
        reranked_candidates: list[dict],
        user_id: int,
        user_role: str,
        max_contexts: int = 5,
    ) -> list[dict]:
        """
        将重排序后的子切片转换为父切片上下文。

        处理规则：
        1. 按照 Reranker 排序结果分组。
        2. 同一个父切片只生成一个上下文。
        3. 保留同一个父切片下所有命中的子切片。
        4. 普通文本子切片不重复拼接。
        5. 命中的表格子切片内容补充到父切片上下文。
        6. 批量查询父切片，并再次校验知识库访问权限。
        """

        if not reranked_candidates or max_contexts <= 0:
            return []

        # =====================================================
        # 第一步：按照父切片 ID 对候选子切片分组
        # =====================================================

        grouped_candidates: dict[int, list[dict]] = {}

        for candidate in reranked_candidates:
            child_chunk = candidate.get("chunk")

            if child_chunk is None:
                continue

            parent_id = child_chunk.parent_chunk_id

            # 没有关联父切片的候选结果暂不参与上下文构建
            if parent_id is None:
                continue

            if parent_id not in grouped_candidates:
                grouped_candidates[parent_id] = []

            grouped_candidates[parent_id].append(candidate)

        if not grouped_candidates:
            return []

        # 按照首次命中的顺序保留父切片
        selected_parent_ids = list(grouped_candidates.keys())[
            :max_contexts
        ]

        # =====================================================
        # 第二步：批量查询父切片
        # =====================================================

        parent_chunks = await self.repository.get_parent_chunks_by_ids(
            parent_ids=selected_parent_ids,
            user_id=user_id,
            user_role=user_role,
        )

        parent_chunk_map = {
            parent.id: parent
            for parent in parent_chunks
        }

        # =====================================================
        # 第三步：构建最终上下文
        # =====================================================

        contexts = []

        for parent_id in selected_parent_ids:

            parent_chunk = parent_chunk_map.get(parent_id)

            # 父切片不存在或用户无权访问时跳过
            if parent_chunk is None:
                continue

            candidates = grouped_candidates[parent_id]

            # 按照 Reranker 排序保留所有命中的子切片
            child_chunks = []
            matched_table_chunks = []

            seen_child_ids = set()

            for candidate in candidates:
                child_chunk = candidate.get("chunk")

                if child_chunk is None:
                    continue

                # 避免重复添加同一个子切片
                if child_chunk.id in seen_child_ids:
                    continue

                seen_child_ids.add(child_chunk.id)

                child_chunks.append(child_chunk)

                # 只将表格子切片的实际内容补充到父上下文
                if self._is_table_chunk(child_chunk):
                    matched_table_chunks.append(child_chunk)

            if not child_chunks:
                continue

            # 使用排序第一的候选结果作为主要检索信息
            best_candidate = candidates[0]

            # 构建最终 LLM 上下文
            context_content = self._build_context_content(
                parent_content=parent_chunk.content,
                matched_table_chunks=matched_table_chunks,
            )

            context = {
                **best_candidate,

                # 父切片 ORM 对象
                "chunk": parent_chunk,

                # 父切片 ID
                "parent_chunk_id": parent_id,

                # 所有命中的子切片
                "child_chunks": child_chunks,

                # 兼容原有单个子切片字段
                "child_chunk": child_chunks[0],

                # 命中的表格子切片
                "matched_table_chunks": matched_table_chunks,

                # 最终提供给 LLM 的上下文
                "content": context_content,
            }

            contexts.append(context)

        return contexts