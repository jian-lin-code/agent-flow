
"""AgentFlow 历史消息处理。"""

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage


def build_history_messages(
    history: list[dict[str, str]] | None,
    max_messages: int = 10,
) -> list[BaseMessage]:
    """将历史消息转换为 LangChain 消息对象。

    只保留最近 max_messages 条有效消息。
    """

    if not history:
        return []

    messages: list[BaseMessage] = []

    for item in history:
        role = item.get("role")
        content = item.get("content", "").strip()

        if not content:
            continue

        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    return messages[-max_messages:]
