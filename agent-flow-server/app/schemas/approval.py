"""审批相关 Pydantic 模型。"""

from enum import Enum

from pydantic import BaseModel, Field


class ApprovalDecision(str, Enum):
    """审批结论。"""

    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecisionRequest(BaseModel):
    """审批决策请求体。"""

    decision: ApprovalDecision = Field(
        description="审批结论：approved（通过）/ rejected（驳回）"
    )
    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="审批意见，驳回时建议填写原因",
    )
