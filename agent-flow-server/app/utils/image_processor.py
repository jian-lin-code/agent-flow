import asyncio
import base64
import hashlib
import re
import time
from functools import lru_cache
from typing import Tuple, Deque, Dict, Optional
from collections import deque

import redis.asyncio as aioredis
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.utils.llm import get_llm_model
from app.utils.logger import logger
from app.events.document_progress import emit

# Markdown / HTML 的 alt 文本里不能出现这些字符，否则会破坏语法结构
_ALT_FORBIDDEN = re.compile(r"[\[\]()<>|`*_#\r\n\t]+")
# 模型偶尔会返回这些"看起来有内容但其实没信息"的占位词
_EMPTY_SUMMARY_WORDS = {
    "", "图片", "图片描述", "这张图片", "如图所示", "无", "暂无", "图片内容",
    "一张图片", "图像", "图片展示", "示意图",
}


class ImageProcessor:
    def __init__(self):
        self.request_deque: Deque[float] = deque()
        # 并发场景下多个协程会同时读写 deque，必须加锁
        self._limiter_lock = asyncio.Lock()
        self._redis: aioredis.Redis | None = None

    # ------------------------------------------------------------------
    # 摘要缓存：key 为图片内容 md5，重新处理 / 重复上传可直接复用，
    # 避免同一张图被反复计费（缓存不可用时静默降级，不影响主流程）。
    # ------------------------------------------------------------------
    def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                decode_responses=True,
            )
        return self._redis

    @staticmethod
    def digest(image_data: bytes) -> str:
        return hashlib.md5(image_data).hexdigest()

    async def _cache_get(self, digest: str) -> Optional[str]:
        try:
            return await self._get_redis().get(f"img_summary:{digest}")
        except Exception:
            return None

    async def _cache_set(self, digest: str, summary: str) -> None:
        try:
            await self._get_redis().set(
                f"img_summary:{digest}", summary, ex=settings.IMAGE_SUMMARY_CACHE_TTL
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 摘要文本清洗：alt 文本既要可读，也不能破坏 Markdown / HTML 结构
    # ------------------------------------------------------------------
    @staticmethod
    def clean_summary(raw: str, max_len: int = 80) -> str:
        text = (raw or "").strip()
        text = text.replace("```markdown", "").replace("```", "").replace("`", "")
        text = _ALT_FORBIDDEN.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip(" ，。;；:：-—")
        # 去掉模型爱加的"这张图展示了…"之类的前缀
        text = re.sub(r"^(这张|该|此)?(图片|图像|插图|图)(中|里)?(展示了|显示了|说明了|描述的是|为|是)?", "", text).strip()
        if len(text) > max_len:
            text = text[:max_len].rstrip(" ，。;；:：") + "…"
        return text

    def build_fallback_summary(self, doc_stem: str, image_content: tuple[str, str], label: str = "") -> str:
        """模型返回空内容时的兜底 alt：用图片上下文/文档名拼一个可读描述。"""
        pre_text = self.clean_summary(image_content[0] if image_content else "", max_len=28)
        if pre_text:
            return self.clean_summary(f"{label or '插图'}：{pre_text}") or "文档插图"
        return self.clean_summary(f"{doc_stem} 中的{label or '插图'}") or "文档插图"

    async def generate_image_summary(
            self,
            image_data: bytes,
            img_format: str,
            doc_stem: str,
            image_content: Tuple[str, str],
            ctx: Optional[dict] = None,
            label: str = "",
    ) -> str:
        """核心方法：接收图片的 bytes，调用多模态大模型生成摘要。

        统一接收 bytes，抹平了 Path 和 bytes 的差异。
        返回值一定会是**非空且语法安全**的文本：模型失败/返回空串时走上下文兜底，
        否则 Markdown 里会留下 `![](url)` 这种没有描述、检索也搜不到的图片。
        """
        fallback = self.build_fallback_summary(doc_stem, image_content, label)
        if not image_data:
            return fallback

        digest = self.digest(image_data)
        if cached := await self._cache_get(digest):
            return cached

        try:
            base64_image = base64.b64encode(image_data).decode("utf-8")
            text_prompt = (
                f"这是'{doc_stem}'文件中的一张图片，"
                f"图片上文部分为：'{image_content[0]}'，"
                f"图片下文部分为：'{image_content[1]}'。"
                f"请用中文简要总结这张图片的内容，用于 Markdown 图片标题。"
            )
            messages = [
                HumanMessage(
                    content=[
                        {"type": "text", "text": text_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{img_format};base64,{base64_image}"}
                        }
                    ]
                )
            ]
            chat_model = get_llm_model(model_name=settings.VL_PLUS_MODEL)
            response = await chat_model.ainvoke(messages)

            summary = self.clean_summary(getattr(response, "content", "") or "")
            if summary.strip("。.… ") in _EMPTY_SUMMARY_WORDS or len(summary) < 2:
                logger.warning("[多模态] 模型返回空摘要，使用上下文兜底: %s", digest[:8])
                return fallback

            await self._cache_set(digest, summary)
            return summary

        except Exception as e:
            logger.error(f"[多模态] 图像总结失败, 详细错误: {str(e)}")
            document_uid = (ctx or {}).get("document_uid", "")
            if ctx is not None:
                await emit(
                    f"图片摘要失败，改用上下文描述（{str(e)[:60]}）",
                    ctx=ctx,
                    stage="parsing",
                    level="warn",
                )
            return fallback

    async def apply_rate_limit(
            self,
            max_requests: int | None = None,
            window_seconds: int = 60,
            ctx: Optional[dict] = None,
    ):
        """滑动窗口限流器（并发安全）。

        只在真正需要等待时输出一条日志：之前每张图片都会打印一条"时间戳已记录"，
        一本 300 页的手册会刷出几百条无用日志，把真正有用的进度信息淹没。
        """
        max_requests = max_requests or settings.IMAGE_SUMMARY_RPM
        async with self._limiter_lock:
            current_time = time.time()
            while self.request_deque and current_time - self.request_deque[0] >= window_seconds:
                self.request_deque.popleft()

            if len(self.request_deque) >= max_requests:
                sleep_duration = window_seconds - (current_time - self.request_deque[0])
                if sleep_duration > 0:
                    await emit(
                        f"多模态模型限流（{max_requests} 次/分钟），等待 {sleep_duration:.1f}s 后继续",
                        ctx=ctx,
                        stage="parsing",
                        level="warn",
                    )
                    await asyncio.sleep(sleep_duration)
                    current_time = time.time()
                    while self.request_deque and current_time - self.request_deque[0] >= window_seconds:
                        self.request_deque.popleft()

            self.request_deque.append(time.time())

    @staticmethod
    def merge_summary_and_url(summaries: Dict[str, str], urls: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
        """
        合并图片摘要字典和URL字典，过滤掉上传失败无URL的图片
        :param summaries: 图片摘要字典，键：图片文件名，值：内容摘要
        :param urls: 图片URL字典，键：图片文件名，值：MinIO访问URL
        :return: 合并后的图片信息字典，键：图片文件名，值：(摘要, URL)元组
        """
        image_info = {}
        for image_file, summary in summaries.items():
            if url := urls.get(image_file):
                image_info[image_file] = (summary, url)
        return image_info


@lru_cache(maxsize=1)
def get_image_processor() -> ImageProcessor:
    return ImageProcessor()
