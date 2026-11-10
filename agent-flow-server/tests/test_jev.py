"""意图识别节点：通过 Jev 判断用户当前消息的主要意图。"""
import asyncio
from typing import Any

import httpx

from app.core.config import settings

INTENT_CRITERIA = {
    "business_query": "查询业务记录、状态或统计数据。",
    "business_action": "发起或要求执行业务。",
    "knowledge_query": "询问企业制度、规范或知识。",
    "provide_information": "补充当前任务所需的信息。",
    "confirm_action": "确认之前提出的操作。",
    "cancel_action": "取消之前提出的操作。",
    "small_talk": "问候、感谢或普通闲聊。",
    "unknown": "信息不足、含义模糊或无法归类。",
}

JEV_TIMEOUT = 15.0


async def classify_intent_with_jev(state_text: str) -> dict[str, Any]:
    """
    调用 Jev 异步识别用户意图。

    Args:
        state_text: 当前对话上下文，包含历史消息和当前消息。

    Returns:
        {
            "intent": "business_query",
            "confidence": 0.95,
            "probabilities": {...}
        }

    注意：响应字段结构根据当前提供的示例暂定，
    需要拿真实 API 响应验证。
    """
    api_base = settings.JEV_API_BASE
    api_key = settings.JEV_API_KEY
    modol = settings.JEV_MODEL

    payload = {
        "model": modol,
        "state": state_text,
        "questions": {
            "intent": {
                "type": "choice",
                "instructions": "判断用户当前消息的主要意图。",
                "criteria": INTENT_CRITERIA,
            }
        },
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    async with httpx.AsyncClient(timeout=JEV_TIMEOUT) as client:
        response = await client.post(
            api_base,
            headers=headers,
            json=payload,
        )

        # HTTP 4xx / 5xx 时抛出异常
        response.raise_for_status()

    try:
        result = response.json()
        print(result)
        intent_result = result["questions"]["intent"]
        chosen_intent = intent_result["choice"]
        confidence = intent_result["confidence"]
        probabilities = intent_result.get("probabilities", {})
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Jev 返回数据格式不符合预期，响应内容：{response.text}"
        ) from exc

    # 防止模型返回不在预定义范围内的意图
    if chosen_intent not in INTENT_CRITERIA:
        raise RuntimeError(f"Jev 返回了未知意图：{chosen_intent}")

    return {
        "intent": chosen_intent,
        "confidence": confidence,
        "probabilities": probabilities,
    }


if __name__ == '__main__':
    asyncio.run(classify_intent_with_jev("公司报销流程怎么样的"))