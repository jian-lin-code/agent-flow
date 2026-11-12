"""Markdown（制度稿）→ 排版 HTML（doc-typeset 版式：A4 / 宋体小四 / 黑体标题 / 全框线表格 / 页脚页码）。"""

import html
import re
import sys

SRC = r"C:\Users\xiaojianlin\Desktop\agent-flow\output\2332d8cd-0fb8-4c26-a358-871c92c93781\stage1\final_draft.md"
OUT = r"C:\Users\xiaojianlin\Desktop\agent-flow\output\2332d8cd-0fb8-4c26-a358-871c92c93781\stage2\formatted-考勤与请销假管理制度.html"

CSS = """
  /* 页面规则：A4 纵向，页脚居中页码（GB/T 9704 惯例 — 1 — 形式） */
  @page {
    @bottom-center { content: "— " counter(page) " —"; }
  }

  :root {
    --ff-body: "SimSun", 宋体, serif;
    --ff-heading: "SimHei", 黑体, sans-serif;
    --fs-title: 22pt;
    --fs-h2: 15pt;
    --fs-h3: 12pt;
    --fs-body: 12pt;
    --fs-table: 10.5pt;
    --lh-body: 1.7;
    --color-text: #000000;
    --color-th-bg: #f2f2f2;
    --color-border: #000000;
    --spacing-chapter: 16pt;
    --spacing-chapter-after: 8pt;
    --spacing-article: 9pt;
    --spacing-paragraph: 4pt;
    --spacing-title-after: 22pt;
    --spacing-table-top: 6pt;
    --spacing-table-bottom: 12pt;
    --spacing-cell-y: 4pt;
    --spacing-cell-x: 6pt;
    --page-content-width: 15.6cm;
  }

  * { box-sizing: border-box; }

  body {
    font-family: var(--ff-body);
    font-size: var(--fs-body);
    line-height: var(--lh-body);
    color: var(--color-text);
    max-width: var(--page-content-width);
    margin: 0 auto;
    padding: 0;
  }

  h1.doc-title {
    font-family: var(--ff-heading);
    font-size: var(--fs-title);
    font-weight: bold;
    text-align: center;
    text-indent: 0;
    line-height: 1.5;
    margin: 0 0 var(--spacing-title-after) 0;
  }

  h2.chapter {
    font-family: var(--ff-heading);
    font-size: var(--fs-h2);
    font-weight: bold;
    text-align: center;
    text-indent: 0;
    margin: var(--spacing-chapter) 0 var(--spacing-chapter-after) 0;
    page-break-after: avoid;
  }

  /* 条标题：制度类文档的条不做 Heading 层级，用加粗段落承载（避免 h2→h3 层级跳读） */
  p.article {
    font-family: var(--ff-heading);
    font-size: var(--fs-h3);
    font-weight: bold;
    text-align: left;
    text-indent: 0;
    margin: var(--spacing-article) 0 var(--spacing-paragraph) 0;
    page-break-after: avoid;
  }

  p {
    text-indent: 2em;
    text-align: justify;
    margin: 0 0 var(--spacing-paragraph) 0;
  }

  p.flat { text-indent: 0; }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--fs-table);
    margin: var(--spacing-table-top) 0 var(--spacing-table-bottom) 0;
  }

  th, td {
    border: 1px solid var(--color-border);
    padding: var(--spacing-cell-y) var(--spacing-cell-x);
    text-align: left;
    vertical-align: middle;
    text-indent: 0;
    line-height: 1.5;
  }

  th {
    background: var(--color-th-bg);
    font-family: var(--ff-heading);
    font-weight: bold;
    text-align: center;
  }
"""


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return text


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        line = raw.strip()

        if not line:
            i += 1
            continue

        # 文档标题
        if line.startswith("# "):
            out.append(f'  <h1 class="doc-title">{inline(line[2:].strip())}</h1>')
            i += 1
            continue

        # 章标题
        if line.startswith("## "):
            out.append(f'  <h2 class="chapter">{inline(line[3:].strip())}</h2>')
            i += 1
            continue

        # 条标题：整行加粗且以「第X条」开头
        m = re.fullmatch(r"\*\*(第[一二三四五六七八九十百]+条[^*]*)\*\*", line)
        if m:
            out.append(
                f'  <p class="article">{inline(m.group(1).strip())}</p>'
            )
            i += 1
            continue

        # 表格：当前行以 | 开头，且下一行是分隔行
        if line.startswith("|") and i + 1 < n and re.fullmatch(
            r"\|[\s:\-|]+\|", lines[i + 1].strip()
        ):
            header = split_row(line)
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            ths = "".join(f"<th>{inline(c)}</th>" for c in header)
            trs = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                for r in rows
            )
            out.append(
                "  <table>\n    <thead><tr>" + ths + "</tr></thead>\n    <tbody>"
                + trs + "</tbody>\n  </table>"
            )
            continue

        out.append(f"  <p>{inline(line)}</p>")
        i += 1

    return "\n".join(out)


def main() -> int:
    with open(SRC, encoding="utf-8") as f:
        md = f.read()

    body = convert(md)

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="docx-page-size" content="A4">
  <title>考勤与请销假管理制度</title>
  <style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)

    print(f"written: {OUT}")
    print(f"长度: {len(doc)} 字符 | 表格: {doc.count('<table>')} | 章: {doc.count('class=\"chapter\"')} | 条: {doc.count('class=\"article\"')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
