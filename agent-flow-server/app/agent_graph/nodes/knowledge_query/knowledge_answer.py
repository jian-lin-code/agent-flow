"""知识库问答节点。"""

from typing import Any

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
from app.utils.task_ui import _build_knowledge_sources_payload


# 将检索上下文整理成带编号的知识来源文本
def _build_knowledge_contexts(
    contexts: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """构建模型使用的知识上下文，并整理前端展示的引用来源。"""
    context_parts: list[str] = []
    sources: list[dict[str, Any]] = []

    for index, context in enumerate(contexts, start=1):
        content = (context.get("content") or "").strip()
        if not content:
            continue

        document_title = context.get("document_title") or "未知文档"
        knowledge_base_name = context.get("knowledge_base_name") or "未知知识库"
        start_line = context.get("source_start_line")
        end_line = context.get("source_end_line")

        if start_line is not None and end_line is not None:
            location = f"第 {start_line}-{end_line} 行"
        elif start_line is not None:
            location = f"第 {start_line} 行"
        else:
            location = "未记录行号"

        source = {
            "index": len(sources) + 1,
            "document_title": document_title,
            "knowledge_base_name": knowledge_base_name,
            "source_start_line": start_line,
            "source_end_line": end_line,
            "document_id": context.get("document_id"),
            "parent_chunk_id": context.get("parent_chunk_id"),
            # 引用定位：前端据此跳转到文档预览并滚动到命中段落
            "document_uid": context.get("document_uid"),
            "knowledge_base_uid": context.get("knowledge_base_uid"),
            "heading_path": context.get("heading_path") or [],
            "anchor_text": context.get("anchor_text") or "",
        }

        sources.append(source)

        context_parts.append(
            # f"[知识来源 {source['index']}]\n"
            # f"知识库：{knowledge_base_name}\n"
            # f"文档：{document_title}\n"
            # f"位置：{location}\n"
            f"内容：\n{content}"
        )

    return "\n\n".join(context_parts), sources


# 根据知识库检索上下文生成有来源依据的回答
async def handle_knowledge_answer(state: AgentState) -> dict[str, Any]:
    """结合用户问题和知识库上下文生成回答，并推送文本增量。"""
    current_message = (state.get("current_message") or "").strip()
    workflow_run_uid = state.get("workflow_run_uid")

    contexts = state.get("knowledge_contexts") or []
    if not contexts:
        raise ValueError("生成知识库回答时缺少检索上下文")

    knowledge_context, sources = _build_knowledge_contexts(contexts)

    if not knowledge_context:
        raise ValueError("知识库检索上下文中没有有效内容")

    system_prompt = render_prompt("knowledge/knowledge_answer.j2")

    messages = [
        SystemMessage(content=system_prompt),
        *build_history_messages(state.get("history"),4),
        HumanMessage(
            content=(
                f"用户当前问题：\n{current_message}\n\n"
                f"知识库检索上下文：\n{knowledge_context}\n\n"
                "请严格依据知识库检索上下文回答用户问题。"
            )
        ),
    ]

    usage_callback = create_usage_callback()
    llm = get_llm_model()
    answer_parts: list[str] = []

    # 流式接收模型输出，并将文本增量推送到前端
    async for chunk in llm.astream(
        messages,
        config={"callbacks": [usage_callback]},
        stream_options={"include_usage": True}
    ):
        content = chunk.content

        if isinstance(content, str):
            text_delta = content
        elif isinstance(content, list):
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
            "正在生成知识库回答",
            run_uid=workflow_run_uid,
            event=ChatProgressEvent.CONTENT_DELTA,
            scope=ChatProgressScope.MESSAGE,
            delta=text_delta,
        )

    answer = "".join(answer_parts).strip()

    if not answer:
        raise RuntimeError("知识库问答模型返回的回复内容为空")

    usage = get_token_usage(usage_callback)

    print("知识库问答 Token usage:", usage)

    return {
        "answer": answer,
        "ui_payload": _build_knowledge_sources_payload(sources),
        **accumulate_token_usage(state, usage),
    }


# 在没有检索到知识上下文时生成明确的无结果回复
async def handle_knowledge_no_result(state: AgentState) -> dict[str, Any]:
    """告知用户当前可访问的知识库中没有检索到相关资料。"""
    workflow_run_uid = state.get("workflow_run_uid")

    if not workflow_run_uid:
        raise ValueError("知识库无结果回复时缺少 workflow_run_uid")

    answer = (
        "暂时没有在你有权限访问的知识库中检索到与这个问题相关的资料。"
        "你可以尝试换一种问法，或确认相关制度文件是否已经上传到知识库。"
    )

    await emit(
        "未检索到相关知识资料",
        run_uid=workflow_run_uid,
        event=ChatProgressEvent.CONTENT_DELTA,
        scope=ChatProgressScope.MESSAGE,
        delta=answer,
    )

    return {
        "answer": answer,
        "knowledge_sources": [],
    }