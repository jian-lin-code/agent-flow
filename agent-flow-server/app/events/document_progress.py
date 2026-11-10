from datetime import datetime
from typing import Dict, Any, AsyncIterator
import re

from app.core.config import settings
import asyncio
import json
import redis.asyncio as aioredis
from app.schemas.knowledge import DocumentProgressEvent

# 历史日志里的 "[解析] xxx" / "[Worker] xxx" 前缀与前端展示的阶段标签重复，
# 统一在出口处剥掉，让日志正文保持干净（前端用 stage 字段做分组和着色）。
_LEGACY_TAG_RE = re.compile(
    r"^\s*\[(解析|Worker|图片|多模态|缓存|入库|向量化|切分|检索|重排序|完成|错误)\]\s*"
)

class RedisProgressBroker:
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url, decode_responses=True)

    async def publish(self, event: DocumentProgressEvent) -> None:
        # 把事件序列化为 JSON，发布到对应的频道（频道键使用对外 uid，不暴露内部 id）
        channel = f"doc_progress:{event.document_uid}"
        await self.redis.publish(channel, event.model_dump_json())

    async def subscribe(
        self,
        document_uid: str,
        ready_event: asyncio.Event | None = None,
    ) -> AsyncIterator[DocumentProgressEvent]:
        pubsub = self.redis.pubsub()
        channel = f"doc_progress:{document_uid}"
        await pubsub.subscribe(channel)

        # 通知调用方：Redis 订阅已经真正建立，可以安全地查询数据库快照了
        if ready_event is not None:
            ready_event.set()

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue

                yield DocumentProgressEvent(**data)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()


# 这里需要读取你的 Redis 地址配置
progress_broker = RedisProgressBroker(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")


async def emit(
        message: str,
        *,
        document_uid: str | None = None,
        ctx: dict | None = None,  # 👈 新增参数：接收 ARQ 的上下文
        status: str | None = None,
        stage: str | None = None,
        progress: int | None = None,
        level: str = "info",
        stage_records: list[Dict[str, Any]] | None = None,
        chunk_count: int | None = None,
        vectorized_count: int | None = None
) -> None:
    # document_uid 未显式传入时，优先从 ctx 读取（worker 加载文档后写入），
    # 这样 parser/chunker/embedding 等仅透传 ctx 的 emit 调用也能带上对外 uid。
    if not document_uid and isinstance(ctx, dict):
        document_uid = ctx.get("document_uid") or ""

    # 阶段的取值优先级：显式传入 > status > ctx["stage"]（worker 在进入新阶段时写入，
    # 让 parser/chunker 等下游模块的 emit 自动带上正确的阶段，不用每个调用点都传）
    if not stage and isinstance(ctx, dict):
        stage = ctx.get("stage")
    stage = stage or status
    if progress is not None:
        progress = max(0, min(100, int(progress)))

    # 剥掉历史遗留的 "[解析]" 之类前缀，阶段信息交给 stage 字段承载
    message = _LEGACY_TAG_RE.sub("", message or "").strip() or (message or "").strip()

    # 1. 把时间戳格式化好，准备组装日志
    log_item = {
        "document_uid": document_uid,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "stage": stage,
        "level": level,
    }

    # 2. 👇 核心：如果传了 ctx，就把日志追加到内存里
    if ctx is not None:
        if "process_logs" not in ctx:
            ctx["process_logs"] = []
        ctx["process_logs"].append(log_item)

    # 3. 发送给前端 (SSE) —— 事件对外暴露 document_uid，不暴露内部自增 id
    await progress_broker.publish(DocumentProgressEvent(
        document_uid=document_uid,
        message=message,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status=status,
        stage=stage,
        progress=progress,
        level=level,
        stage_records=stage_records,
        chunk_count=chunk_count,
        vectorized_count=vectorized_count,
    ))

