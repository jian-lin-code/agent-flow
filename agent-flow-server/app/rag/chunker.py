from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.events.document_progress import emit
from app.utils.logger import logger


# ============================================================
# 数据结构
# ============================================================

@dataclass
class MarkdownTable:
    """
    Markdown 表格的数据结构。

    Attributes:
        tmp_id: 表格唯一临时 ID。
        placeholder: 在原文中替代表格的占位符。
        content: 表格完整 Markdown 内容。
        heading_path: 表格所属的 Markdown 标题路径。
        start_line: 表格在原文中的起始行号，从 1 开始。
        end_line: 表格在原文中的结束行号，从 1 开始。
    """

    tmp_id: str
    placeholder: str
    content: str
    heading_path: list[str]
    start_line: int
    end_line: int


@dataclass
class TextSection:
    """
    Markdown 文档章节的数据结构。

    Attributes:
        content: 章节正文，不包含 Markdown 标题。
        heading_path: 当前章节的完整标题路径。
        start_line: 正文在原文中的起始行号。
        end_line: 正文在原文中的结束行号。
    """

    content: str
    heading_path: list[str]
    start_line: int
    end_line: int


@dataclass
class SectionGroup:
    """
    多个相邻章节组成的切片处理单元。

    一个 Group 可以包含一个或多个 Section。

    短章节合并后，Group 负责组织父块切分；
    但不会丢失内部各个 Section 原有的标题路径和行号。

    Attributes:
        sections: 当前分组包含的章节。
    """

    sections: list[TextSection]

    @property
    def content_length(self) -> int:
        """计算当前分组所有章节正文的总字符数。"""
        return sum(
            len(section.content.strip())
            for section in self.sections
        )


class AdvancedMarkdownChunker:
    """
    Markdown/TXT 文档父子切片器。

    核心功能：
        1. 支持 Markdown 和 TXT 文档。
        2. Markdown 按标题划分章节。
        3. 自动合并符合条件的相邻短章节。
        4. 使用父块和子块两级结构切分正文。
        5. Markdown 表格独立提取和切片。
        6. 保留父子块关联关系。
        7. 保留切片在原文中的起止行号。
        8. 正文 content 不拼接标题路径。
        9. 提供独立的 Embedding 文本构建方法。

    行号说明：
        source_start_line/source_end_line 对应传入 process()
        的原始文本行号，从 1 开始。

        如果 PDF/DOCX 已经转换成 Markdown，
        这里的行号对应转换后的 Markdown 行号，
        不代表 PDF 页码。
    """

    # Markdown 标题匹配规则。
    HEADER_PATTERN = re.compile(
        r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$"
    )

    # Markdown 表格行匹配规则。
    TABLE_ROW_PATTERN = re.compile(
        r"^[ \t]*\|.*\|[ \t]*$"
    )

    # Markdown 表格分隔行匹配规则。
    TABLE_SEPARATOR_PATTERN = re.compile(
        r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*"
        r"(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$"
    )

    # 匹配表格占位符。
    TABLE_PLACEHOLDER_PATTERN = re.compile(
        r"\[\[AF_TABLE_[a-fA-F0-9]+\]\]"
    )

    def __init__(
        self,
        *,
        parent_chunk_size: int = 2000,
        parent_chunk_overlap: int = 150,
        child_chunk_size: int = 500,
        child_chunk_overlap: int = 80,
        table_chunk_size: int = 1200,
        table_row_overlap: int = 1,
        short_section_threshold: int = 250,
        section_merge_target: int = 600,
        section_merge_max_size: int = 2000,
        separators: list[str] | None = None,
    ):
        """
        初始化文档切片器。

        Args:
            parent_chunk_size:
                父块目标字符数。默认 2000。

            parent_chunk_overlap:
                相邻父块之间的字符重叠长度。默认 150。

            child_chunk_size:
                子块目标字符数。默认 500。

            child_chunk_overlap:
                相邻子块之间的字符重叠长度。默认 80。

            table_chunk_size:
                表格单个切片的最大目标字符数。默认 1200。

            table_row_overlap:
                表格拆分时，相邻表格切片重复的数据行数。默认 1。

            short_section_threshold:
                短章节判断阈值。
                正文字符数小于该值的章节才参与合并。
                默认 250。

            section_merge_target:
                短章节合并的目标字符数。
                当前分组达到该值后，不再继续接收下一个短章节。
                默认 600。

            section_merge_max_size:
                短章节合并后的最大字符数。
                默认 2000。

            separators:
                RecursiveCharacterTextSplitter 使用的分隔符。
                默认优先按照段落、换行、中文标点、空格切分。
        """

        self._validate_config(
            parent_chunk_size=parent_chunk_size,
            parent_chunk_overlap=parent_chunk_overlap,
            child_chunk_size=child_chunk_size,
            child_chunk_overlap=child_chunk_overlap,
            table_chunk_size=table_chunk_size,
            table_row_overlap=table_row_overlap,
            short_section_threshold=short_section_threshold,
            section_merge_target=section_merge_target,
            section_merge_max_size=section_merge_max_size,
        )

        self.parent_chunk_size = parent_chunk_size
        self.parent_chunk_overlap = parent_chunk_overlap

        self.child_chunk_size = child_chunk_size
        self.child_chunk_overlap = child_chunk_overlap

        self.table_chunk_size = table_chunk_size
        self.table_row_overlap = table_row_overlap

        self.short_section_threshold = short_section_threshold
        self.section_merge_target = section_merge_target
        self.section_merge_max_size = section_merge_max_size

        self.separators = separators or [
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            "；",
            "，",
            " ",
            "",
        ]

        # 父块切分器。
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=parent_chunk_overlap,
            separators=self.separators,
            length_function=len,
            keep_separator=True,
        )

        # 子块切分器。
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
            separators=self.separators,
            length_function=len,
            keep_separator=True,
        )

    # ========================================================
    # 配置与基础工具
    # ========================================================

    @staticmethod
    def _validate_config(
        parent_chunk_size: int,
        parent_chunk_overlap: int,
        child_chunk_size: int,
        child_chunk_overlap: int,
        table_chunk_size: int,
        table_row_overlap: int,
        short_section_threshold: int,
        section_merge_target: int,
        section_merge_max_size: int,
    ) -> None:
        """
        校验切片器初始化参数。

        Args:
            parent_chunk_size: 父块长度。
            parent_chunk_overlap: 父块重叠长度。
            child_chunk_size: 子块长度。
            child_chunk_overlap: 子块重叠长度。
            table_chunk_size: 表格切片长度。
            table_row_overlap: 表格行重叠数量。
            short_section_threshold: 短章节判断阈值。
            section_merge_target: 短章节合并目标长度。
            section_merge_max_size: 短章节合并最大长度。

        Raises:
            ValueError: 参数不符合要求时抛出。
        """

        if (
            parent_chunk_size <= 0
            or child_chunk_size <= 0
            or table_chunk_size <= 0
        ):
            raise ValueError("切片 size 必须大于 0")

        if (
            parent_chunk_overlap < 0
            or parent_chunk_overlap >= parent_chunk_size
        ):
            raise ValueError(
                "parent_chunk_overlap 必须 >= 0 且小于 parent_chunk_size"
            )

        if (
            child_chunk_overlap < 0
            or child_chunk_overlap >= child_chunk_size
        ):
            raise ValueError(
                "child_chunk_overlap 必须 >= 0 且小于 child_chunk_size"
            )

        if table_row_overlap < 0:
            raise ValueError("table_row_overlap 不能小于 0")

        if short_section_threshold <= 0:
            raise ValueError("short_section_threshold 必须大于 0")

        if section_merge_target <= 0:
            raise ValueError("section_merge_target 必须大于 0")

        if section_merge_max_size < section_merge_target:
            raise ValueError(
                "section_merge_max_size 必须大于或等于 section_merge_target"
            )

        if short_section_threshold > section_merge_max_size:
            raise ValueError(
                "short_section_threshold 不能大于 section_merge_max_size"
            )

    @staticmethod
    def _new_id() -> str:
        """生成 UUID 字符串，作为切片或表格的临时唯一标识。"""
        return str(uuid.uuid4())

    @staticmethod
    def _normalize_newlines(text: str) -> str:
        """
        统一文本换行符。

        Args:
            text: 原始文档文本。

        Returns:
            将 \\r\\n 和 \\r 统一转换为 \\n 的文本。
        """
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _remove_empty_html_anchors(text: str) -> str:
        """移除空的 HTML 锚点，保留换行结构。"""

        return re.sub(
            r'<a\b[^>]*\bid\s*=\s*["\']?[^"\'>\s]+["\']?[^>]*>\s*</a>',
            '',
            text,
            flags=re.IGNORECASE,
        )
    @staticmethod
    def _make_chunk(
        *,
        document_uid: str,
        content: str,
        tmp_id: str,
        parent_id: str | None,
        is_parent: bool,
        chunk_index: int,
        metadata: dict[str, Any],
        source_start_line: int | None = None,
        source_end_line: int | None = None,
    ) -> dict[str, Any]:
        """
        组装统一格式的切片数据。

        Args:
            document_uid: 所属文档 UID。
            content: 切片正文，不包含标题路径前缀。
            tmp_id: 当前切片临时 UID。
            parent_id: 父块 UID；父块为 None。
            is_parent: 是否为父块。
            chunk_index: 当前文档中的切片顺序。
            metadata: 切片元数据。
            source_start_line: 原文起始行号。
            source_end_line: 原文结束行号。

        Returns:
            可交给后续入库流程处理的切片字典。
        """

        result: dict[str, Any] = {
            "tmp_id": tmp_id,
            "document_uid": document_uid,
            "parent_id": parent_id,
            "is_parent": is_parent,
            "content": content.strip(),
            "chunk_index": chunk_index,
            "metadata": metadata,
            "embedding": None,
        }

        if source_start_line is not None:
            result["source_start_line"] = int(source_start_line)

        if source_end_line is not None:
            result["source_end_line"] = int(source_end_line)

        return result

    # ========================================================
    # Embedding 文本构建
    # ========================================================

    @staticmethod
    def build_embedding_text(
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        根据正文和标题路径构建向量化文本。

        注意：
            数据库 content 不包含标题路径。
            向量化时调用此方法，动态补充章节上下文。

        对于普通章节切片：
            标题路径 + 正文。

        对于跨多个章节的父块：
            每个章节片段分别添加自己的标题路径，
            避免将多个章节错误地归到同一个标题下。

        对于表格切片：
            使用 metadata 中的 heading_path。

        Args:
            content: 切片正文。
            metadata: 切片 metadata。

        Returns:
            用于 Embedding 的文本。
        """

        metadata = metadata or {}

        embedding_segments = metadata.get("embedding_segments") or []

        # 多章节父块或子块：分别添加各自的标题路径。
        if embedding_segments:
            parts: list[str] = []

            for segment in embedding_segments:
                segment_content = str(
                    segment.get("content") or ""
                ).strip()

                if not segment_content:
                    continue

                heading_path = segment.get("heading_path") or []
                heading_text = " > ".join(heading_path)

                if heading_text:
                    parts.append(
                        f"{heading_text}\n{segment_content}"
                    )
                else:
                    parts.append(segment_content)

            if parts:
                return "\n\n".join(parts)

        # 普通切片或表格切片。
        heading_path = metadata.get("heading_path") or []
        heading_text = " > ".join(heading_path)

        if heading_text:
            return f"{heading_text}\n{content.strip()}"

        return content.strip()

    # ========================================================
    # Markdown 表格提取
    # ========================================================

    @classmethod
    def _extract_tables(
        cls,
        lines: list[str],
    ) -> tuple[list[str], list[MarkdownTable]]:
        """
        提取 Markdown 表格，并用占位符替换原文表格。

        处理规则：
            1. 识别 Markdown 表头和分隔行。
            2. 提取完整表格内容。
            3. 记录表格标题路径。
            4. 记录表格原文行号。
            5. 使用占位符替换表格。
            6. 占位符之外的行仍然保留原始行位置。

        Args:
            lines: 原始 Markdown 文本行列表。

        Returns:
            protected_lines:
                表格被占位符替换后的文本行。

            tables:
                提取出来的 MarkdownTable 列表。
        """

        output = list(lines)
        tables: list[MarkdownTable] = []

        heading_stack: dict[int, str] = {}

        i = 0

        while i < len(lines):
            line = lines[i]

            # 更新标题路径。
            heading_match = cls.HEADER_PATTERN.match(line.strip())

            if heading_match:
                level = len(heading_match.group(1))
                heading_stack[level] = heading_match.group(2).strip()

                for old_level in list(heading_stack):
                    if old_level > level:
                        del heading_stack[old_level]

            # 判断是否为 Markdown 表格起始位置。
            if (
                i + 1 < len(lines)
                and cls.TABLE_ROW_PATTERN.match(line)
                and cls.TABLE_SEPARATOR_PATTERN.match(lines[i + 1])
            ):
                start = i

                table_lines = [
                    lines[i],
                    lines[i + 1],
                ]

                i += 2

                # 收集后续数据行。
                while (
                    i < len(lines)
                    and cls.TABLE_ROW_PATTERN.match(lines[i])
                ):
                    table_lines.append(lines[i])
                    i += 1

                if len(table_lines) >= 3:
                    table_id = cls._new_id()

                    placeholder = (
                        f"AF_TABLE_{table_id.replace('-', '')}"
                    )

                    table = MarkdownTable(
                        tmp_id=table_id,
                        placeholder=placeholder,
                        content="\n".join(table_lines),
                        heading_path=[
                            heading_stack[k]
                            for k in sorted(heading_stack)
                        ],
                        start_line=start + 1,
                        end_line=start + len(table_lines),
                    )

                    tables.append(table)

                    # 第一行使用占位符。
                    output[start] = f"[[{placeholder}]]"

                    # 其他表格行置空，但不删除行。
                    for row_idx in range(
                        start + 1,
                        start + len(table_lines),
                    ):
                        output[row_idx] = ""

                else:
                    # 无效表格，恢复原始文本。
                    output[start:start + len(table_lines)] = table_lines

                continue

            i += 1

        return output, tables

    # ========================================================
    # Markdown 章节解析
    # ========================================================

    @classmethod
    def _split_sections(
        cls,
        lines: list[str],
        is_plain_text: bool,
    ) -> list[TextSection]:
        """
        将文档划分为多个 Section。

        Markdown：
            根据 H1-H6 标题划分章节。
            标题只保存在 heading_path 中，不进入正文。

        TXT：
            整篇文本作为一个 Section。
            heading_path 为空。

        Args:
            lines: 文档文本行列表。
            is_plain_text: 是否为纯文本模式。

        Returns:
            按原文顺序排列的 TextSection 列表。
        """

        if is_plain_text:
            text = "\n".join(lines).strip()

            return [
                TextSection(
                    content=text,
                    heading_path=[],
                    start_line=1,
                    end_line=max(1, len(lines)),
                )
            ] if text else []

        sections: list[TextSection] = []

        heading_stack: dict[int, str] = {}

        current_lines: list[str] = []
        current_path: list[str] = []

        current_start: int | None = None

        def flush(end_line: int) -> None:
            """
            保存当前标题下的正文。

            Args:
                end_line: 当前正文结束行号。
            """

            nonlocal current_lines, current_start

            content = "\n".join(current_lines).strip()

            if content and current_start is not None:
                sections.append(
                    TextSection(
                        content=content,
                        heading_path=list(current_path),
                        start_line=current_start,
                        end_line=max(current_start, end_line),
                    )
                )

            current_lines = []
            current_start = None

        for idx, line in enumerate(lines):
            line_number = idx + 1

            heading_match = cls.HEADER_PATTERN.match(line.strip())

            if heading_match:
                # 先保存上一个标题下的正文。
                flush(idx)

                level = len(heading_match.group(1))

                heading_stack[level] = heading_match.group(2).strip()

                # 删除更深层级的旧标题。
                for old_level in list(heading_stack):
                    if old_level > level:
                        del heading_stack[old_level]

                current_path = [
                    heading_stack[k]
                    for k in sorted(heading_stack)
                ]

                continue

            if current_start is None:
                current_start = line_number

            current_lines.append(line)

        if current_lines:
            flush(len(lines))

        return sections

    # ========================================================
    # 短章节合并
    # ========================================================

    @staticmethod
    def _can_merge_sections(
        first: TextSection,
        second: TextSection,
    ) -> bool:
        """
        判断两个相邻章节是否允许合并。

        合并条件：
            1. 两个章节都必须存在父标题。
            2. 两个章节标题层级必须一致。
            3. 两个章节必须拥有相同的直接父标题路径。

        例如允许：

            # 差旅管理制度
            ## 住宿标准
            ## 交通标准

        不允许：

            # 差旅管理制度
            ## 住宿标准

            # 财务管理制度
            ## 发票管理

        也不允许不同层级的章节合并。

        Args:
            first: 前一个章节。
            second: 后一个章节。

        Returns:
            是否允许合并。
        """

        first_path = first.heading_path
        second_path = second.heading_path

        # 无标题章节和 H1 章节不参与合并。
        if len(first_path) < 2 or len(second_path) < 2:
            return False

        # 标题层级必须一致。
        if len(first_path) != len(second_path):
            return False

        # 直接父标题路径必须一致。
        return first_path[:-1] == second_path[:-1]

    def _merge_short_sections(
        self,
        sections: list[TextSection],
    ) -> list[SectionGroup]:
        """
        合并相邻短章节。

        处理规则：
            1. 长度达到 short_section_threshold 的章节独立成组。
            2. 短章节只有满足同级、同父标题条件才允许合并。
            3. 合并后达到 section_merge_target，不再继续接收新章节。
            4. 合并后不能超过 section_merge_max_size。
            5. 不同主题之间绝不合并。
            6. 每个 Section 的 heading_path 和行号始终独立保留。

        Args:
            sections: 原始章节列表。

        Returns:
            SectionGroup 列表。
        """

        groups: list[SectionGroup] = []

        current_sections: list[TextSection] = []

        def flush() -> None:
            """将当前累积的短章节保存为一个 SectionGroup。"""

            nonlocal current_sections

            if current_sections:
                groups.append(
                    SectionGroup(
                        sections=current_sections
                    )
                )

                current_sections = []

        for section in sections:
            section_length = len(section.content.strip())

            # 长章节不参与合并，独立成组。
            if section_length >= self.short_section_threshold:
                flush()

                groups.append(
                    SectionGroup(
                        sections=[section]
                    )
                )

                continue

            if not current_sections:
                current_sections = [section]
                continue

            previous_section = current_sections[-1]

            # 标题层级或父标题不同，不允许合并。
            if not self._can_merge_sections(
                previous_section,
                section,
            ):
                flush()
                current_sections = [section]
                continue

            current_length = sum(
                len(item.content.strip())
                for item in current_sections
            )

            candidate_length = current_length + section_length

            # 当前分组已经达到目标长度，或者加入后超过最大长度。
            if (
                current_length >= self.section_merge_target
                or candidate_length > self.section_merge_max_size
            ):
                flush()
                current_sections = [section]
                continue

            current_sections.append(section)

        flush()

        return groups

    # ========================================================
    # 文本定位与行号映射
    # ========================================================

    @staticmethod
    def _find_piece_span(
        source: str,
        piece: str,
        search_from: int,
    ) -> tuple[int, int] | None:
        """
        在来源文本中定位切片的字符起止位置。

        采用顺序搜索，处理重复文本时从上一次搜索位置继续。

        Args:
            source: 原始来源文本。
            piece: RecursiveCharacterTextSplitter 生成的切片。
            search_from: 本次搜索起始字符位置。

        Returns:
            (start_offset, end_offset)，找不到时返回 None。
        """

        needle = piece.strip()

        if not needle:
            return None

        pos = source.find(needle, search_from)

        if pos < 0:
            # 尝试根据切片首个非空行定位。
            first_line = next(
                (
                    item.strip()
                    for item in needle.splitlines()
                    if item.strip()
                ),
                "",
            )

            if not first_line:
                return None

            pos = source.find(first_line, search_from)

            if pos < 0:
                return None

            end_pos = pos + len(first_line)

        else:
            end_pos = pos + len(needle)

        return pos, end_pos

    @staticmethod
    def _line_range_for_piece(
        source: str,
        piece: str,
        search_from: int,
        base_line: int,
    ) -> tuple[int, int] | None:
        """
        根据切片在来源文本中的位置计算原文行号。

        Args:
            source: 来源文本。
            piece: 当前切片文本。
            search_from: 搜索起始字符位置。
            base_line: 来源文本第一行对应的原文行号。

        Returns:
            (start_line, end_line)，无法定位时返回 None。
        """

        span = AdvancedMarkdownChunker._find_piece_span(
            source,
            piece,
            search_from,
        )

        if span is None:
            return None

        start_pos, end_pos = span

        start_line = (
            base_line
            + source.count("\n", 0, start_pos)
        )

        end_line = (
            base_line
            + source.count(
                "\n",
                0,
                max(start_pos, end_pos - 1),
            )
        )

        return start_line, end_line

    @staticmethod
    def _remove_table_placeholders(text: str) -> str:
        """
        从正文中移除表格占位符。

        表格会单独生成检索切片，因此不应该将占位符作为普通正文
        交给子块切分器或 Embedding。

        Args:
            text: 原始文本。

        Returns:
            移除表格占位符后的文本。
        """

        return AdvancedMarkdownChunker.TABLE_PLACEHOLDER_PATTERN.sub(
            "",
            text,
        )

    # ========================================================
    # SectionGroup 组合与来源映射
    # ========================================================

    @staticmethod
    def _build_group_source(
        group: SectionGroup,
        section_indexes: dict[int, int],
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        将一个 SectionGroup 组合为父块切分使用的来源文本。

        注意：
            组合只用于父块切分。
            不会修改原始 Section，也不会丢失章节独立信息。

        Args:
            group: 当前章节分组。
            section_indexes: Section 对象 ID 到原始章节索引的映射。

        Returns:
            group_text:
                当前分组组合后的文本。

            segments:
                每个章节在 group_text 中的字符范围及原始 Section 信息。
        """

        parts: list[str] = []
        segments: list[dict[str, Any]] = []

        cursor = 0

        for section in group.sections:
            # 章节之间添加两个换行符。
            if parts:
                parts.append("\n\n")
                cursor += 2

            section_text = section.content

            start_offset = cursor

            parts.append(section_text)

            cursor += len(section_text)

            segments.append(
                {
                    "section": section,
                    "section_index": section_indexes.get(
                        id(section),
                        -1,
                    ),
                    "start_offset": start_offset,
                    "end_offset": cursor,
                }
            )

        return "".join(parts), segments

    @staticmethod
    def _get_intersections(
        segments: list[dict[str, Any]],
        start_offset: int,
        end_offset: int,
    ) -> list[dict[str, Any]]:
        """
        获取当前切片与各章节之间的交集。

        一个父块可能包含多个章节，因此需要确定：
            1. 当前父块涉及哪些章节。
            2. 每个章节实际贡献了哪些正文。
            3. 每段正文属于哪个标题路径。

        Args:
            segments: SectionGroup 的章节位置映射。
            start_offset: 当前切片起始字符位置。
            end_offset: 当前切片结束字符位置。

        Returns:
            交集列表，每项包含原始 Section 和对应局部字符范围。
        """

        results: list[dict[str, Any]] = []

        for segment in segments:
            intersection_start = max(
                start_offset,
                segment["start_offset"],
            )

            intersection_end = min(
                end_offset,
                segment["end_offset"],
            )

            if intersection_start >= intersection_end:
                continue

            local_start = (
                intersection_start
                - segment["start_offset"]
            )

            local_end = (
                intersection_end
                - segment["start_offset"]
            )

            section = segment["section"]

            results.append(
                {
                    "section": section,
                    "section_index": segment["section_index"],
                    "local_start": local_start,
                    "local_end": local_end,
                    "content": section.content[
                        local_start:local_end
                    ],
                }
            )

        return results

    @staticmethod
    def _get_source_range(
        intersections: list[dict[str, Any]],
    ) -> tuple[int, int] | None:
        """
        根据章节交集计算切片在原文中的行号范围。

        不使用组合文本的行号计算，避免章节间添加分隔符后
        导致原文行号发生偏移。

        Args:
            intersections: 当前切片涉及的章节交集。

        Returns:
            原文起止行号；没有有效交集时返回 None。
        """

        ranges: list[tuple[int, int]] = []

        for item in intersections:
            section: TextSection = item["section"]

            local_start = item["local_start"]
            local_end = item["local_end"]

            if local_start >= local_end:
                continue

            start_line = (
                section.start_line
                + section.content.count("\n", 0, local_start)
            )

            end_line = (
                section.start_line
                + section.content.count(
                    "\n",
                    0,
                    max(local_start, local_end - 1),
                )
            )

            ranges.append(
                (start_line, end_line)
            )

        if not ranges:
            return None

        return (
            min(item[0] for item in ranges),
            max(item[1] for item in ranges),
        )

    @classmethod
    def _build_embedding_segments(
        cls,
        intersections: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        根据章节交集构建 Embedding 所需的分段信息。

        每个分段分别保留：
            - heading_path
            - content

        这样跨章节父块在向量化时，可以分别使用各自的标题路径。

        Args:
            intersections: 当前切片涉及的章节交集。

        Returns:
            Embedding 分段列表。
        """

        results: list[dict[str, Any]] = []

        for item in intersections:
            section: TextSection = item["section"]

            segment_content = cls._remove_table_placeholders(
                item["content"]
            ).strip()

            if not segment_content:
                continue

            results.append(
                {
                    "heading_path": list(section.heading_path),
                    "content": segment_content,
                }
            )

        return results

    @staticmethod
    def _build_heading_paths(
        intersections: list[dict[str, Any]],
    ) -> list[list[str]]:
        """
        获取当前切片涉及的所有唯一标题路径。

        Args:
            intersections: 当前切片涉及的章节交集。

        Returns:
            去重后的标题路径列表。
        """

        results: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()

        for item in intersections:
            heading_path = list(
                item["section"].heading_path
            )

            key = tuple(heading_path)

            if key in seen:
                continue

            seen.add(key)
            results.append(heading_path)

        return results

    # ========================================================
    # 表格切片
    # ========================================================

    def _split_table(
        self,
        table: MarkdownTable,
    ) -> list[dict[str, Any]]:
        """
        将大型 Markdown 表格拆分为多个表格切片。

        处理规则：
            1. 表头和分隔行在每个切片中重复。
            2. 按数据行进行拆分。
            3. 支持相邻表格切片重复指定数量的数据行。
            4. 保留每个表格部分的原文行号。

        Args:
            table: 已经提取出来的 MarkdownTable。

        Returns:
            表格切片列表，每项包含 content、part_index、
            part_count 和行号。
        """

        lines = table.content.splitlines()

        # 不需要拆分的表格。
        if (
            len(table.content) <= self.table_chunk_size
            or len(lines) < 3
        ):
            return [
                {
                    "content": table.content,
                    "part_index": 0,
                    "part_count": 1,
                    "source_start_line": table.start_line,
                    "source_end_line": table.end_line,
                }
            ]

        header_lines = lines[:2]
        data_lines = lines[2:]

        groups: list[list[tuple[str, int]]] = []

        current: list[tuple[str, int]] = []

        def build(
            rows: list[tuple[str, int]],
        ) -> str:
            """
            将表头、分隔行和数据行组合为 Markdown 表格。

            Args:
                rows: 当前表格部分的数据行及其原文行号。

            Returns:
                完整 Markdown 表格文本。
            """

            return "\n".join(
                header_lines
                + [row for row, _ in rows]
            )

        for row_idx, row in enumerate(
            data_lines,
            start=table.start_line + 2,
        ):
            candidate = build(
                current + [(row, row_idx)]
            )

            if (
                current
                and len(candidate) > self.table_chunk_size
            ):
                groups.append(current)

                overlap = min(
                    self.table_row_overlap,
                    len(current),
                )

                current = (
                    current[-overlap:]
                    if overlap
                    else []
                )

            current.append(
                (row, row_idx)
            )

        if current:
            groups.append(current)

        result: list[dict[str, Any]] = []

        for idx, group in enumerate(groups):
            result.append(
                {
                    "content": build(group),
                    "part_index": idx,
                    "part_count": len(groups),
                    # 每个部分都包含表头，因此起始行是表格表头行。
                    "source_start_line": table.start_line,
                    "source_end_line": group[-1][1],
                }
            )

        return result

    # ========================================================
    # 核心切片流程
    # ========================================================

    async def process(
        self,
        *,
        content: str,
        ctx: Dict,
        source_type: str | None = None,
        filename: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        执行完整文档切片流程。

        处理顺序：
            1. 校验输入。
            2. 识别文档类型。
            3. 提取 Markdown 表格。
            4. 按标题划分 Section。
            5. 合并符合条件的短章节。
            6. 按 SectionGroup 生成父块。
            7. 根据父块与原始 Section 的关系生成子块。
            8. 为父块和子块记录标题路径及原文行号。
            9. 为表格建立独立检索切片。
            10. 建立表格与父块的关联。
            11. 返回全部切片。

        Args:
            content:
                文档解析后的原始文本。

            ctx:
                任务上下文，必须包含 document_uid。
                用于进度推送和日志关联。

            source_type:
                文档类型，例如 md、txt、pdf、docx。
                如果没有提供，则尝试从 filename 获取。

            filename:
                原始文件名，用于推断文档类型。

        Returns:
            切片字典列表。

            每个切片包含：
                tmp_id
                document_uid
                parent_id
                is_parent
                content
                chunk_index
                metadata
                embedding
                source_start_line
                source_end_line
        """

        document_uid = (ctx or {}).get(
            "document_uid",
            "",
        )

        await emit(
            "[切分] 接收到解析结果，准备开始切片",
            ctx=ctx,
        )

        # ----------------------------------------------------
        # 1. 输入校验
        # ----------------------------------------------------

        if not isinstance(content, str):
            logger.error(
                "[Chunker][DOC-%s] 输入校验失败：content 不是字符串",
                document_uid,
            )

            await emit(
                "[切分] 失败：输入内容不是字符串",
                ctx=ctx,
            )

            raise TypeError("content 必须是字符串")

        source_text = self._normalize_newlines(content)
        # 清理文档中的空 HTML 锚点，保留换行结构。
        source_text = self._remove_empty_html_anchors(source_text)
        if not source_text.strip():
            await emit(
                "[切分] 文档内容为空，跳过切片",
                ctx=ctx,
            )

            return []

        original_lines = source_text.split("\n")

        # ----------------------------------------------------
        # 2. 识别文档类型
        # ----------------------------------------------------

        normalized_type = (
            source_type or ""
        ).strip().lower()

        if not normalized_type and filename:
            normalized_type = (
                Path(filename).suffix.lower().lstrip(".")
            )

        if normalized_type in {
            "txt",
            "text",
            "plain",
            "plain_text",
        }:
            is_plain_text = True

        elif normalized_type in {
            "md",
            "markdown",
            "pdf",
            "docx",
            "",
        }:
            is_plain_text = False

        else:
            logger.error(
                "[Chunker][DOC-%s] 不支持的 source_type：%s",
                document_uid,
                normalized_type,
            )

            await emit(
                f"[切分] 不支持的文档类型 ({normalized_type})，切片中止",
                ctx=ctx,
            )

            raise ValueError(
                f"不支持的切片 source_type: {normalized_type}"
            )

        await emit(
            (
                f"[切分] 已识别文档类型："
                f"{'纯文本' if is_plain_text else 'Markdown'}，"
                f"共 {len(original_lines)} 行"
            ),
            ctx=ctx,
        )

        # ----------------------------------------------------
        # 3. 提取 Markdown 表格
        # ----------------------------------------------------

        if is_plain_text:
            protected_lines = list(original_lines)

            tables: list[MarkdownTable] = []

            await emit(
                "[切分] 纯文本模式，不单独提取表格",
                ctx=ctx,
            )

        else:
            await emit(
                "[切分] 正在扫描并提取 Markdown 表格",
                ctx=ctx,
            )

            protected_lines, tables = self._extract_tables(
                original_lines
            )

            await emit(
                f"[切分] 表格扫描完成，共发现 {len(tables)} 个表格",
                ctx=ctx,
            )

        table_by_placeholder = {
            table.placeholder: table
            for table in tables
        }

        # ----------------------------------------------------
        # 4. 划分 Section
        # ----------------------------------------------------

        sections = self._split_sections(
            protected_lines,
            is_plain_text,
        )

        # 记录每个 Section 在原始 sections 中的索引。
        section_indexes = {
            id(section): index
            for index, section in enumerate(sections)
        }

        chunks: list[dict[str, Any]] = []

        chunk_index = 0

        # 表格 UID -> 关联父块 UID。
        table_parent_map: dict[str, str] = {}

        await emit(
            (
                f"[切分] 文档结构分析完成，包含 {len(sections)} 个章节，"
                f"开始分析短章节合并"
            ),
            ctx=ctx,
        )

        # ----------------------------------------------------
        # 5. 合并短章节
        # ----------------------------------------------------

        section_groups = self._merge_short_sections(
            sections
        )

        await emit(
            (
                f"[切分] 短章节合并完成："
                f"{len(sections)} 个章节合并为 "
                f"{len(section_groups)} 个分组"
            ),
            ctx=ctx,
        )

        # ----------------------------------------------------
        # 6. 按 SectionGroup 生成父块和子块
        # ----------------------------------------------------

        for group_index, group in enumerate(
            section_groups
        ):
            # 组合当前 Group 的章节文本。
            group_text, group_segments = self._build_group_source(
                group,
                section_indexes,
            )

            if not group_text.strip():
                continue

            await emit(
                (
                    f"[切分] 正在处理章节分组 "
                    f"{group_index + 1}/{len(section_groups)}，"
                    f"包含 {len(group.sections)} 个章节，"
                    f"正文长度 {len(group_text)}"
                ),
                ctx=ctx,
            )

            # 对整个分组进行父块切分。
            parent_texts = self.parent_splitter.split_text(
                group_text
            )

            parent_search_from = 0

            for parent_part_index, parent_text in enumerate(
                parent_texts
            ):
                if not parent_text.strip():
                    continue

                # ------------------------------------------------
                # 6.1 定位父块在 Group 中的字符范围
                # ------------------------------------------------

                parent_span = self._find_piece_span(
                    group_text,
                    parent_text,
                    parent_search_from,
                )

                if parent_span is not None:
                    parent_start_offset, parent_end_offset = (
                        parent_span
                    )

                    # 保留 overlap，下一次搜索从当前位置之后开始。
                    parent_search_from = max(
                        0,
                        parent_start_offset + 1,
                    )

                else:
                    # 无法定位时，保守使用整个 Group 范围。
                    parent_start_offset = 0
                    parent_end_offset = len(group_text)

                # ------------------------------------------------
                # 6.2 找出父块涉及的章节
                # ------------------------------------------------

                parent_intersections = self._get_intersections(
                    group_segments,
                    parent_start_offset,
                    parent_end_offset,
                )

                parent_source_range = self._get_source_range(
                    parent_intersections
                )

                if parent_source_range:
                    parent_start_line, parent_end_line = (
                        parent_source_range
                    )

                else:
                    parent_start_line = group.sections[0].start_line
                    parent_end_line = group.sections[-1].end_line

                # ------------------------------------------------
                # 6.3 构建父块内容
                # ------------------------------------------------

                parent_tmp_id = self._new_id()

                parent_content = parent_text

                # 表格占位符替换为说明文字，并记录父块关系。
                for placeholder, table in table_by_placeholder.items():
                    marker = f"[[{placeholder}]]"

                    if marker not in parent_content:
                        continue

                    table_parent_map[table.tmp_id] = parent_tmp_id

                    parent_content = parent_content.replace(
                        marker,
                        (
                            "[表格内容已单独建立检索切片；"
                            f"表格编号：{table.tmp_id}]"
                        ),
                    )

                # 父块标题路径。
                parent_heading_paths = self._build_heading_paths(
                    parent_intersections
                )

                # 为后续 Embedding 保留每个章节的独立正文。
                parent_embedding_segments = (
                    self._build_embedding_segments(
                        parent_intersections
                    )
                )

                parent_metadata: dict[str, Any] = {
                    "type": "parent",
                    "heading_paths": parent_heading_paths,
                    "section_indexes": list(
                        dict.fromkeys(
                            item["section_index"]
                            for item in parent_intersections
                        )
                    ),
                    "group_index": group_index,
                    "parent_part_index": parent_part_index,
                    "embedding_segments": parent_embedding_segments,
                }

                # 只有一个标题路径时，兼容旧版 heading_path。
                if len(parent_heading_paths) == 1:
                    parent_metadata["heading_path"] = (
                        parent_heading_paths[0]
                    )

                parent_chunk = self._make_chunk(
                    document_uid=document_uid,
                    content=parent_content,
                    tmp_id=parent_tmp_id,
                    parent_id=None,
                    is_parent=True,
                    chunk_index=chunk_index,
                    metadata=parent_metadata,
                    source_start_line=parent_start_line,
                    source_end_line=parent_end_line,
                )

                chunks.append(parent_chunk)

                await emit(
                    (
                        f"[切分] 已生成父块 "
                        f"(行 {parent_start_line}-{parent_end_line}，"
                        f"长度 {len(parent_content)}，"
                        f"涉及章节 {len(parent_heading_paths)} 个)"
                    ),
                    ctx=ctx,
                )

                chunk_index += 1

                # ------------------------------------------------
                # 6.4 根据父块涉及的章节生成子块
                # ------------------------------------------------

                # 不直接对整个父块切分。
                # 按章节分别切分，防止子块跨章节后标题路径丢失。
                for intersection in parent_intersections:
                    section: TextSection = intersection["section"]

                    local_start = intersection["local_start"]
                    local_end = intersection["local_end"]

                    section_piece = section.content[
                        local_start:local_end
                    ]

                    # 子块不包含表格占位符。
                    child_source = self._remove_table_placeholders(
                        section_piece
                    )

                    if not child_source.strip():
                        continue

                    child_texts = self.child_splitter.split_text(
                        child_source
                    )

                    child_search_from = 0

                    # 计算当前父块在该 Section 中对应的原文起始行。
                    section_base_line = (
                        section.start_line
                        + section.content.count(
                            "\n",
                            0,
                            local_start,
                        )
                    )

                    for child_part_index, child_text in enumerate(
                        child_texts
                    ):
                        if not child_text.strip():
                            continue

                        # 计算子块在当前 Section 片段中的行号。
                        child_span = self._line_range_for_piece(
                            child_source,
                            child_text,
                            child_search_from,
                            section_base_line,
                        )

                        if child_span:
                            child_start_line, child_end_line = (
                                child_span
                            )

                            found = child_source.find(
                                child_text.strip(),
                                child_search_from,
                            )

                            if found >= 0:
                                child_search_from = max(
                                    0,
                                    found + 1,
                                )

                        else:
                            # 定位失败时，回退到当前 Section 交集范围。
                            child_start_line = section_base_line

                            child_end_line = (
                                section_base_line
                                + max(
                                    0,
                                    child_source.count("\n"),
                                )
                            )

                        child_embedding_segments = [
                            {
                                "heading_path": list(
                                    section.heading_path
                                ),
                                "content": child_text.strip(),
                            }
                        ]

                        child_metadata: dict[str, Any] = {
                            "type": "text",
                            "heading_path": list(
                                section.heading_path
                            ),
                            "heading_paths": [
                                list(section.heading_path)
                            ],
                            "section_index": intersection[
                                "section_index"
                            ],
                            "group_index": group_index,
                            "parent_part_index": parent_part_index,
                            "child_part_index": child_part_index,
                            "embedding_segments": (
                                child_embedding_segments
                            ),
                        }

                        child_chunk = self._make_chunk(
                            document_uid=document_uid,
                            content=child_text,
                            tmp_id=self._new_id(),
                            parent_id=parent_tmp_id,
                            is_parent=False,
                            chunk_index=chunk_index,
                            metadata=child_metadata,
                            source_start_line=child_start_line,
                            source_end_line=child_end_line,
                        )

                        chunks.append(child_chunk)

                        chunk_index += 1

        # ----------------------------------------------------
        # 7. 生成独立表格切片
        # ----------------------------------------------------

        for table_index, table in enumerate(
            tables,
            start=1,
        ):
            await emit(
                (
                    f"[切分] 正在处理表格 "
                    f"{table_index}/{len(tables)}"
                ),
                ctx=ctx,
            )

            parent_tmp_id = table_parent_map.get(
                table.tmp_id
            )

            table_heading_path = list(
                table.heading_path
            )

            # 如果表格没有对应的正文父块，则创建独立父块。
            if parent_tmp_id is None:
                parent_tmp_id = self._new_id()

                parent_metadata: dict[str, Any] = {
                    "type": "parent",
                    "heading_path": table_heading_path,
                    "heading_paths": [table_heading_path],
                    "contains_table": True,
                    "table_id": table.tmp_id,
                }

                parent_chunk = self._make_chunk(
                    document_uid=document_uid,
                    content=(
                        f"[关联表格内容，表格编号：{table.tmp_id}]"
                    ),
                    tmp_id=parent_tmp_id,
                    parent_id=None,
                    is_parent=True,
                    chunk_index=chunk_index,
                    metadata=parent_metadata,
                    source_start_line=table.start_line,
                    source_end_line=table.end_line,
                )

                chunks.append(parent_chunk)

                chunk_index += 1

            # 拆分大型表格。
            table_parts = self._split_table(table)

            for part in table_parts:
                table_metadata: dict[str, Any] = {
                    "type": "table",
                    "heading_path": table_heading_path,
                    "heading_paths": [table_heading_path],
                    "table_id": table.tmp_id,
                    "table_part_index": part["part_index"],
                    "table_part_count": part["part_count"],
                }

                table_chunk = self._make_chunk(
                    document_uid=document_uid,
                    content=part["content"],
                    tmp_id=self._new_id(),
                    parent_id=parent_tmp_id,
                    is_parent=False,
                    chunk_index=chunk_index,
                    metadata=table_metadata,
                    source_start_line=part.get(
                        "source_start_line",
                        table.start_line,
                    ),
                    source_end_line=part.get(
                        "source_end_line",
                        table.end_line,
                    ),
                )

                chunks.append(table_chunk)

                chunk_index += 1

        # ----------------------------------------------------
        # 8. 完成统计
        # ----------------------------------------------------

        parent_count = sum(
            1 for chunk in chunks
            if chunk["is_parent"]
        )

        child_count = len(chunks) - parent_count

        logger.info(
            (
                "文档切片完成：document_uid=%s, "
                "source_type=%s, sections=%d, groups=%d, "
                "tables=%d, parents=%d, children=%d, chunks=%d"
            ),
            document_uid,
            "txt" if is_plain_text else "markdown",
            len(sections),
            len(section_groups),
            len(tables),
            parent_count,
            child_count,
            len(chunks),
        )

        await emit(
            (
                f"[切分] 文档切片全部完成，"
                f"原始章节 {len(sections)} 个，"
                f"合并后分组 {len(section_groups)} 个，"
                f"父块 {parent_count} 个，"
                f"子块 {child_count} 个，"
                f"表格 {len(tables)} 个，"
                f"总计 {len(chunks)} 个切块"
            ),
            ctx=ctx,
        )

        return chunks


# ============================================================
# 全局切片器实例
# ============================================================

@lru_cache(maxsize=1)
def get_document_chunker() -> AdvancedMarkdownChunker:
    """
    获取全局复用的文档切片器实例。

    使用 lru_cache 避免每次处理文档时重复创建
    RecursiveCharacterTextSplitter。

    Returns:
        AdvancedMarkdownChunker 实例。
    """

    return AdvancedMarkdownChunker()