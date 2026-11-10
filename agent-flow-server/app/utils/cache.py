import asyncio
from functools import lru_cache
from pathlib import Path

import aiofiles

from app.utils.logger import logger
from app.core.config import settings


class LocalDocumentCache:
    def __init__(self):
        # 从 settings 读取缓存目录，如果没有配置，默认在项目根目录建一个 uploads_cache
        # 建议在 .env 里配：LOCAL_CACHE_DIR=uploads_cache
        cache_dir_name = getattr(settings, "LOCAL_CACHE_DIR", "temp/uploads")

        # 获取项目根目录（假设当前文件在 core/ 目录下，往上一级就是根目录）
        # 如果你有配置 BASE_DIR，直接用 settings.BASE_DIR
        self.base_dir = Path(__file__).resolve().parent.parent.parent / cache_dir_name
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, document_uid: str, filename: str) -> Path:
        """根据文档ID和原始文件名，生成缓存路径"""
        suffix = Path(filename).suffix
        return self.base_dir / f"{document_uid}{suffix}"

    async def write(self, document_uid: str, filename: str, content: bytes) -> Path:
        """异步写入缓存"""
        file_path = self.get_cache_path(document_uid, filename)

        def _sync_write():
            with open(file_path, "wb") as f:
                f.write(content)

        await asyncio.to_thread(_sync_write)
        logger.debug(f"文档 {document_uid} 已缓存至本地: {file_path}")
        return file_path

    async def read(self, document_uid: str, filename: str) -> bytes | None:
        """异步读取缓存，如果不存在返回 None"""
        file_path = self.get_cache_path(document_uid, filename)
        if not file_path.exists():
            return None

        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def remove(self, document_uid: str, filename: str):
        """异步删除缓存"""
        file_path = self.get_cache_path(document_uid, filename)
        if not file_path.exists():
            return

        def _sync_remove():
            try:
                file_path.unlink()
                logger.debug(f"文档 {document_uid} 本地缓存已清理: {file_path}")
            except Exception as e:
                logger.warning(f"清理缓存失败 {file_path}: {e}")

        await asyncio.to_thread(_sync_remove)

@lru_cache(maxsize=1)
def get_document_cache() -> LocalDocumentCache:
    return LocalDocumentCache()