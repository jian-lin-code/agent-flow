"""业务任务解析节点。"""

from typing import Any
from uuid import UUID

from app.agent_graph.state import AgentState
from app.services.business_task_service import BusinessTaskService
from app.utils.task_ui import _build_task_list_ui_payload


async def resolve_business_task(
    state: AgentState,
) -> dict[str, Any]:
    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")
    action = state.get("action")
    selected_task_uid = state.get("selected_task_uid")

    business_tasks = state.get("business_tasks") or []
    active_task_uid = state.get("active_business_task_uid")

    if user_id is None or conversation_id is None:
        return {
            "selected_business_task": None,
            "task_selection_required": False,
            "answer": "缺少用户或会话信息，暂时无法定位业务任务。",
        }

    business_service = BusinessTaskService()

    # 1. 用户显式选择任务：验证并持久化绑定。
    if action == "select_business_task":
        if not selected_task_uid:
            return {
                "selected_business_task": None,
                "task_selection_required": False,
                "answer": "任务选择失败：缺少任务 ID，请重新点击任务卡片。",
            }

        try:
            normalized_uid = str(UUID(selected_task_uid))
        except (ValueError, TypeError, AttributeError):
            return {
                "selected_business_task": None,
                "task_selection_required": False,
                "answer": "任务标识无效，请重新选择需要操作的任务。",
            }

        try:
            selected_task = await business_service.select_business_task(
                task_uid=normalized_uid,
                user_id=user_id,
                conversation_id=conversation_id,
            )
        except RuntimeError:
            return {
                "selected_business_task": None,
                "task_selection_required": False,
                "answer": (
                    "你选择的任务不存在、不属于当前会话，"
                    "或当前状态不允许继续操作。请重新选择。"
                ),
            }

        return {
            "selected_business_task": selected_task,
            "task_selection_required": False,
            "answer": (
                f"已选择报销任务：{selected_task['title']}。\n"
                "接下来可以继续补充费用明细，或查看当前报销信息。"
            ),
            "ui_payload": {
                "ui_type": "business_task",
                "business_task": selected_task,
            },
        }

    # 2. 普通消息：优先恢复会话中已经绑定的任务。
    if active_task_uid:
        # 不能直接使用上下文里的极简任务字典（缺少 display 等字段），
        # 必须通过 Service 重新获取经 _build_business_task_response 包装的完整数据。
        try:
            active_task = await business_service.select_business_task(
                task_uid=active_task_uid,
                user_id=user_id,
                conversation_id=conversation_id,
            )
        except RuntimeError:
            active_task = None

        if active_task is not None:
            return {
                "selected_business_task": active_task,
                "task_selection_required": False,
            }

        # 3. 绑定任务已经不在可操作列表中，清除失效绑定。
        await business_service.clear_active_business_task(
            user_id=user_id,
            conversation_id=conversation_id,
            expected_task_uid=active_task_uid,
        )

    # 4. 当前用户没有可操作任务
    if not business_tasks:
        return {
            "selected_business_task": None,
            "task_selection_required": False,
            "answer": ("当前会话没有可以操作的待处理业务任务噢，"
                       "要不要我帮你发起一笔新的报销单？🙋‍♂️\n"
                       "💡 小提示：已经提交的申请正在走审批流程，"
                       "暂时无法重新编辑或撤回，可以在「我的报销」里查看进度～"
                        ),
        }

    if len(business_tasks) == 1:
        selected_task = business_tasks[0]

        # 单任务自动关联也保存到会话，保持行为一致。
        selected_task = await business_service.select_business_task(
            task_uid=selected_task["uid"],
            user_id=user_id,
            conversation_id=conversation_id,
        )

        return {
            "selected_business_task": selected_task,
            "task_selection_required": False,
            "ui_payload": {
                "ui_type": "business_task",
                "business_task": selected_task,
            },
        }

    return {
        "selected_business_task": None,
        "task_selection_required": True,
        "answer": "当前会话有多个待处理任务，请先选择要操作的任务：",
        "ui_payload": _build_task_list_ui_payload(business_tasks,action="select_business_task",),
        # 意图节点可能已抽取了费用操作，但此时还没有确定目标任务，
        # 必须丢弃，避免下一轮误用到用户选中的其他任务上。
        "extracted_operations": None,
        "extraction_clarification": None,
    }