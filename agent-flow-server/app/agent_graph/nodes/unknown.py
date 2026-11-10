"""AgentFlow 未知意图兜底处理节点。"""

from typing import Any

from app.agent_graph.state import AgentState
from app.events.chat_progress import (
    ChatProgressEvent,
    ChatProgressScope,
    emit,
)


UNKNOWN_RESPONSE = (
    "抱歉，我暂时无法准确理解你的需求。\n\n"
    "目前我主要支持以下功能：\n"
    "1. 发起报销申请\n"
    "2. 查询报销记录、审批进度和审批历史\n"
    "3. 查询报销预审结果和报销统计\n"
    "4. 查询企业知识库中的制度和业务规范\n\n"
    "你可以尝试换一种方式描述你的需求。"
)


async def handle_unknown(
    state: AgentState,
) -> dict[str, Any]:
    """处理无法识别的用户意图。

    不调用 LLM，不执行知识库检索和业务操作，
    直接返回能力范围提示。
    """

    answer = UNKNOWN_RESPONSE

    workflow_run_uid = state.get("workflow_run_uid")

    # 通过 SSE 推送固定回复，保持与普通回复一致的前端交互。
    if workflow_run_uid:
        await emit(
            "正在生成回复",
            run_uid=workflow_run_uid,
            event=ChatProgressEvent.CONTENT_DELTA,
            scope=ChatProgressScope.MESSAGE,
            delta=answer,
        )

    return {
        "answer": answer,
    }