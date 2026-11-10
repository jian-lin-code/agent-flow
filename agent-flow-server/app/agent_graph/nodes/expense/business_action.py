"""报销业务发起节点。"""

from typing import Any
from app.agent_graph.state import AgentState
from app.services.business_task_service import BusinessTaskService
from app.utils.task_ui import _build_task_ui_payload


async def handle_business_action(
    state: AgentState,
) -> dict[str, Any]:
    """处理业务发起意图，创建报销业务草稿。"""

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")
    workflow_run_uid = state.get("workflow_run_uid")
    business_action_ready = state.get("business_action_ready")
    # 1. 检查必要的上下文信息
    if user_id is None or conversation_id is None:
        return {
            "business_action_ready": False,
            "selected_business_task": None,
            "task_selection_required": False,
            "answer": "缺少用户或会话信息，暂时无法创建报销任务。",
        }

    if not workflow_run_uid:
        return {
            "business_action_ready": False,
            "selected_business_task": None,
            "task_selection_required": False,
            "answer": "缺少工作流执行信息，暂时无法创建报销任务。",
        }

    # 2. 调用业务服务
    business_service = BusinessTaskService()

    result = await business_service.create_business_task_from_workflow(
        user_id=user_id,
        conversation_id=conversation_id,
        workflow_run_uid=workflow_run_uid,
    )

    # 3. 检查服务返回结果
    selected_task = result.get("selected_business_task")

    if not selected_task:
        return {
            "business_action_ready": False,
            "selected_business_task": None,
            "task_selection_required": False,
            "answer": "报销任务创建失败，请稍后重试。",
        }


    if not business_action_ready:
        return {
            "business_action_ready": business_action_ready,  # 不需要收集信息
            "selected_business_task": selected_task,
            "task_selection_required": False,
            "answer": (
                "已为你创建报销草稿。\n\n"
                "请提供本次报销的费用信息，例如费用类型、金额、"
                "发生日期和费用用途，我会帮你整理报销明细。"
            ),
            "ui_payload": _build_task_ui_payload(selected_task),
        }

    return {
        "business_action_ready": True, #创建成功继续进去 ---> 提取信息
        "selected_business_task": selected_task,
        "task_selection_required": False,
    }