"""为历史图片附件补生成缩略图（一次性脚本，可重复执行）。

背景：报销单列表页只显示 36px 缩略图，此前直接用原图，单页 10 条记录会产生
30MB 级别的图片下载，挤占带宽并拖慢同期的接口请求。新上传的附件会在上传时
自动生成缩略图，本脚本用于补齐存量数据。

用法：
    cd agent-flow-server && PYTHONPATH=. uv run python scripts/backfill_expense_thumbnails.py
"""

import asyncio

from sqlalchemy import select

from app.core import database as db
from app.models.expense_claim import Attachment
from app.utils.logger import logger
from app.utils.minio_client import get_expense_minio_storage, thumb_object_name


async def _exists(storage, object_name: str) -> bool:
    def check() -> bool:
        try:
            storage.client.stat_object(storage.bucket, object_name)
            return True
        except Exception:
            return False

    return await asyncio.to_thread(check)


async def main() -> None:
    db.init_db_engine()
    storage = get_expense_minio_storage()
    await storage.init()

    async with db.async_session() as session:  # type: ignore[misc]
        rows = (
            await session.execute(
                select(Attachment).where(Attachment.content_type.like("image/%"))
            )
        ).scalars().all()

    logger.info(f"待检查图片附件 {len(rows)} 个")

    created = skipped = failed = 0
    for att in rows:
        if not att.storage_path:
            continue
        if await _exists(storage, thumb_object_name(att.storage_path)):
            skipped += 1
            continue
        try:
            content = await storage.download(att.storage_path)
            thumb = await storage.upload_image_thumbnail(att.storage_path, content)
            if thumb:
                created += 1
                logger.info(f"已生成缩略图: {att.storage_path} ({att.file_size / 1024:.0f}KB)")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.error(f"处理失败 {att.storage_path}: {e}")

    logger.info(f"完成：新生成 {created}，已存在 {skipped}，失败 {failed}")


if __name__ == "__main__":
    asyncio.run(main())
