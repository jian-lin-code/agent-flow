"""为历史 docx 文档补齐解析产物 Markdown（一次性脚本，可重复执行）。

背景：新上传的 docx 在 rag_task 解析完成后会把 MinerU 生成的 md 上传到对象存储，
并把 documents.access_url 指向该 md，前端预览直接按 Markdown 渲染，排版比 mammoth
转 HTML 好得多。本脚本用于补齐改造前已入库的存量 docx（重新解析一次源文件）。

用法：
    cd agent-flow-server && PYTHONPATH=. uv run python scripts/backfill_docx_markdown.py
"""

import asyncio

from sqlalchemy import select

from app.core import database as db
from app.models.knowledge import Document
from app.rag.parser import get_document_parser
from app.utils.logger import logger
from app.utils.minio_client import build_object_url, get_minio_storage, parsed_md_object_name


async def _parse_with_retry(parser, source: bytes, title: str, uid: str, attempts: int = 3) -> str:
    """MinerU 结果 zip 偶尔 503，重试几次再放弃。"""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            result = await parser.parse(file_bytes=source, filename=title, ctx={"document_uid": uid})
            return (result.get("content") or "").strip()
        except Exception as exc:
            last_exc = exc
            logger.warning("解析失败（第 %d/%d 次）%s: %s", i + 1, attempts, title, exc)
            if i + 1 < attempts:
                await asyncio.sleep(5)
    raise last_exc  # type: ignore[misc]


async def main() -> None:
    db.init_db_engine()
    storage = get_minio_storage()
    await storage.init()
    parser = get_document_parser()

    async with db.async_session() as session:  # type: ignore[misc]
        docs = (
            await session.execute(
                select(Document).where(Document.title.ilike("%.docx")).order_by(Document.id)
            )
        ).scalars().all()

        logger.info("待补齐 docx 文档：%d 个", len(docs))
        ok, skipped, failed = 0, 0, 0

        for doc in docs:
            # 先取标量字段：rollback 后 ORM 属性会过期，再访问会触发同步 IO 报错
            uid, title, storage_path = doc.uid, doc.title, doc.storage_path

            # 幂等：access_url 已指向 md 的文档说明补齐过，直接跳过
            if (doc.access_url or "").lower().endswith(".md"):
                logger.info("跳过 %s：access_url 已指向 Markdown", title)
                skipped += 1
                continue

            if not storage_path:
                logger.warning("跳过 %s：缺少 storage_path", title)
                skipped += 1
                continue

            object_name = parsed_md_object_name(uid)
            try:
                source = await storage.download(storage_path)
                if not source:
                    logger.warning("跳过 %s：源文件下载为空", title)
                    skipped += 1
                    continue

                content = await _parse_with_retry(parser, source, title, uid)
                if not content:
                    logger.warning("跳过 %s：解析结果为空", title)
                    skipped += 1
                    continue

                await storage.upload(object_name, content.encode("utf-8"), "text/markdown; charset=utf-8")
                doc.access_url = build_object_url(object_name)
                await session.commit()
                ok += 1
                logger.info("已补齐 %s · md %d 字符 · %s", title, len(content), build_object_url(object_name))
            except Exception as exc:  # 单个失败不影响其它文档
                await session.rollback()
                failed += 1
                logger.error("补齐失败 %s: %s", title, exc)

        print(f"完成：成功 {ok} · 跳过 {skipped} · 失败 {failed}")


if __name__ == "__main__":
    asyncio.run(main())
