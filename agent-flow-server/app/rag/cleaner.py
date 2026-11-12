"""
文档清洗模块。

职责位置：
    解析（MinerU / 文本解码）之后、切分（AdvancedMarkdownChunker）之前。
    parser 负责把任意格式文档变成文本，本模块负责把这段文本整理成
    结构稳定、可直接切分的 Markdown，chunker 只做纯切分。

处理顺序（顺序有依赖，不可随意调整）：

    阶段 0  字符归一
        换行符、零宽字符、控制字符、全角空格、制表符。

    阶段 1  HTML 结构化
        1. <table> → Markdown 管道表格
           （必须先于「去标签」执行，否则列边界会永久丢失）
        2. <h1>-<h6> → # 标题
        3. 块级标签 → 换行，行内标签 → 只留文字
        4. 最后才做 HTML 实体反转义
           （先反转义会把 &lt;div&gt; 变成真标签，随后被误删）

    阶段 2  结构性去噪（仅 Markdown）
        目录块、页眉页脚重复行、页码行、装饰分隔线、纯图片行；
        相邻双语标题合并、章节层级校正。

    阶段 3  空白归一
        行尾空白、行首缩进、连续空行、标题前后空行。

约束：
    只做格式化，不做语义级删改。
    金额、条款号、日期、期限一律原样保留 —— 财务/制度类文档错一个字即事故。
    结构性删除一律用「空行占位」，尽量不改变行号，
    使切片的 source_start_line / source_end_line 仍能对应到解析文本。
"""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field


# ============================================================
# 阶段 0：字符级正则
# ============================================================

# 零宽字符、方向控制符、软连字符、BOM、不可见控制字符。
_ZERO_WIDTH_PATTERN = re.compile(
    "["
    "\ufeff"          # BOM
    "\u200b-\u200f"   # 零宽空格 / 零宽连接符 / 方向标记
    "\u202a-\u202e"   # 方向控制符
    "\u2060-\u2063"   # 词连接符
    "\u00ad"          # 软连字符
    "\x00-\x08\x0b\x0c\x0e-\x1f"  # 控制字符（保留 \n \t）
    "]"
)

# 各种「看起来是空格」的字符统一成半角空格。
_SPACE_TRANSLATION = str.maketrans(
    {
        "\u00a0": " ",  # &nbsp;
        "\u3000": " ",  # 全角空格
        "\u2000": " ",
        "\u2001": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\t": " ",
        "\v": " ",
        "\f": " ",
    }
)


# ============================================================
# 阶段 1：HTML 正则
# ============================================================

_HTML_TABLE_PATTERN = re.compile(r"<table\b[^>]*>(.*?)</table\s*>", re.I | re.S)
_HTML_ROW_PATTERN = re.compile(r"<tr\b[^>]*>(.*?)</tr\s*>", re.I | re.S)
# 单元格允许缺失闭合标签：用「下一个单元格 / 行结束 / 文本结束」兜底。
_HTML_CELL_PATTERN = re.compile(
    r"<t([dh])\b([^>]*)>(.*?)(?:</t[dh]\s*>|(?=<t[dh]\b)|$)",
    re.I | re.S,
)
_HTML_HEADING_PATTERN = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1\s*>", re.I | re.S)
_BR_PATTERN = re.compile(r"<br\s*/?>", re.I)
_BLOCK_END_PATTERN = re.compile(
    r"</(?:p|div|section|article|li|tr|h[1-6]|ul|ol|blockquote|pre|table|dd|dt)\s*>",
    re.I,
)
_LI_OPEN_PATTERN = re.compile(r"<li\b[^>]*>", re.I)
_ANY_TAG_PATTERN = re.compile(r"<[^<>]*>")
_RESIDUAL_TAG_PATTERN = re.compile(
    r"</?[a-zA-Z][a-zA-Z0-9:_.-]*(?:\s[^<>]{0,200})?/?>"
)

# 空 HTML 锚点：MinerU 等工具会输出 <a id="heading_9"></a> 这类纯锚点。
_EMPTY_ANCHOR_PATTERN = re.compile(
    r'<a\b[^>]*\bid\s*=\s*["\']?[^"\'>\s]+["\']?[^>]*>\s*</a>',
    re.I,
)


# ============================================================
# 阶段 2：Markdown 结构正则
# ============================================================

_MD_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")

# 目录标题：## 目录 / ## 目 录 / ## Contents / ## Table of Contents
_TOC_HEADING_PATTERN = re.compile(
    r"^#{1,6}[ \t]*(?:目[ \t]*录|目[ \t]*次|contents?|table\s+of\s+contents)[ \t]*$",
    re.I,
)

# 点线目录行：第一章 总则 . . . . . . 1 / 第一章 总则 ...... 1 / 第一章 总则 …… 1
_DOT_LEADER_PATTERN = re.compile(
    r"^[ \t]*\S.{0,90}?(?:[.·…][ \t]*){3,}\d{1,4}[ \t]*$"
)

# 页码行：3 / - 3 - / 第 3 页 / 第 3 页 共 10 页 / 3/10 / 共 10 页
_PAGE_NUMBER_PATTERN = re.compile(
    r"^[ \t]*[-—–·]?[ \t]*(?:第[ \t]*)?\d{1,4}[ \t]*"
    r"(?:"
    r"页[ \t]*(?:[/共][ \t]*\d{1,4}[ \t]*页?)?"
    r"|/[ \t]*\d{1,4}"
    r"|共[ \t]*\d{1,4}[ \t]*页"
    r")?"
    r"[ \t]*[-—–·]?[ \t]*$"
)

# 装饰分隔线：----、====、﹏﹏﹏、****
_SEPARATOR_PATTERN = re.compile(r"^[ \t]*(?:[-=*_·•—–~﹏※#][ \t]*){3,}$")

# 纯标点行：。。。。、，，，
_PUNCT_ONLY_PATTERN = re.compile(r"^[ \t]*[，。、；：,.;:!?！？…·]{2,}[ \t]*$")

# 纯图片行：![](images/xxx.jpg)
_IMAGE_ONLY_PATTERN = re.compile(r"^[ \t]*!\[([^\]]*)\]\([^)]*\)[ \t]*$")

# 章节序号：第X章 / 第X节 / 第X条
_CJK_NUM = "一二三四五六七八九十百千零〇两"
_CHAPTER_PATTERN = re.compile(rf"^第[ \t]*[{_CJK_NUM}\d]+[ \t]*章")
_SECTION_PATTERN = re.compile(rf"^第[ \t]*[{_CJK_NUM}\d]+[ \t]*节")
_ARTICLE_PATTERN = re.compile(rf"^第[ \t]*[{_CJK_NUM}\d]+[ \t]*条")

# Markdown 列表 / 引用行前缀，用于判断行首缩进是否要保留。
_MD_PREFIX_PATTERN = re.compile(r"^(?:[-*+][ \t]|\d+[.)][ \t]|>|#|\|)")

# 加粗片段：**文本**（非贪婪，避免跨段误吞）
_BOLD_SPAN_PATTERN = re.compile(r"\*\*(.+?)\*\*")

# 整行加粗：行内只有一个加粗片段且没有其他可见文本（标题/小节名的常见转出形态），
# 第二组捕获尾随的冒号等标点，去壳时原样保留
_WHOLE_LINE_BOLD_PATTERN = re.compile(r"^[ \t]*\*\*(.+?)\*\*([ \t:：]*)$")

# 表格行：以 | 开头（允许缩进）
_TABLE_LINE_PATTERN = re.compile(r"^[ \t]*\|")

# 中文字符，用于判断标题是否属于中文/英文双标题。
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")


# ============================================================
# 清洗统计
# ============================================================

@dataclass
class CleanStats:
    """
    清洗过程的命中统计，用于日志与问题排查。

    Attributes:
        original_chars: 清洗前字符数。
        cleaned_chars: 清洗后字符数。
        hits: 规则名 -> 命中次数（字符类规则记录字符数）。
        rollback: 是否触发了内容保护回滚。
    """

    original_chars: int = 0
    cleaned_chars: int = 0
    hits: dict[str, int] = field(default_factory=dict)
    rollback: bool = False

    def hit(self, name: str, count: int = 1) -> None:
        """记录一次规则命中。"""
        if count <= 0:
            return
        self.hits[name] = self.hits.get(name, 0) + int(count)

    def summary(self) -> str:
        """生成一行可读摘要，供日志与进度推送使用。"""
        details = "、".join(
            f"{name} {count}"
            for name, count in self.hits.items()
            if count > 0
        )

        if not details:
            details = "未发现结构性噪声"

        return (
            f"{self.original_chars:,} → {self.cleaned_chars:,} 字符；"
            f"{details}"
        )


# ============================================================
# 清洗器
# ============================================================

class DocumentCleaner:
    """
    文档清洗器：把解析结果整理成结构稳定的 Markdown。

    典型用法：

        cleaner = get_document_cleaner()
        text, stats = cleaner.clean(md_text, is_markdown=True)
        logger.info("清洗完成：%s", stats.summary())

    Attributes:
        MIN_KEEP_RATIO: 内容保护阈值，结构清洗后低于该比例则回滚。
        MIN_GUARD_CHARS: 启用内容保护的最小文本长度。
            太短的文本（片段、短消息）删除几行就会低于阈值，
            没有参考意义，因此不触发保护。
        REPEATED_LINE_MIN_COUNT: 页眉页脚判定的最小重复次数。
        PAGE_NUMBER_MIN_COUNT: 页码行判定的最小命中次数。
        TOC_MIN_LINES: 点线目录块判定的最小连续行数。
        HEADING_MERGE_MAX_LEN: 相邻标题合并后的最大长度。
        ARTICLE_TITLE_MAX_LEN: 条级标题的最大长度（超过说明是正文，不升级为标题）。
    """

    MIN_KEEP_RATIO = 0.4
    MIN_GUARD_CHARS = 500
    REPEATED_LINE_MIN_COUNT = 3
    PAGE_NUMBER_MIN_COUNT = 3
    TOC_MIN_LINES = 2
    HEADING_MERGE_MAX_LEN = 120
    ARTICLE_TITLE_MAX_LEN = 30

    def __init__(
        self,
        *,
        normalize_heading_levels: bool = True,
        merge_bilingual_headings: bool = True,
    ) -> None:
        """
        初始化清洗器。

        Args:
            normalize_heading_levels:
                是否按「第X章 / 第X节 / 第X条」校正标题层级。
                PDF 转换出的标题层级常常不可靠（条与章同为 H2），
                校正后 heading_path 才能正确表达从属关系。

            merge_bilingual_headings:
                是否合并相邻的同级标题。
                中英文双标题（# 中文名 / # English Name）如果不合并，
                英文标题会成为后续所有章节 heading_path 的根节点。
        """

        self.normalize_heading_levels = normalize_heading_levels
        self.merge_bilingual_headings = merge_bilingual_headings

    # ========================================================
    # 对外入口
    # ========================================================

    def clean(
        self,
        text: str,
        *,
        is_markdown: bool = True,
    ) -> tuple[str, CleanStats]:
        """
        执行完整清洗流程。

        Args:
            text: 解析得到的原始文本。
            is_markdown: 是否按 Markdown 处理。
                False（纯文本）只做字符归一与空白归一，
                跳过 HTML 与目录/标题相关规则，避免误伤 txt 正文。

        Returns:
            (清洗后的文本, 清洗统计)。
        """

        stats = CleanStats(original_chars=len(text or ""))

        if not text or not text.strip():
            stats.cleaned_chars = 0
            return "", stats

        # 阶段 0：字符归一。
        text = self._normalize_characters(text, stats)

        if is_markdown:
            # 阶段 1 的结果作为内容保护基线：
            # 阶段 2 若误删过多，回滚到这里，而不是回到满是 HTML 的原始文本。
            baseline = text

            # 阶段 1：HTML 结构化。
            text = self._normalize_html(text, stats)

            # 阶段 2：结构性去噪。
            text = self._remove_structural_noise(
                text,
                stats,
                normalize_headings=self.normalize_heading_levels,
                merge_headings=self.merge_bilingual_headings,
            )

            if self._should_rollback(baseline, text):
                stats.rollback = True
                stats.hit("内容保护回滚", 1)
                text = baseline

            # 阶段 3：空白归一（Markdown 结构感知）。
            text = self._normalize_whitespace(text, stats, is_markdown=True)

        else:
            text = self._normalize_whitespace(text, stats, is_markdown=False)

        stats.cleaned_chars = len(text)

        return text, stats

    def _should_rollback(self, baseline: str, cleaned: str) -> bool:
        """
        判断结构性清洗是否删除过多内容。

        判定口径：
            1. 只对足够长的文档启用保护，短文本删除几行就会低于阈值。
            2. 按非空白字符数比较，避免空行占位影响比例。

        Args:
            baseline: 阶段 0 + 阶段 1 之后的文本。
            cleaned: 阶段 2 之后的文本。

        Returns:
            是否需要回滚。
        """

        if len(baseline) < self.MIN_GUARD_CHARS:
            return False

        baseline_size = len(re.sub(r"\s", "", baseline))
        cleaned_size = len(re.sub(r"\s", "", cleaned))

        if baseline_size == 0:
            return False

        return cleaned_size < baseline_size * self.MIN_KEEP_RATIO

    # ========================================================
    # 阶段 0：字符归一
    # ========================================================

    @staticmethod
    def _normalize_characters(text: str, stats: CleanStats) -> str:
        """
        统一换行符、清除不可见字符、归一各类空白字符。

        Args:
            text: 原始文本。
            stats: 清洗统计。

        Returns:
            归一后的文本。
        """

        # 换行符统一：Windows / 老式 Mac / Unicode 行分隔符。
        text = (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\u2028", "\n")
            .replace("\u2029", "\n")
        )

        # 零宽字符与控制字符：会让 "# "、表格正则等匹配失败，也会污染向量。
        cleaned = _ZERO_WIDTH_PATTERN.sub("", text)

        if len(cleaned) != len(text):
            stats.hit("零宽/控制字符", len(text) - len(cleaned))

        text = cleaned

        # 全角空格、&nbsp;、制表符等统一成半角空格。
        return text.translate(_SPACE_TRANSLATION)

    # ========================================================
    # 阶段 1：HTML 结构化
    # ========================================================

    def _normalize_html(self, text: str, stats: CleanStats) -> str:
        """
        把 HTML 片段转换为 Markdown 结构。

        步骤顺序不可调整：
            表格 → 标题 → 块级断行 → 行内去标签 → 实体反转义 → 残留兜底。

        Args:
            text: 字符归一后的文本。
            stats: 清洗统计。

        Returns:
            去除 HTML 结构后的 Markdown 文本。
        """

        # 1. 表格必须先转换，否则下面一旦把标签去掉，列与列的边界就没了。
        text, converted, dropped = self._convert_html_tables(text)

        stats.hit("HTML 表格转 Markdown", converted)
        stats.hit("丢弃空表/无效表", dropped)

        # 2. HTML 标题 → Markdown 标题。
        def _heading_repl(match: re.Match) -> str:
            level = int(match.group(1))
            title = _ANY_TAG_PATTERN.sub("", match.group(2))
            title = html.unescape(title).strip()

            if not title:
                return "\n"

            return f"\n\n{'#' * level} {title}\n\n"

        text, heading_count = _HTML_HEADING_PATTERN.subn(_heading_repl, text)

        stats.hit("HTML 标题", heading_count)

        # 3. 空锚点：只删锚点本身，保留原有换行结构。
        text, anchor_count = _EMPTY_ANCHOR_PATTERN.subn("", text)

        stats.hit("空 HTML 锚点", anchor_count)

        # 4. 块级标签断行，列表项转 Markdown 列表。
        text = _BR_PATTERN.sub("\n", text)
        text = _BLOCK_END_PATTERN.sub("\n", text)
        text = _LI_OPEN_PATTERN.sub("- ", text)

        # 5. 其余行内标签只去标签保留文字（<span>、<b>、<sup> 等）。
        before_tag = len(text)
        text = _ANY_TAG_PATTERN.sub("", text)
        stats.hit("HTML 标签", before_tag - len(text))

        # 6. 兜底：畸形 / 未闭合标签（必须在实体反转义之前，否则会被反转义出的
        #    正文内容当标签删掉，例如 "&lt;div&gt;" 转义后是正文而非标签）。
        text = _RESIDUAL_TAG_PATTERN.sub("", text)

        # 7. 实体反转义必须放在去标签之后：
        #    否则 &lt;div&gt; 会先变成真标签，再被上一步当标签删掉。
        text = html.unescape(text)

        return text

    def _convert_html_tables(self, text: str) -> tuple[str, int, int]:
        """
        把 HTML 表格转换为 Markdown 管道表格。

        Args:
            text: 待处理文本。

        Returns:
            (转换后的文本, 成功转换的表格数, 丢弃的表格数)。

        Note:
            转换后是标准管道表格，chunker 现有 AF_TABLE 机制可直接复用，
            再往后的表格切片逻辑无需改动。
        """

        converted = 0
        dropped = 0

        def _repl(match: re.Match) -> str:
            nonlocal converted, dropped

            table_md = self._html_table_to_markdown(match.group(1))

            if table_md is None:
                dropped += 1
                return "\n"

            converted += 1

            return f"\n\n{table_md}\n\n"

        return _HTML_TABLE_PATTERN.sub(_repl, text), converted, dropped

    def _html_table_to_markdown(self, table_html: str) -> str | None:
        """
        将单个 HTML 表格转成 Markdown 管道表格。

        处理要点：
            1. <th> 与 <td> 等价处理，无表头时把首行当表头。
            2. 自动补 | --- | 分隔行（MinerU 输出的表格通常没有表头语义）。
            3. colspan 补空单元格，rowspan 向下填充，避免整行错列。
            4. 单元格内的 <br>、换行转空格，| 转义为 \\|。

        Args:
            table_html: <table> 内部 HTML。

        Returns:
            Markdown 表格文本；无有效内容时返回 None。
        """

        rows_html = _HTML_ROW_PATTERN.findall(table_html)

        if not rows_html:
            return None

        grid: list[list[str]] = []
        # 列索引 -> (剩余跨行数, 单元格文本)
        pending: dict[int, tuple[int, str]] = {}

        for row_html in rows_html:
            cells = _HTML_CELL_PATTERN.findall(row_html)

            if not cells:
                # 没有单元格但有文字：降级为单列表格行。
                text = self._cell_text(row_html)

                if text:
                    grid.append([text])

                continue

            row: list[str] = []
            column = 0
            cell_index = 0

            while cell_index < len(cells):
                # 先补齐上一行 rowspan 延续下来的列。
                while column in pending:
                    remain, value = pending[column]
                    row.append(value)

                    if remain <= 1:
                        del pending[column]
                    else:
                        pending[column] = (remain - 1, value)

                    column += 1

                _, attrs, cell_html = cells[cell_index]

                value = self._cell_text(cell_html)
                colspan = self._attr_int(attrs, "colspan", 1)
                rowspan = self._attr_int(attrs, "rowspan", 1)

                row.append(value)

                if rowspan > 1:
                    pending[column] = (rowspan - 1, value)

                for _ in range(colspan - 1):
                    column += 1
                    row.append("")

                    if rowspan > 1:
                        pending[column] = (rowspan - 1, "")

                column += 1
                cell_index += 1

            # 行末剩余的 rowspan 延续列。
            while column in pending:
                remain, value = pending[column]
                row.append(value)

                if remain <= 1:
                    del pending[column]
                else:
                    pending[column] = (remain - 1, value)

                column += 1

            grid.append(row)

        # 丢弃全空行。
        grid = [row for row in grid if any(cell for cell in row)]

        # 少于两行（只有表头或只有一行数据）的表转成表格没有检索价值。
        if len(grid) < 2:
            return None

        width = max(len(row) for row in grid)
        grid = [row + [""] * (width - len(row)) for row in grid]

        header, body = grid[0], grid[1:]

        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in range(width)) + " |",
        ]

        lines.extend("| " + " | ".join(row) + " |" for row in body)

        return "\n".join(lines)

    @staticmethod
    def _cell_text(cell_html: str) -> str:
        """
        提取单元格纯文本。

        Args:
            cell_html: 单元格内部 HTML。

        Returns:
            压平空白、转义管道符后的文本。
        """

        text = _BR_PATTERN.sub(" ", cell_html)
        text = _ANY_TAG_PATTERN.sub("", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()

        # 管道符会截断列，必须转义。
        return text.replace("|", "\\|")

    @staticmethod
    def _attr_int(attrs: str, name: str, default: int = 1) -> int:
        """
        读取标签属性中的整数值。

        Args:
            attrs: 标签属性字符串。
            name: 属性名，例如 colspan。
            default: 未设置时的默认值。

        Returns:
            属性整数值，非法时返回默认值。
        """

        match = re.search(rf'{name}\s*=\s*["\']?\s*(\d+)', attrs, re.I)

        if not match:
            return default

        value = int(match.group(1))

        return value if value > 0 else default

    # ========================================================
    # 阶段 2：结构性去噪
    # ========================================================

    def _remove_structural_noise(
        self,
        text: str,
        stats: CleanStats,
        *,
        normalize_headings: bool,
        merge_headings: bool,
    ) -> str:
        """
        删除目录、页眉页脚、页码等结构性噪声，并修正标题结构。

        所有删除均用空行占位，尽量保持行号不变。

        Args:
            text: HTML 结构化后的文本。
            stats: 清洗统计。
            normalize_headings: 是否校正章节标题层级。
            merge_headings: 是否合并相邻同级标题。

        Returns:
            去噪后的文本。
        """

        lines = text.split("\n")

        # 1. 目录块（标题命中 + 点线行块）。
        lines, toc_removed = self._remove_toc(lines)

        stats.hit("目录块", toc_removed)

        # 2. 页码行：仅当全篇命中达到阈值才处理，避免误删正文里的孤立数字。
        lines, page_removed = self._remove_page_numbers(lines)

        stats.hit("页码行", page_removed)

        # 3. 页眉页脚 / 水印：多条重复出现的短行。
        lines, repeat_removed = self._remove_repeated_lines(lines)

        stats.hit("页眉页脚重复行", repeat_removed)

        # 4. 纯图片行、装饰分隔线、纯标点行。
        lines, misc_removed = self._remove_decorative_lines(lines)

        stats.hit("图片/装饰行", misc_removed)

        # 5. 冗余强调清理：标题行/表格行/整行加粗里的 ** 是解析引擎的格式残留，
        #    不承载强调语义，还会稀释向量、污染前端预览。
        #    必须在标题层级校正之前：去掉星号的「第X条」行才能被识别为标题。
        lines, stripped = self._strip_redundant_emphasis(lines)

        stats.hit("冗余强调清理", stripped)

        # 6. 章节层级校正（第X章 / 第X节 / 第X条）。
        #    必须在标题合并之前：否则「第二章 职责分工」和「第五条 员工职责」
        #    在层级校正前同为 H2，可能被误判成双标题合并掉。
        if normalize_headings:
            lines, fixed = self._normalize_heading_levels(lines)
            stats.hit("标题层级校正", fixed)

        # 7. 相邻同级标题合并（中英文双标题）。
        if merge_headings:
            lines, merged = self._merge_adjacent_headings(lines)
            stats.hit("相邻标题合并", merged)

        return "\n".join(lines)

    def _remove_toc(self, lines: list[str]) -> tuple[list[str], int]:
        """
        删除目录块。

        两种识别方式：
            1. 标题本身是「目录 / Contents」，删到下一个标题为止。
            2. 连续多行点线目录（第一章 总则 . . . 1）。

        Args:
            lines: 文本行列表。

        Returns:
            (处理后的行列表, 删除行数)。
        """

        output = list(lines)
        removed = 0

        index = 0

        while index < len(output):
            if _TOC_HEADING_PATTERN.match(output[index].strip()):
                output[index] = ""
                removed += 1

                cursor = index + 1

                while cursor < len(output):
                    if _MD_HEADING_PATTERN.match(output[cursor].strip()):
                        break

                    if output[cursor].strip():
                        removed += 1

                    output[cursor] = ""
                    cursor += 1

                index = cursor
                continue

            index += 1

        # 点线目录块：连续多行才删，单行可能是正文中的对齐文本。
        index = 0

        while index < len(output):
            if _DOT_LEADER_PATTERN.match(output[index]):
                cursor = index

                while cursor < len(output) and _DOT_LEADER_PATTERN.match(
                    output[cursor]
                ):
                    cursor += 1

                if cursor - index >= self.TOC_MIN_LINES:
                    for blank_index in range(index, cursor):
                        output[blank_index] = ""
                        removed += 1

                index = cursor
                continue

            index += 1

        return output, removed

    def _remove_page_numbers(self, lines: list[str]) -> tuple[list[str], int]:
        """
        删除页码行。

        Args:
            lines: 文本行列表。

        Returns:
            (处理后的行列表, 删除行数)。
        """

        candidates = [
            index
            for index, line in enumerate(lines)
            if line.strip() and _PAGE_NUMBER_PATTERN.match(line)
        ]

        # 数量不足说明这些数字是正文内容，不是页码。
        if len(candidates) < self.PAGE_NUMBER_MIN_COUNT:
            return lines, 0

        for index in candidates:
            lines[index] = ""

        return lines, len(candidates)

    def _remove_repeated_lines(self, lines: list[str]) -> tuple[list[str], int]:
        """
        删除反复出现的短行（页眉、页脚、水印）。

        判定方式：去掉数字与空格后内容相同、长度 4-40 的短行，
        在全篇出现次数达到阈值即视为版式噪声。

        Args:
            lines: 文本行列表。

        Returns:
            (处理后的行列表, 删除行数)。
        """

        def repeat_key(line: str) -> str | None:
            stripped = line.strip()

            if not 6 <= len(stripped) <= 40:
                return None

            # 标题、表格行、列表、引用不参与。
            if stripped[0] in "#|>-*+":
                return None

            # 以句末标点结尾的通常是正文，不参与。
            if stripped[-1] in "。！？；：，、.!?;:,":
                return None

            key = re.sub(r"[\d\s]", "", stripped)

            return key if len(key) >= 4 else None

        keys = [repeat_key(line) for line in lines]

        counter = Counter(key for key in keys if key)

        repeated = {
            key
            for key, count in counter.items()
            if count >= self.REPEATED_LINE_MIN_COUNT
        }

        if not repeated:
            return lines, 0

        removed = 0

        for index, key in enumerate(keys):
            if key and key in repeated:
                lines[index] = ""
                removed += 1

        return lines, removed

    def _remove_decorative_lines(self, lines: list[str]) -> tuple[list[str], int]:
        """
        删除纯图片行、装饰分隔线、纯标点行。

        图片无法进入向量库，只有 alt 文字有检索价值。

        Args:
            lines: 文本行列表。

        Returns:
            (处理后的行列表, 删除行数)。
        """

        removed = 0

        for index, line in enumerate(lines):
            stripped = line.strip()

            if not stripped:
                continue

            image_match = _IMAGE_ONLY_PATTERN.match(stripped)

            if image_match:
                alt = image_match.group(1).strip()

                if len(alt) >= 2:
                    lines[index] = f"[图: {alt}]"
                else:
                    lines[index] = ""
                    removed += 1

                continue

            if _SEPARATOR_PATTERN.match(stripped) or _PUNCT_ONLY_PATTERN.match(
                stripped
            ):
                lines[index] = ""
                removed += 1

        return lines, removed

    def _merge_adjacent_headings(self, lines: list[str]) -> tuple[list[str], int]:
        """
        合并相邻的同级双语标题（中间只有空行）。

        例如中英文双标题：

            # 财务报销管理制度
            # Financial Reimbursement Management Policy

        合并为一行，避免第二个标题成为后续所有章节的父级。

        合并条件严格限定为「一个中文标题 + 一个纯拉丁标题」或「标题完全相同」，
        避免把「第二章 职责分工」和「第五条 员工职责」这类真实层级误合并。

        Args:
            lines: 文本行列表。

        Returns:
            (处理后的行列表, 合并次数)。
        """

        merged = 0
        index = 0

        while index < len(lines):
            first = _MD_HEADING_PATTERN.match(lines[index].strip())

            if not first:
                index += 1
                continue

            cursor = index + 1

            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1

            second = (
                _MD_HEADING_PATTERN.match(lines[cursor].strip())
                if cursor < len(lines)
                else None
            )

            if not second or len(second.group(1)) != len(first.group(1)):
                index += 1
                continue

            first_title = first.group(2).strip()
            second_title = second.group(2).strip()

            if not self._is_bilingual_pair(first_title, second_title):
                index += 1
                continue

            title = f"{first_title} / {second_title}"

            if len(title) > self.HEADING_MERGE_MAX_LEN:
                index += 1
                continue

            lines[index] = f"{first.group(1)} {title}"
            lines[cursor] = ""
            merged += 1

            # 不移动 index，继续尝试与后面第三个同级标题合并。

        return lines, merged

    @staticmethod
    def _is_bilingual_pair(first: str, second: str) -> bool:
        """
        判断两个标题是否为同一标题的双语写法。

        Args:
            first: 第一个标题文字。
            second: 第二个标题文字。

        Returns:
            是否属于双语标题对。
        """

        if first == second:
            return True

        first_has_cjk = bool(_CJK_PATTERN.search(first))
        second_has_cjk = bool(_CJK_PATTERN.search(second))

        if first_has_cjk == second_has_cjk:
            return False

        # 有中文的那一侧，另一侧必须是纯拉丁标题。
        latin_side = second if first_has_cjk else first

        return bool(_LATIN_PATTERN.search(latin_side))

    def _strip_redundant_emphasis(self, lines: list[str]) -> tuple[list[str], int]:
        """
        清理不承载强调语义的 ``**`` 标记。

        docx/PDF 解析引擎会把 Word 的加粗文字（多为标题、表头）原样转成
        Markdown 的 ``**…**``。这类加粗是格式残留而非强调：

            - 标题行：标题本身已是结构信号，星号是纯噪声；
            - 表格行：管道表首行天然是表头，星号是纯噪声；
            - 整行加粗：事实上的标题（如 ``**第四条 工时制度**``），去星号；
              若内容命中章/节/条模式，直接提升为对应层级标题，
              让 heading_path 能接住这条结构信息；
            - 行内强调（句中部分加粗）：真实的强调语义，原样保留。

        Args:
            lines: 文本行列表。

        Returns:
            (处理后的行列表, 清理的行数)。
        """

        cleaned = 0

        for index, line in enumerate(lines):
            stripped = line.strip()

            if not stripped:
                continue

            # 1. 标题行：去掉 # 后标题文本里的所有加粗壳。
            heading = _MD_HEADING_PATTERN.match(stripped)
            if heading:
                level, title = heading.group(1), heading.group(2)
                new_title = _BOLD_SPAN_PATTERN.sub(r"\1", title)
                if new_title != title:
                    lines[index] = f"{level} {new_title}"
                    cleaned += 1
                continue

            # 2. 表格行：表头加粗是引擎的固定行为，整行去壳。
            if _TABLE_LINE_PATTERN.match(line):
                new_line = _BOLD_SPAN_PATTERN.sub(r"\1", line)
                if new_line != line:
                    lines[index] = new_line
                    cleaned += 1
                continue

            # 3. 整行加粗：去壳；命中章节条模式时提升为标题。
            whole = _WHOLE_LINE_BOLD_PATTERN.match(stripped)
            if whole:
                inner, tail = whole.group(1).strip(), whole.group(2).strip()

                if _CHAPTER_PATTERN.match(inner):
                    lines[index] = f"## {inner}"
                elif _SECTION_PATTERN.match(inner):
                    lines[index] = f"### {inner}"
                elif (
                    _ARTICLE_PATTERN.match(inner)
                    and len(inner) <= self.ARTICLE_TITLE_MAX_LEN
                ):
                    lines[index] = f"#### {inner}"
                else:
                    # 普通整行加粗：只去壳，保留尾随冒号等标点。
                    lines[index] = f"{inner}{tail}"

                cleaned += 1

        return lines, cleaned

    def _normalize_heading_levels(self, lines: list[str]) -> tuple[list[str], int]:
        """
        按「第X章 / 第X节 / 第X条」校正标题层级。

        PDF 转 Markdown 时，条级标题常与章级标题同为 H2，
        导致 heading_path 表达不出从属关系，检索时上下文定位错误。

        校正规则：
            章 → H2，节 → H3，条 → H4。
            条级标题加长度门槛，避免把正文段落当成标题。

        Args:
            lines: 文本行列表。

        Returns:
            (处理后的行列表, 校正条数)。
        """

        fixed = 0

        for index, line in enumerate(lines):
            match = _MD_HEADING_PATTERN.match(line.strip())

            if not match:
                continue

            level = len(match.group(1))
            title = match.group(2).strip()

            if _CHAPTER_PATTERN.match(title):
                target = 2
            elif _SECTION_PATTERN.match(title):
                target = 3
            elif (
                _ARTICLE_PATTERN.match(title)
                and len(title) <= self.ARTICLE_TITLE_MAX_LEN
            ):
                target = 4
            else:
                continue

            if target == level:
                continue

            lines[index] = f"{'#' * target} {title}"
            fixed += 1

        return lines, fixed

    # ========================================================
    # 阶段 3：空白归一
    # ========================================================

    def _normalize_whitespace(
        self,
        text: str,
        stats: CleanStats,
        *,
        is_markdown: bool,
    ) -> str:
        """
        归一空白与段落结构。

        处理内容：
            1. 清除行尾空白。
            2. 压缩连续空行（切分器依赖 \\n\\n 作为段落分隔符）。
            3. Markdown 文档补充标题前后空行、去除正文多余缩进。

        Args:
            text: 待处理文本。
            stats: 清洗统计。
            is_markdown: 是否为 Markdown。

        Returns:
            归一后的文本。
        """

        lines = [line.rstrip() for line in text.split("\n")]

        if is_markdown:
            lines = self._strip_markdown_indent(lines)
            lines = self._ensure_heading_blank_lines(lines)

        text = "\n".join(lines)
        collapsed = re.sub(r"\n{3,}", "\n\n", text)

        if len(collapsed) != len(text):
            stats.hit("压缩连续空行", len(text) - len(collapsed))

        return collapsed.strip("\n")

    @staticmethod
    def _strip_markdown_indent(lines: list[str]) -> list[str]:
        """
        去除正文多余缩进，保留代码块与列表缩进。

        Args:
            lines: 文本行列表。

        Returns:
            处理后的行列表。
        """

        in_fence = False

        for index, line in enumerate(lines):
            stripped = line.strip()

            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue

            if in_fence or not line or not line[0].isspace():
                continue

            # 列表、引用、标题、表格的缩进有语义，保留。
            if _MD_PREFIX_PATTERN.match(stripped):
                continue

            lines[index] = stripped

        return lines

    @staticmethod
    def _ensure_heading_blank_lines(lines: list[str]) -> list[str]:
        """
        保证标题前后各有一个空行。

        标题紧贴正文时，RecursiveCharacterTextSplitter 的首选分隔符 \\n\\n
        会退化，父块边界与章节边界错位。

        Args:
            lines: 文本行列表。

        Returns:
            处理后的行列表。
        """

        output: list[str] = []
        total = len(lines)

        for index, line in enumerate(lines):
            if not _MD_HEADING_PATTERN.match(line.strip()):
                output.append(line)
                continue

            if output and output[-1] != "":
                output.append("")

            output.append(line.strip())

            # 下一行已经是空行就不再补，保证清洗幂等。
            following = lines[index + 1] if index + 1 < total else ""

            if following != "":
                output.append("")

        return output


# ============================================================
# 单例
# ============================================================

_CLEANER: DocumentCleaner | None = None


def get_document_cleaner() -> DocumentCleaner:
    """
    获取全局清洗器实例。

    Returns:
        DocumentCleaner 实例。
    """

    global _CLEANER

    if _CLEANER is None:
        _CLEANER = DocumentCleaner()

    return _CLEANER
