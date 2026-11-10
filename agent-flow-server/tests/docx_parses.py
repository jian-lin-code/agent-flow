
import asyncio
import hashlib
import io
import re
from functools import lru_cache

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.events.document_progress import emit
from app.utils.minio_client import get_minio_storage
from app.utils.image_processor import get_image_processor
from app.utils.logger import logger


class DocxToMarkdownConverter:
    """DOCX 转 Markdown，尽可能保留标题、列表、代码、表格、链接和图片。"""

    def __init__(self):
        self.minio_client = get_minio_storage()
        self.image_processor = get_image_processor()
        self.enable_image_processing = False

    async def convert(
        self,
        docx_bytes: bytes,
        doc_title: str,
        kb_uid: str,
        document_uid: str,
        ctx: dict,
    ) -> str:
        if not docx_bytes:
            raise ValueError("DOCX 文件内容为空")

        ctx["document_uid"] = document_uid
        ctx["kb_uid"] = kb_uid

        await emit(
            f"【DOCX】：开始解析 Word 文档 {doc_title}",
            ctx=ctx,
        )

        try:
            doc = Document(io.BytesIO(docx_bytes))
            blocks = list(self._iter_block_items(doc))

            # 文件名 -> (图片字节, MIME 类型)
            image_bytes_by_name: dict[str, tuple[bytes, str]] = {}
            image_summary_map: dict[str, str] = {}
            image_info: dict[str, tuple[str, str]] = {}
            md_blocks: list[str] = []

            await emit(
                f"【DOCX】：开始处理，共发现 {len(blocks)} 个正文块",
                ctx=ctx,
            )

            index = 0

            while index < len(blocks):
                block = blocks[index]

                if isinstance(block, Table):
                    table_md = self._render_table(block)
                    if table_md:
                        md_blocks.append(table_md)
                    index += 1
                    continue

                if not isinstance(block, Paragraph):
                    index += 1
                    continue

                # 连续代码段落合并，避免每行代码都产生单独围栏。
                if self._is_code_paragraph(block):
                    code_paragraphs = []

                    while index < len(blocks):
                        current = blocks[index]

                        if not isinstance(current, Paragraph):
                            break

                        if not self._is_code_paragraph(current):
                            break

                        code_paragraphs.append(current)
                        index += 1

                    code_lines = []

                    for paragraph in code_paragraphs:
                        code_text = self._paragraph_text_with_hyperlinks(
                            paragraph
                        )
                        code_lines.append(code_text.rstrip())

                        # 代码段落中的图片也不能丢弃。
                        self._extract_paragraph_images(
                            paragraph,
                            doc,
                            image_bytes_by_name,
                        )

                    code = "\n".join(code_lines).strip("\n")

                    if code:
                        md_blocks.append(self._render_code_block(code))

                    continue

                rendered = self._render_paragraph(
                    block=block,
                    doc=doc,
                    image_bytes_by_name=image_bytes_by_name,
                )

                if rendered:
                    md_blocks.extend(rendered)

                index += 1

            images_to_upload = [
                (name, image_bytes, content_type)
                for name, (image_bytes, content_type)
                in image_bytes_by_name.items()
            ]

            await emit(
                f"【DOCX】：扫描完成，提取到 {len(blocks)} 个正文块，"
                f"{len(images_to_upload)} 张不同图片",
                ctx=ctx,
            )

            if images_to_upload and self.enable_image_processing:
                image_info = await self._process_images(
                    doc=doc,
                    images_to_upload=images_to_upload,
                    image_summary_map=image_summary_map,
                    doc_title=doc_title,
                    ctx=ctx,
                )

                md_blocks = self._replace_image_placeholders(
                    md_blocks,
                    image_info,
                )
            else:
                # 关闭图片处理时，保留可识别的图片占位符，
                # 不生成虚假的图片 URL。
                md_blocks = self._replace_image_placeholders(
                    md_blocks,
                    {},
                )

            markdown = self._normalize_markdown(md_blocks)

            if not markdown.strip():
                raise ValueError(
                    "DOCX 解析结果为空，请检查文档是否包含可提取的正文"
                )

            await emit(
                "【DOCX】：Markdown 转换完成，准备进入切分阶段",
                ctx=ctx,
            )

            return markdown

        except Exception as exc:
            logger.exception(
                "DOCX 转 Markdown 失败，document_id=%s",
                document_id,
            )
            await emit(
                f"【DOCX】：解析失败：{str(exc)[:200]}",
                ctx=ctx,
            )
            raise

    # =========================================================
    # 一、遍历正文块
    # =========================================================

    @staticmethod
    def _iter_block_items(parent):
        """按照 Word 中的实际顺序遍历段落和表格。"""
        if isinstance(parent, DocumentObject):
            parent_element = parent.element.body
        else:
            parent_element = parent._tc

        for child in parent_element.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                yield Table(child, parent)

    # =========================================================
    # 二、段落渲染
    # =========================================================

    def _render_paragraph(
        self,
        block: Paragraph,
        doc,
        image_bytes_by_name: dict[str, tuple[bytes, str]],
    ) -> list[str]:
        output: list[str] = []

        image_names = self._extract_paragraph_images(
            block,
            doc,
            image_bytes_by_name,
        )

        for image_name in image_names:
            output.append(f"<!-- DOCX_IMAGE:{image_name} -->")

        text = self._paragraph_text_with_hyperlinks(block).strip()

        if not text:
            return output

        style_name = (
            block.style.name
            if block.style is not None
            else "Normal"
        )

        # 标题样式优先。
        heading_level = self._get_heading_level(style_name)

        if heading_level:
            output.append(f"{'#' * heading_level} {text}")
            return output

        if style_name.strip().lower() == "title":
            output.append(f"# {text}")
            return output

        numbered_heading = self._render_numbered_heading(text)

        if numbered_heading:
            output.append(numbered_heading)
            return output

        list_marker = self._get_list_marker(block)

        if list_marker:
            indent, marker = list_marker
            output.append(f"{'  ' * indent}{marker} {text}")
            return output

        output.append(text)
        return output

    @staticmethod
    def _get_heading_level(style_name: str) -> int | None:
        match = re.fullmatch(
            r"(?:Heading|标题)\s*([1-6])",
            style_name.strip(),
            re.IGNORECASE,
        )
        return int(match.group(1)) if match else None

    @staticmethod
    def _render_numbered_heading(text: str) -> str | None:
        # 章节标题，如“第一章 总则”“第十二节 报销标准”
        if re.match(
            r"^第[一二三四五六七八九十百千万零〇0-9]+[章节篇部]\s*",
            text,
        ):
            return f"# {text}"

        # 支持 2.1 标题、2.1标题、2.1.3 标题。
        if re.match(r"^\d+\.\d+\.\d+(?:\s+|\s*)(?=\S)", text):
            return f"### {text}"

        if re.match(r"^\d+\.\d+(?:\s+|\s*)(?=\S)", text):
            return f"## {text}"

        return None

    # =========================================================
    # 三、代码识别和代码块渲染
    # =========================================================

    @staticmethod
    def _is_code_style(style_name: str) -> bool:
        name = style_name.strip().lower()

        return (
            name in {
                "code",
                "source code",
                "代码",
                "代码块",
                "代码文本",
            }
            or "code block" in name
            or "代码块" in name
        )

    def _is_code_paragraph(self, paragraph: Paragraph) -> bool:
        """
        先使用明确的代码样式，再使用保守的代码特征识别。
        启发式识别不能替代 Word 中正确设置代码样式。
        """
        style_name = (
            paragraph.style.name
            if paragraph.style is not None
            else "Normal"
        )

        if self._is_code_style(style_name):
            return True

        text = paragraph.text.strip()

        if not text:
            return False

        # 强代码特征：函数/类声明、导入语句、装饰器等。
        strong_patterns = (
            r"^(async\s+)?def\s+\w+\s*\(",
            r"^class\s+\w+[\s(:]",
            r"^(from\s+\S+\s+import|import\s+\S+)",
            r"^@\w+",
            r"^(return|raise|yield)\b",
            r"^(if|elif|else|for|while|try|except|finally|with)\b.*:",
        )

        if any(re.search(pattern, text) for pattern in strong_patterns):
            return True

        # 代码表达式特征需要同时满足多个条件，避免误判普通中文正文。
        code_symbols = sum(
            text.count(symbol)
            for symbol in ("(", ")", "{", "}", "==", "=>", "->", "&&", "||")
        )

        has_assignment = bool(
            re.search(r"(?<![=!<>])=(?!=)", text)
        )
        has_semicolon = ";" in text
        has_function_call = bool(
            re.search(r"\b[A-Za-z_]\w*\s*\([^)]*\)", text)
        )

        return (
            code_symbols >= 3
            and (has_assignment or has_semicolon or has_function_call)
        )

    @staticmethod
    def _render_code_block(text: str) -> str:
        """选择不会与代码内容冲突的 Markdown 围栏。"""
        longest = max(
            (
                len(match.group(0))
                for match in re.finditer(r"`+", text)
            ),
            default=0,
        )

        fence = "`" * max(3, longest + 1)
        return f"{fence}\n{text}\n{fence}"

    # =========================================================
    # 四、超链接、换行和制表符
    # =========================================================

    @staticmethod
    def _paragraph_text_with_hyperlinks(
        paragraph: Paragraph,
    ) -> str:
        """
        按 XML 子节点顺序读取文字。
        保留外部超链接、手动换行和制表符。
        """
        parts: list[str] = []

        def read_run(run_element) -> str:
            values: list[str] = []

            for node in run_element.iter():
                if node.tag == qn("w:t"):
                    values.append(node.text or "")
                elif node.tag == qn("w:tab"):
                    values.append("\t")
                elif node.tag in {qn("w:br"), qn("w:cr")}:
                    values.append("\n")

            return "".join(values)

        for child in paragraph._p.iterchildren():
            if child.tag == qn("w:r"):
                parts.append(read_run(child))

            elif child.tag == qn("w:hyperlink"):
                link_text = "".join(
                    read_run(run)
                    for run in child.iterchildren()
                    if run.tag == qn("w:r")
                )

                rel_id = child.get(qn("r:id"))
                url = None

                if rel_id:
                    relationship = paragraph.part.rels.get(rel_id)
                    if relationship is not None:
                        url = relationship.target_ref

                if link_text and url:
                    safe_text = (
                        link_text.replace("\\", "\\\\")
                        .replace("[", r"\[")
                        .replace("]", r"\]")
                    )
                    safe_url = url.replace("\\", "%5C").replace(")", "%29")
                    parts.append(f"[{safe_text}]({safe_url})")
                else:
                    parts.append(link_text)

        return "".join(parts)

    # =========================================================
    # 五、Word 列表
    # =========================================================

    @staticmethod
    def _get_list_marker(
        paragraph: Paragraph,
    ) -> tuple[int, str] | None:
        """
        解析显式编号属性，并兼容常见列表样式。
        返回 (缩进级别, Markdown 列表标记)。
        """
        style_name = (
            paragraph.style.name.lower()
            if paragraph.style is not None
            else ""
        )

        # 常见列表样式回退。
        if (
            "list bullet" in style_name
            or "项目符号" in style_name
            or "无序列表" in style_name
        ):
            return 0, "-"

        if (
            "list number" in style_name
            or "编号列表" in style_name
            or "有序列表" in style_name
        ):
            return 0, "1."

        p_pr = paragraph._p.pPr

        if p_pr is None or p_pr.numPr is None:
            # 样式链可能继承列表定义，继续查找父样式。
            style = paragraph.style

            while style is not None and style.base_style is not None:
                style = style.base_style
                name = style.name.lower()

                if "list bullet" in name or "项目符号" in name:
                    return 0, "-"

                if "list number" in name or "编号列表" in name:
                    return 0, "1."

            return None

        num_pr = p_pr.numPr
        num_id_node = num_pr.numId
        ilvl_node = num_pr.ilvl

        if num_id_node is None or num_id_node.val is None:
            return None

        num_id = int(num_id_node.val)
        level = (
            int(ilvl_node.val)
            if ilvl_node is not None and ilvl_node.val is not None
            else 0
        )

        try:
            numbering = paragraph.part.numbering_part.element
        except Exception:
            return None

        abstract_num_id = None

        for num in numbering.findall(qn("w:num")):
            if int(num.get(qn("w:numId"), "-1")) == num_id:
                abstract = num.find(qn("w:abstractNumId"))

                if abstract is not None:
                    abstract_num_id = int(abstract.get(qn("w:val")))

                # 某个具体编号可能覆盖抽象编号的列表格式。
                break

        if abstract_num_id is None:
            return None

        for abstract in numbering.findall(qn("w:abstractNum")):
            if int(
                abstract.get(qn("w:abstractNumId"), "-1")
            ) != abstract_num_id:
                continue

            for lvl in abstract.findall(qn("w:lvl")):
                lvl_value = lvl.find(qn("w:ilvl"))

                if lvl_value is None:
                    continue

                if int(lvl_value.get(qn("w:val"), "0")) != level:
                    continue

                fmt_node = lvl.find(qn("w:numFmt"))

                if fmt_node is None:
                    continue

                fmt = fmt_node.get(qn("w:val"), "bullet")

                if fmt == "bullet":
                    return level, "-"

                return level, "1."

        return None

    # =========================================================
    # 六、表格
    # =========================================================

    def _render_table(self, table: Table) -> list[str]:
        rows: list[list[str]] = []

        for row in table.rows:
            cells = [
                self._escape_table_cell(cell.text)
                for cell in row.cells
            ]
            rows.append(cells)

        if not rows:
            return []

        max_columns = max(len(row) for row in rows)

        if max_columns == 0:
            return []

        normalized_rows = [
            row + [""] * (max_columns - len(row))
            for row in rows
        ]

        header = normalized_rows[0]

        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * max_columns) + " |",
        ]

        for row in normalized_rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return ["\n".join(lines)]

    @staticmethod
    def _escape_table_cell(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("|", r"\|")
        text = text.replace("\n", "<br>")
        return text.strip()

    # =========================================================
    # 七、图片提取和上下文
    # =========================================================

    def _extract_paragraph_images(
        self,
        paragraph: Paragraph,
        doc,
        image_bytes_by_name: dict[str, tuple[bytes, str]],
    ) -> list[str]:
        names: list[str] = []

        for shape in paragraph._p.xpath(".//pic:pic"):
            try:
                embed_ids = shape.xpath(".//a:blip/@r:embed")

                if not embed_ids:
                    continue

                image_part = doc.part.related_parts[embed_ids[0]]
                image_bytes = image_part.blob
                content_type = image_part.content_type

                extension = content_type.split("/")[-1].lower()

                if extension == "jpeg":
                    extension = "jpg"
                elif extension == "svg+xml":
                    extension = "svg"

                digest = hashlib.sha256(image_bytes).hexdigest()
                filename = f"{digest}.{extension}"

                image_bytes_by_name.setdefault(
                    filename,
                    (image_bytes, content_type),
                )

                # 同一图片在正文中重复出现时，保留每次引用。
                names.append(filename)

            except Exception:
                logger.exception("DOCX 图片提取失败")

        return names

    def _extract_image_contexts(
        self,
        doc,
        context_len: int = 100,
    ) -> dict[str, tuple[str, str]]:
        """
        保留原有接口。
        以最近的非空前后文作为图片摘要上下文。
        """
        context_map: dict[str, tuple[str, str]] = {}
        paragraphs = list(doc.paragraphs)
        texts = [p.text.strip() for p in paragraphs]

        for index, paragraph in enumerate(paragraphs):
            shapes = paragraph._p.xpath(".//pic:pic")

            if not shapes:
                continue

            previous_text = ""
            next_text = ""

            for j in range(index - 1, -1, -1):
                if texts[j]:
                    previous_text = texts[j][-context_len:]
                    break

            for j in range(index + 1, len(texts)):
                if texts[j]:
                    next_text = texts[j][:context_len]
                    break

            for shape in shapes:
                try:
                    embed_ids = shape.xpath(".//a:blip/@r:embed")
                    if not embed_ids:
                        continue

                    image_part = doc.part.related_parts[embed_ids[0]]
                    digest = hashlib.sha256(image_part.blob).hexdigest()

                    extension = (
                        image_part.content_type.split("/")[-1].lower()
                    )
                    if extension == "jpeg":
                        extension = "jpg"

                    filename = f"{digest}.{extension}"
                    context_map[filename] = (
                        previous_text,
                        next_text,
                    )

                except Exception:
                    logger.exception("提取图片上下文失败")

        return context_map

    # =========================================================
    # 八、图片摘要与 MinIO
    # =========================================================

    async def _process_images(
        self,
        doc,
        images_to_upload,
        image_summary_map,
        doc_title,
        ctx,
    ) -> dict[str, tuple[str, str]]:
        image_context_map = self._extract_image_contexts(doc)
        total_images = len(images_to_upload)

        await emit(
            f"【多模态】：开始为 {total_images} 张图片生成摘要...",
            ctx=ctx,
        )

        for index, (filename, image_bytes, content_type) in enumerate(
            images_to_upload,
            start=1,
        ):
            try:
                await self.image_processor.apply_rate_limit(
                    max_requests=10,
                    ctx=ctx,
                )

                context = image_context_map.get(filename, ("", ""))

                summary = await self.image_processor.generate_image_summary(
                    image_data=image_bytes,
                    img_format=content_type,
                    doc_stem=doc_title,
                    image_content=context,
                )

                image_summary_map[filename] = summary or "图片"

                await emit(
                    f"【图片摘要】：[{index}/{total_images}] 完成",
                    ctx=ctx,
                )

            except Exception:
                logger.exception("图片摘要生成失败：%s", filename)
                image_summary_map[filename] = "图片摘要生成失败"

        await emit(
            "【DOCX】：开始上传至 MinIO...",
            ctx=ctx,
        )

        image_url_map = await self.minio_client.upload_docx_images_batch(
            target_images=images_to_upload,
            ctx=ctx,
        )

        image_info = self.image_processor.merge_summary_and_url(
            image_summary_map,
            image_url_map,
        )

        await emit(
            "【DOCX】：图片上传合并完成",
            ctx=ctx,
        )

        return image_info


    @staticmethod
    def _replace_image_placeholders(
            md_blocks: list[str],
            image_info: dict[str, tuple[str, str]],
    ) -> list[str]:
        """替换图片占位符，并兼容意外出现的嵌套列表。"""

        result: list[str] = []

        def flatten(items):
            for item in items:
                if isinstance(item, (list, tuple)):
                    yield from flatten(item)
                elif item is not None:
                    yield str(item)

        for block in flatten(md_blocks):
            match = re.fullmatch(
                r"<!-- DOCX_IMAGE:(.+?) -->",
                block.strip(),
            )

            if not match:
                result.append(block)
                continue

            filename = match.group(1)
            summary, url = image_info.get(
                filename,
                ("图片摘要尚未生成", ""),
            )

            if not url:
                result.append(f"[图片：{summary}]")
                continue

            safe_summary = (
                str(summary)
                .replace("\n", " ")
                .replace("[", r"\[")
                .replace("]", r"\]")
            )
            safe_url = str(url).replace(")", "%29")

            result.append(f"![{safe_summary}]({safe_url})")

        return result

    # =========================================================
    # 九、Markdown 规范化
    # =========================================================

    @staticmethod
    def _normalize_markdown(blocks: list[str]) -> str:
        """
        以 Markdown 块为单位拼接。
        不对代码块内部执行全局空白压缩。
        """
        output = []

        for block in blocks:
            if block is None:
                continue

            text = str(block).strip("\r\n")

            if not text.strip():
                continue

            output.append(text)

        markdown = "\n\n".join(output).strip()
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

        return markdown + "\n" if markdown else ""


@lru_cache(maxsize=1)
def get_docx_converter() -> DocxToMarkdownConverter:
    return DocxToMarkdownConverter()


async def test():
    docx_converter = get_docx_converter()

    file_path = (
        r"C:\Users\xiaojianlin\Desktop\agent-flow"
        r"\agent-flow-server\tests\docs\测试docx转md.docx"
    )

    try:
        with open(file_path, "rb") as f:
            docx_bytes = f.read()
    except FileNotFoundError:
        logger.error("文件不存在，请检查路径: %s", file_path)
        return

    content = await docx_converter.convert(
        docx_bytes=docx_bytes,
        doc_title="测试文档切分.docx",
        kb_uid="test-kb-uid",
        document_uid="test-doc-uid",
        ctx={},
    )

    output_path = "test_output.md"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Markdown 结果已保存至: %s", output_path)


if __name__ == "__main__":
    asyncio.run(test())
