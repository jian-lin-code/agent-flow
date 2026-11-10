
"""聊天工作流进度事件定义、Redis 发布与订阅。"""
import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.utils.datetime_helper import utc_now
from app.utils.logger import logger


class RedisChatProgressBroker:
    """通过 Redis Pub/Sub 发布和订阅工作流进度事件。"""

    def __init__(self, redis_url: str) -> None:
        """初始化 Redis 进度事件客户端。"""
        self.redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
        )

    async def publish(
        self,
        run_uid: str,
        event: dict[str, Any],
    ) -> None:
        """向指定工作流的 Redis 频道发布一条进度事件。"""
        channel = f"chat_progress:{run_uid}"

        await self.redis.publish(
            channel,
            json.dumps(event, ensure_ascii=False),
        )

    async def subscribe(
        self,
        run_uid: str,
        ready_event: asyncio.Event | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """订阅指定工作流的事件，并忽略无法解析的消息。"""
        pubsub = self.redis.pubsub()
        channel = f"chat_progress:{run_uid}"

        await pubsub.subscribe(channel)
        # 通知调用方：Redis 订阅已经真正建立。
        if ready_event is not None:
            ready_event.set()

        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue

                raw_data = message.get("data")

                if not isinstance(raw_data, str):
                    continue

                try:
                    event_data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(
                        "忽略格式错误的聊天进度事件：run_uid=%s",
                        run_uid,
                    )
                    continue

                if isinstance(event_data, dict):
                    yield event_data

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def close(self) -> None:
        """关闭 Redis 客户端，释放连接资源。"""
        await self.redis.aclose()


progress_broker = RedisChatProgressBroker(
    f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
)


class ChatProgressEvent(str, Enum):
    """定义前后端统一使用的聊天工作流事件名称。"""

    RUN_STARTED = "run_started"
    RUN_SNAPSHOT = "run_snapshot"
    STEP_STARTED = "step_started"
    PROGRESS = "progress"

    # 模型流式输出：每次推送一个文本增量
    CONTENT_DELTA = "content_delta"

    ASSISTANT_MESSAGE = "assistant_message"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


class ChatProgressScope(str, Enum):
    """定义进度事件影响的数据范围。"""

    RUN = "run"
    STEP = "step"
    MESSAGE = "message"


def _enum_value(value: Any) -> Any:
    """将枚举转换为其底层值，保证事件字段可以 JSON 序列化。"""
    if isinstance(value, Enum):
        return value.value

    return value


def _infer_scope(
    event: str,
    step_name: str | None,
    message_uid: str | None,
) -> ChatProgressScope:
    """根据事件类型推断事件作用范围。"""
    if event == ChatProgressEvent.STEP_STARTED.value:
        return ChatProgressScope.STEP

    if event == ChatProgressEvent.CONTENT_DELTA.value:
        return ChatProgressScope.MESSAGE

    if step_name is not None:
        return ChatProgressScope.STEP

    if message_uid is not None:
        return ChatProgressScope.MESSAGE

    return ChatProgressScope.RUN


async def emit(
    message: str,
    *,
    run_uid: str | None = None,
    ctx: dict[str, Any] | None = None,
    event: str | ChatProgressEvent = ChatProgressEvent.PROGRESS,
    status: str | Enum | None = None,
    scope: str | ChatProgressScope | None = None,
    step_name: str | None = None,
    step_key: str | None = None,
    display_name: str | None = None,
    message_uid: str | None = None,
    content: str | None = None,
    delta: str | None = None,
    error_message: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    extra_data: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    """
    记录工作流进度，并发布统一格式的 SSE 事件。

    message：进度说明。
    content：完整聊天消息正文。
    delta：本次模型生成的文本增量。
    scope：区分工作流、步骤和聊天消息级别的状态。
    """
    if not run_uid and isinstance(ctx, dict):
        run_uid = ctx.get("run_uid") or ""

    event_value = _enum_value(event)
    status_value = _enum_value(status)

    if not isinstance(event_value, str):
        raise TypeError("event 必须是字符串或 ChatProgressEvent")

    if not run_uid:
        logger.warning("缺少 run_uid，无法发布聊天进度事件")
        return

    if scope is None:
        scope_value = _infer_scope(
            event=event_value,
            step_name=step_name,
            message_uid=message_uid,
        ).value
    else:
        scope_value = _enum_value(scope)

    if not isinstance(scope_value, str):
        raise TypeError("scope 必须是字符串或 ChatProgressScope")

    timestamp = utc_now().isoformat()

    payload: dict[str, Any] = {
        "event_uid": str(uuid.uuid4()),
        "run_uid": run_uid,
        "event": event_value,
        "scope": scope_value,
        "time": timestamp,
        "message": message,
    }

    if status_value is not None:
        payload["status"] = status_value

    if step_name is not None:
        payload["step_name"] = step_name

    if step_key is not None:
        payload["step_key"] = step_key

    if display_name is not None:
        payload["display_name"] = display_name

    if message_uid is not None:
        payload["message_uid"] = message_uid

    if content is not None:
        payload["content"] = content

    if delta is not None:
        payload["delta"] = delta

    if input_tokens is not None:
        payload["input_tokens"] = input_tokens

    if output_tokens is not None:
        payload["output_tokens"] = output_tokens

    if total_tokens is not None:
        payload["total_tokens"] = total_tokens

    if error_message is not None:
        payload["error_message"] = error_message

    if extra_data is not None:
        payload["extra_data"] = extra_data

    if metrics is not None:
        payload["metrics"] = metrics

    if isinstance(ctx, dict):
        ctx.setdefault("process_logs", []).append(payload.copy())

    try:
        await progress_broker.publish(run_uid, payload)
    except Exception:
        # 推送失败不能覆盖数据库中已经持久化的执行结果。
        logger.exception(
            "发布聊天进度事件失败：run_uid=%s event=%s",
            run_uid,
            event_value,
        )
