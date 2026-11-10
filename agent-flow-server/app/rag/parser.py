from pathlib import Path
from functools import lru_cache
from typing import Dict, Any

from app.core.exceptions import FileProcessingError
from app.events.document_progress import emit
from app.utils.logger import logger
from app.rag.parsers.mineru_engine import get_mineru_service


class DocumentParser:
    def __init__(self):
        self.mineru_service = get_mineru_service()

    @staticmethod
    def _decode_text(file_bytes: bytes) -> str:
        """统一解码 TXT 和 Markdown 文件。"""
        try:
            # 优先使用 UTF-8
            return file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            # 兼容部分 Windows 环境下的中文文本
            try:
                return file_bytes.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise FileProcessingError(
                    "文本文件编码无法识别，请转换为 UTF-8 后重新上传"
                ) from exc

    async def parse(
            self,
            file_bytes: bytes,
            filename: str,
            ctx: Dict,
    ) -> Dict[str, Any]:
        """统一解析入口：将不同格式的文档转换为文本内容。"""
        document_uid = (ctx or {}).get("document_uid", "")
        suffix = Path(filename).suffix.lower()
        doc_stem = Path(filename).stem

        logger.info("[Parser][DOC-%s] 开始解析文档: %s, 类型: %s", document_uid, filename, suffix)

        await emit(
            f"[解析] 接收到文档 {doc_stem}，准备分发解析任务",
            ctx=ctx,
        )

        if suffix in {".txt", ".md"}:
            file_type = "纯文本" if suffix == ".txt" else "Markdown"

            await emit(
                f"[解析] 检测到{file_type}文档，正在提取文字内容",
                ctx=ctx,
            )

            content = self._decode_text(file_bytes)

        elif suffix in {".pdf", ".docx"}:
            file_type = "PDF" if suffix == ".pdf" else "Word"

            await emit(
                f"[解析] 检测到{file_type}文档，移交 MinerU 引擎处理",
                ctx=ctx,
            )

            content = await self.mineru_service.convert_pdf_to_md(
                pdf_bytes=file_bytes,
                filename=filename,
                ctx=ctx,
            )

        else:
            logger.error("[Parser][DOC-%s] 不支持的文档格式: %s", document_uid, suffix)
            await emit(
                f"[解析] 不支持的文档格式 {suffix}，解析中止",
                ctx=ctx,
            )
            raise FileProcessingError(f"不支持的文件格式: {suffix}")

        if not content or not content.strip():
            logger.error("[Parser][DOC-%s] 文档内容为空: %s", document_uid, filename)
            await emit(
                f"[解析] 失败：文档内容为空",
                ctx=ctx,
            )
            raise FileProcessingError(f"文档内容为空: {filename}")

        logger.info("[Parser][DOC-%s] 文档解析成功，提取内容共 %d 个字符", document_uid, len(content))


        return {
            "content": content,
            "source_type": suffix[1:],
            "filename": filename,
            "ctx": ctx
        }


@lru_cache(maxsize=1)
def get_document_parser() -> DocumentParser:
    return DocumentParser()