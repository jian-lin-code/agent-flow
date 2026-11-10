
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent_graph.history import build_history_messages
from app.agent_graph.prompt_manager import render_prompt
from app.agent_graph.state import AgentState
from app.agent_graph.token_usage import (
    create_usage_callback,
    get_token_usage,
    accumulate_token_usage,
)
from app.events.chat_progress import (
    ChatProgressEvent,
    ChatProgressScope,
    emit,
)
from app.utils.llm import get_llm_model


async def handle_small_talk(state: AgentState) -> dict:
    """生成普通对话回复，并通过 Redis 发布模型文本增量。"""

    current_message = state.get("current_message", "").strip()
    workflow_run_uid = state.get("workflow_run_uid")
    system_prompt = render_prompt("chat/generate_response.j2")

    messages = [
        SystemMessage(content=system_prompt),
        *build_history_messages(state.get("history")),
        HumanMessage(
            content=(
                f"当前用户消息：{current_message}\n"
                "根据以上信息回复用户。"
            )
        ),
    ]

    usage_callback = create_usage_callback()

    llm = get_llm_model()

    answer_parts: list[str] = []

    try:
        async for chunk in llm.astream(
            messages,
            config={
                "callbacks": [usage_callback],
            },
            stream_options={"include_usage": True}
        ):
            content = chunk.content

            if isinstance(content, str):
                text_delta = content

            elif isinstance(content, list):
                # 兼容部分模型返回的多模态内容块。
                text_delta = "".join(
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict)
                    and item.get("type") == "text"
                    and isinstance(item.get("text"), str)
                )

            else:
                text_delta = ""

            if not text_delta:
                continue

            answer_parts.append(text_delta)

            await emit(
                f"正在生成回复",
                run_uid=workflow_run_uid,
                event=ChatProgressEvent.CONTENT_DELTA,
                scope=ChatProgressScope.MESSAGE,
                delta=text_delta,
            )

    except Exception:
        # 让异常继续向上传递，由 step_tracker 和 Worker 负责记录失败。
        raise

    answer = "".join(answer_parts).strip()

    if not answer:
        raise RuntimeError("模型返回的回复内容为空")

    usage = get_token_usage(usage_callback)

    print("回复生成 Token usage:", usage)

    return {
        "answer": answer,
        **accumulate_token_usage(state, usage),
    }
