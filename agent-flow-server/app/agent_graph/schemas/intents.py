"""AgentFlow 意图定义。"""

from enum import Enum

from pydantic import BaseModel, Field, ConfigDict

from app.agent_graph.schemas.business_query import BusinessQueryType, BusinessQueryParams
from app.agent_graph.schemas.expense_extraction import ExpenseItemExtraction


class Intent(str, Enum):
    """用户消息意图。"""

    BUSINESS_ACTION = "business_action"
    """发起或要求执行业务操作。"""

    BUSINESS_QUERY = "business_query"
    """查询业务记录、状态或统计数据。"""

    KNOWLEDGE_QUERY = "knowledge_query"
    """询问企业制度、规范或通用知识。"""

    PROVIDE_INFORMATION = "provide_information"
    """补充当前任务所需的信息。"""

    CONFIRM_ACTION = "confirm_action"
    """确认之前提出的操作。"""

    CANCEL_ACTION = "cancel_action"
    """取消之前提出的操作。"""

    RESUME_ACTION = "resume_action"
    """恢复之前取消或中断的业务任务。"""

    CONFIRM_RESUME = "confirm_resume"
    """确认恢复之前取消的业务任务。"""

    REJECT_RESUME = "reject_resume"
    """拒绝恢复之前取消的业务任务。"""

    SMALL_TALK = "small_talk"
    """问候、感谢或普通闲聊。"""

    UNKNOWN = "unknown"
    """信息不足、含义模糊或无法归类。"""




class IntentResult(BaseModel):
    """LLM 意图识别结果。"""

    intent: Intent = Field(
        description="用户当前消息的主要意图。",
    )
    has_expense_information: bool = Field(
        description=(
            "用户当前消息是否包含可用于报销的实际费用信息，"
            "例如费用类别、金额、发生日期、费用用途等。"
            "仅表达报销意愿不算费用信息。"
        ),
    )
