"""
DocumentCleaner 验证脚本。

覆盖场景：
    1. HTML 表格（MinerU 输出形态，无 <th>、无分隔行）→ Markdown 管道表格。
    2. 中英文双 H1 合并，避免英文标题顶掉中文标题成为 heading_path 根节点。
    3. 点线目录块整块删除。
    4. 「第X章 / 第X条」标题层级校正。
    5. 空白归一、行号占位、幂等性。
    6. 纯文本模式跳过 HTML 转换。
    7. 关键业务信息（金额、条款号、文件编号）零丢失。

运行方式：
    python tests/test_cleaner.py
    或 pytest tests/test_cleaner.py
"""

from pathlib import Path
import sys

# 允许直接执行本文件（python tests/test_cleaner.py）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.cleaner import DocumentCleaner

DOCS_DIR = Path(__file__).parent / "docs"
SAMPLE_FILE = DOCS_DIR / "清洗样例-财务报销制度.md"


def _sample_text() -> str:
    """读取财务报销制度样例（MinerU 真实输出形态）。"""
    return SAMPLE_FILE.read_text(encoding="utf-8")


def get_cleaned(text: str | None = None) -> tuple[str, object]:
    """对样例执行清洗，返回清洗结果与统计。"""
    cleaner = DocumentCleaner()
    return cleaner.clean(text if text is not None else _sample_text())


# ============================================================
# 1. HTML 结构还原
# ============================================================

def test_html_table_converted_to_markdown():
    """HTML 表格应全部转成管道表格，且不再残留任何标签。"""
    cleaned, stats = get_cleaned()

    assert "<table" not in cleaned.lower(), "仍残留 <table> 标签"
    assert "</td>" not in cleaned.lower(), "仍残留 </td> 标签"
    assert "&nbsp;" not in cleaned, "仍残留 &nbsp; 实体"

    # 样例包含 9 个表格。
    assert stats.hits.get("HTML 表格转 Markdown") == 9, stats.hits

    # 表头 + 分隔行 + 数据行齐全，说明补出了分隔行。
    assert "| 文件编号 | AFP-FI-2026-002 |" in cleaned
    assert "| --- | --- |" in cleaned


def test_html_table_keeps_cell_content():
    """表格单元格内容与金额不得被改写。"""
    cleaned, _ = get_cleaned()

    assert "380元/晚" in cleaned
    assert "50元/天" in cleaned
    assert "费用发生后5个工作日内" in cleaned


def test_inline_tags_removed_but_text_kept():
    """行内标签只去标签，保留文字。"""
    cleaner = DocumentCleaner()
    raw = '<p><span style="x">重点</span>：<a id="heading_1"></a>请<b>注意</b><br>下一行</p>'
    cleaned, stats = cleaner.clean(raw, is_markdown=True)

    assert "重点" in cleaned and "注意" in cleaned and "下一行" in cleaned
    assert "<" not in cleaned
    assert stats.hits.get("空 HTML 锚点") == 1


def test_html_entity_unescaped_after_tag_strip():
    """实体反转义在去标签之后执行，&lt;div&gt; 不应被当成标签删除。"""
    cleaner = DocumentCleaner()
    cleaned, _ = cleaner.clean("<p>写法 &lt;div&gt; 是标签</p>", is_markdown=True)

    assert "写法 <div> 是标签" in cleaned


# ============================================================
# 2. 标题结构
# ============================================================

def test_bilingual_headings_merged():
    """相邻同级标题应合并，避免英文标题成为后续章节的父级。"""
    cleaned, stats = get_cleaned()

    assert "# 财务报销管理制度 / Financial Reimbursement Management Policy" in cleaned
    assert stats.hits.get("相邻标题合并") == 1


def test_chapter_heading_levels_normalized():
    """章 → H2，条 → H4，使 heading_path 能表达从属关系。"""
    cleaned, _ = get_cleaned()

    assert "\n## 第一章 总则" in cleaned
    assert "\n#### 第三条 【基本原则】" in cleaned
    assert "\n#### 第五条 【员工职责】" in cleaned
    # 章与条不再被误合并成一行。
    assert "第二章 职责分工 / 第五条" not in cleaned


def test_long_article_line_not_promoted_to_heading():
    """超过长度门槛的条级文本保持原样，不升级为标题。"""
    cleaner = DocumentCleaner()
    raw = "## 第一条 【目的】为规范公司费用报销行为，明确报销范围、标准与审批流程，保障资金安全。"
    cleaned, _ = cleaner.clean(raw, is_markdown=True)

    assert cleaned.startswith("## ")


# ============================================================
# 3. 版式噪声
# ============================================================

def test_toc_removed():
    """点线目录块与「目录」标题应整块删除。"""
    cleaned, stats = get_cleaned()

    assert "目 录" not in cleaned
    assert ". . . ." not in cleaned
    assert "第二章 职责分工 ." not in cleaned
    assert stats.hits.get("目录块", 0) >= 9


def test_repeated_header_footer_removed():
    """重复出现 ≥3 次的页眉页脚行应删除。"""
    cleaner = DocumentCleaner()
    raw = "\n".join(
        ["# 制度"]
        + [f"某某科技有限公司 内部资料\n正文{index}" for index in range(4)]
    )
    cleaned, stats = cleaner.clean(raw, is_markdown=True)

    assert "某某科技有限公司 内部资料" not in cleaned
    assert stats.hits.get("页眉页脚重复行") == 4


def test_page_numbers_removed_only_when_repeated():
    """页码行仅在全篇命中阈值时才删除，正文里的孤立数字保留。"""
    cleaner = DocumentCleaner()

    noisy = "# 制度\n第 1 页 共 3 页\n正文A\n第 2 页 共 3 页\n正文B\n第 3 页 共 3 页\n正文C"
    cleaned, stats = cleaner.clean(noisy, is_markdown=True)
    assert stats.hits.get("页码行") == 3
    assert "正文A" in cleaned and "第 1 页" not in cleaned

    single = "# 制度\n2026 年预算为 3\n正文"
    cleaned_single, stats_single = cleaner.clean(single, is_markdown=True)
    assert "2026 年预算为 3" in cleaned_single
    assert not stats_single.hits.get("页码行")


def test_image_and_separator_lines_removed():
    """纯图片行、装饰分隔线、纯标点行删除，alt 有文字则降级保留。"""
    cleaner = DocumentCleaner()
    raw = "# 制度\n![](images/a.jpg)\n----\n。。。。\n![组织架构图](images/b.jpg)\n正文"
    cleaned, stats = cleaner.clean(raw, is_markdown=True)

    assert "images/a.jpg" not in cleaned
    assert "[图: 组织架构图]" in cleaned
    assert "----" not in cleaned
    assert "。。。。" not in cleaned
    assert stats.hits.get("图片/装饰行") == 3


# ============================================================
# 4. 空白与行号
# ============================================================

def test_whitespace_normalized():
    """连续空行压缩为一个，标题前后保留空行，行尾空白清除。"""
    cleaner = DocumentCleaner()
    raw = "正文一   \n\n\n\n## 小节\n正文二"
    cleaned, _ = cleaner.clean(raw, is_markdown=True)

    assert "\n\n\n" not in cleaned
    assert "   \n" not in cleaned
    assert "## 小节\n\n正文二" in cleaned


def test_line_count_mostly_preserved():
    """结构性删除用空行占位，行号不整体漂移。"""
    text = _sample_text()
    cleaned, _ = get_cleaned(text)

    # 表格转换会增行（1 行 HTML → N 行管道表），其余删除只置空行，
    # 因此清洗后行数应大于等于原行数。
    assert len(cleaned.splitlines()) >= len(text.splitlines()) - 2


def test_idempotent():
    """清洗幂等：clean(clean(x)) == clean(x)。"""
    cleaner = DocumentCleaner()
    once, _ = cleaner.clean(_sample_text(), is_markdown=True)
    twice, stats = cleaner.clean(once, is_markdown=True)

    assert once == twice, "清洗结果不幂等"
    assert not stats.hits, f"二次清洗仍有命中：{stats.hits}"


# ============================================================
# 5. 内容保护
# ============================================================

def test_business_facts_preserved():
    """金额、条款号、文件编号、期限零丢失。"""
    cleaned, _ = get_cleaned()

    for fact in [
        "AFP-FI-2026-002",
        "第二十九条",
        "第三十五条",
        "2026 年 12 月 1 日",
        "5,000 元至 20,000 元",
        "扣回比例不超过当月应发工资的 20%",
        "2026-12-01",
    ]:
        assert fact in cleaned, f"关键信息丢失：{fact}"


def test_rollback_on_over_clean():
    """结构清洗删除超过 60% 时回滚，保证不把文档清空。"""
    cleaner = DocumentCleaner()

    # 造一个「看起来全是目录」的极端文档。
    fake_toc = "\n".join(
        f"第{index}章 章节名字 . . . . . . {index}" for index in range(1, 30)
    )
    cleaned, stats = cleaner.clean(fake_toc, is_markdown=True)

    assert cleaned.strip(), "文档被清空"
    assert stats.rollback is True


# ============================================================
# 6. 纯文本模式
# ============================================================

def test_plain_text_mode_skips_html_and_structure():
    """txt 模式只做字符与空白归一，不做 HTML/目录/标题处理。"""
    cleaner = DocumentCleaner()
    raw = "1\n2\n3\n\n\n<table><tr><td>a</td></tr></table>"
    cleaned, stats = cleaner.clean(raw, is_markdown=False)

    assert "<table>" in cleaned, "txt 模式不应做 HTML 转换"
    assert cleaned.count("1") >= 1, "txt 模式的孤立数字不应被当页码删除"
    assert "\n\n\n" not in cleaned


# ============================================================
# 冗余强调清理（** 噪声星号）
# ============================================================

def test_bold_in_headings_stripped():
    """标题行里的 ** 是引擎格式残留，应去掉。"""
    text = "## **第一章 总则**\n\n正文内容。"
    cleaned, _ = get_cleaned(text)
    assert "**" not in cleaned
    assert "# 第一章 总则" in cleaned


def test_bold_in_table_rows_stripped():
    """表头加粗是引擎固定行为，管道表整行去壳。"""
    text = "| **费用类别** | **说明** |\n| --- | --- |\n| 差旅费 | 出差产生的费用 |"
    cleaned, _ = get_cleaned(text)
    assert "**" not in cleaned
    assert "| 费用类别 | 说明 |" in cleaned
    # 数据行不受影响
    assert "| 差旅费 | 出差产生的费用 |" in cleaned


def test_whole_line_bold_article_promoted():
    """整行加粗的条标题去壳并提升为 H4，heading_path 才能接住。"""
    text = "## 第一章 总则\n\n**第四条 工时制度**\n\n公司实行标准工时制度。"
    cleaned, _ = get_cleaned(text)
    assert "**" not in cleaned
    assert "#### 第四条 工时制度" in cleaned


def test_whole_line_bold_chapter_promoted():
    text = "**第一章 总则**\n\n正文。"
    cleaned, _ = get_cleaned(text)
    assert "## 第一章 总则" in cleaned


def test_whole_line_bold_plain_stripped():
    """非章节条的整行加粗只去壳，保留尾随标点。"""
    text = "**重要提示**：\n\n正文内容。"
    cleaned, _ = get_cleaned(text)
    assert "**" not in cleaned
    assert "重要提示：" in cleaned


def test_inline_emphasis_preserved():
    """句中部分加粗是真实强调语义，必须原样保留。"""
    text = "员工**必须**当日提交申请，逾期不予受理。"
    cleaned, _ = get_cleaned(text)
    assert "员工**必须**当日提交申请" in cleaned


def test_bold_cleanup_counts_in_stats():
    text = "## **第一章 总则**\n\n| **类别** | **说明** |\n| --- | --- |\n| a | b |\n\n**第五条 考勤方式**\n\n正文。"
    _, stats = get_cleaned(text)
    assert stats.hits.get("冗余强调清理", 0) >= 3


def test_empty_input():
    """空输入返回空字符串，不抛异常。"""
    cleaner = DocumentCleaner()

    cleaned, stats = cleaner.clean("", is_markdown=True)
    assert cleaned == ""
    assert stats.original_chars == 0


# ============================================================
# 本地执行
# ============================================================

if __name__ == "__main__":
    import traceback

    cases = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]

    passed = 0
    failed = 0

    for name, case in cases:
        try:
            case()
            passed += 1
            print(f"[PASS] {name}")
        except Exception:
            failed += 1
            print(f"[FAIL] {name}")
            traceback.print_exc()

    print(f"\n合计 {len(cases)} 项：通过 {passed}，失败 {failed}")

    cleaned_text, clean_stats = get_cleaned()
    print("\n===== 清洗摘要 =====")
    print(clean_stats.summary())
    print("\n===== 清洗结果（前 1200 字）=====")
    print(cleaned_text[:1200])
