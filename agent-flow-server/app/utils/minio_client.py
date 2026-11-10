import asyncio
import json
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from minio import Minio
from minio.deleteobjects import DeleteObject

from app.core.config import settings
from app.events.document_progress import emit
from app.utils.logger import logger

# 图片缩略图：列表页只加载缩略图，避免用原图（发票照片常见 2-5MB/张）当 36px 缩略图
THUMB_DIR = "thumbnails"
THUMB_MAX_SIDE = 360
THUMB_QUALITY = 78


def thumb_object_name(storage_path: str) -> str:
    """缩略图对象名：thumbnails/<原路径>.jpg，保持原目录结构便于随附件一起清理。"""
    return f"{THUMB_DIR}/{storage_path.lstrip('/')}.jpg"


def parsed_md_object_name(document_uid: str) -> str:
    """解析产物 Markdown 的对象名：按文档 uid 固定，重复解析直接覆盖，删除时可直接推导。"""
    return f"knowledge/parsed/{document_uid}.md"


def build_object_url(object_name: str, bucket_name: str | None = None) -> str:
    """对象对外访问直链（Bucket 已配置匿名只读）。"""
    bucket = bucket_name or settings.MINIO_BUCKET_NAME
    return f"http://{settings.MINIO_ENDPOINT}/{bucket}/{object_name.lstrip('/')}"


class MinioStorage:
    def __init__(
            self,
            bucket_name: str | None = None,
            public_read: bool = True,
    ) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )

        # 默认仍使用知识库 Bucket，兼容已有调用
        self.bucket = bucket_name or settings.MINIO_BUCKET_NAME

        self.img_dir = settings.MINIO_IMG_DIR

        # 是否允许匿名读取
        self.public_read = public_read

        self._is_initialized = False
        self._init_lock = asyncio.Lock()

    async def init(self) -> None:
        """幂等初始化 Bucket，根据配置设置访问策略"""

        if self._is_initialized:
            return

        async with self._init_lock:
            if self._is_initialized:
                return

            def _sync_init():
                if not self.client.bucket_exists(self.bucket):
                    self.client.make_bucket(self.bucket)

                if self.public_read:
                    # 知识库 Bucket：允许匿名读取
                    policy = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"AWS": ["*"]},
                                "Action": ["s3:GetObject"],
                                "Resource": [
                                    f"arn:aws:s3:::{self.bucket}/*"
                                ],
                            }
                        ],
                    }

                    self.client.set_bucket_policy(
                        self.bucket,
                        json.dumps(policy),
                    )
                else:
                    # 报销 Bucket：确保不存在匿名访问策略
                    self.client.delete_bucket_policy(self.bucket)

            await asyncio.to_thread(_sync_init)

            self._is_initialized = True

    # 上传文档
    async def upload(self, object_name: str, content: bytes, content_type: str | None) -> None:
        await self.init()  # 兜底确保初始化

        def put() -> None:
            self.client.put_object(self.bucket, object_name, BytesIO(content), len(content),
                                   content_type=content_type or "application/octet-stream")

        await asyncio.to_thread(put)

    # 下载文档
    async def download(self, object_name: str) -> bytes:
        await self.init()  # 兜底确保初始化

        def get() -> bytes:
            response = self.client.get_object(self.bucket, object_name)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(get)

    async def remove(self, object_name: str) -> None:
        await self.init()  # 兜底确保初始化
        await asyncio.to_thread(self.client.remove_object, self.bucket, object_name)

    async def upload_image_thumbnail(
            self,
            storage_path: str,
            content: bytes,
            max_side: int = THUMB_MAX_SIDE,
    ) -> str | None:
        """为图片生成等比缩略图并上传，返回缩略图对象名；失败返回 None（不影响主流程）。

        列表页缩略图区域只有 36px，直接用原图会让单页产生几十 MB 下载，
        拖慢同一时间的所有接口请求，因此上传时预生成一份小图。
        """
        await self.init()

        def build() -> bytes | None:
            try:
                from PIL import Image, ImageOps
            except ImportError:  # pragma: no cover - Pillow 缺失时静默跳过
                logger.warning("[MinIO] 未安装 Pillow，跳过缩略图生成")
                return None
            try:
                with Image.open(BytesIO(content)) as im:
                    im = ImageOps.exif_transpose(im)
                    if getattr(im, "is_animated", False):
                        im.seek(0)
                    im = im.convert("RGB")
                    im.thumbnail((max_side, max_side), Image.LANCZOS)
                    out = BytesIO()
                    im.save(out, format="JPEG", quality=THUMB_QUALITY, optimize=True, progressive=True)
                    return out.getvalue()
            except Exception as e:
                logger.warning(f"[MinIO] 生成缩略图失败 {storage_path}: {e}")
                return None

        thumb = await asyncio.to_thread(build)
        if not thumb:
            return None

        object_name = thumb_object_name(storage_path)
        try:
            await self.upload(object_name, thumb, "image/jpeg")
        except Exception as e:
            logger.error(f"[MinIO] 上传缩略图失败 {object_name}: {e}")
            return None
        return object_name

    async def remove_thumbnail(self, storage_path: str) -> None:
        """删除附件时同步清理缩略图（缩略图不存在时静默忽略）。"""
        try:
            await self.remove(thumb_object_name(storage_path))
        except Exception:
            pass

    # 清理minio文档图片目录
    async def clean_minio_directory(
            self,
            prefix: str,
            ctx: Optional[dict] = None
    ) -> None:
        await self.init()  # 兜底确保初始化
        try:
            def _do_clean():
                objects_to_delete = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
                delete_list = []
                for obj in objects_to_delete:
                    delete_list.append(DeleteObject(obj.object_name))
                    if len(delete_list) >= 1000:
                        errs = self.client.remove_objects(self.bucket, delete_list)
                        for err in errs:
                            logger.error(f"[MinIO] 批量删除失败：{err}")
                        delete_list.clear()
                if delete_list:
                    errs = self.client.remove_objects(self.bucket, delete_list)
                    for err in errs:
                        logger.error(f"[MinIO] 批量删除失败：{err}")

            await asyncio.to_thread(_do_clean)
        except Exception as e:
            logger.error(f"[MinIO] 清理目录失败：{e}")
            if ctx is not None:
                await emit(f"[图片] 清理旧图片目录失败：{str(e)[:100]}", ctx=ctx)

    # mineru转成md的图片上传（路径与消息均使用对外 uid，不暴露自增 id）
    async def upload_images_batch(
            self,
            target_images: List[Tuple[str, Path, Tuple[str, str]]],
            ctx: Dict
    ):
        await self.init()  # 兜底确保初始化
        total = len(target_images)
        kb_uid = ctx.get("kb_uid", "")
        document_uid = ctx.get("document_uid", "")
        upload_dir = f"{self.img_dir}/{kb_uid}/{document_uid}"

        # 清理该文档目录
        await self.clean_minio_directory(upload_dir, ctx=ctx)

        urls = {}
        for idx, (img_file, image_path, _) in enumerate(target_images, start=1):
            object_name = f"{upload_dir}/{img_file}"
            content_type = f"image/{image_path.suffix.replace('.', '').lower()}"

            def _sync_upload():
                self.client.fput_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                    file_path=str(image_path),
                    content_type=content_type
                )

            await asyncio.to_thread(_sync_upload)
            urls[img_file] = f"http://{settings.MINIO_ENDPOINT}/{self.bucket}/{object_name}"

            await emit(f"[图片] 正在同步至云端 ({idx}/{total})", ctx=ctx)
        return urls

    # docx图片上传（路径与消息均使用对外 uid，不暴露自增 id）
    async def upload_docx_images_batch(
            self,
            target_images: List[Tuple[str, bytes, str]],
            ctx: Dict
    ) -> Dict[str, str]:
        await self.init()  # 兜底确保初始化
        total = len(target_images)
        if total == 0:
            return {}

        kb_uid = ctx.get("kb_uid", "")
        document_uid = ctx.get("document_uid", "")
        upload_dir = f"{self.img_dir}/{kb_uid}/{document_uid}"
        await self.clean_minio_directory(upload_dir, ctx=ctx)

        urls = {}
        for idx, (img_filename, image_bytes, content_type) in enumerate(target_images, start=1):
            object_name = f"{upload_dir}/{img_filename}"

            def put():
                self.client.put_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                    data=BytesIO(image_bytes),
                    length=len(image_bytes),
                    content_type=content_type or "application/octet-stream"
                )

            await asyncio.to_thread(put)

            minio_url = f"http://{settings.MINIO_ENDPOINT}/{self.bucket}/{object_name}"
            urls[img_filename] = minio_url

            await emit(f"[图片] 正在同步至云端 ({idx}/{total})", ctx=ctx)

        return urls


@lru_cache(maxsize=1)
def get_minio_storage() -> MinioStorage:
    """知识库文件存储：公共读取"""
    return MinioStorage(
        bucket_name=settings.MINIO_BUCKET_NAME,
        public_read=True,
    )


@lru_cache(maxsize=1)
def get_expense_minio_storage() -> MinioStorage:
    """报销附件存储：私有 Bucket"""
    return MinioStorage(
        bucket_name=settings.MINIO_EXPENSE_BUCKET_NAME,
        public_read=False,
    )