"""报销 AI 初审相关 Schema。"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 如果模型和 Schema 在同一个项目里，强烈建议直接复用模型里的枚举，避免改了一处忘了另一处
from app.models.expense_pre_review import PreReviewResult

# 直接使用模型里的枚举作为别名
ExpenseReviewDecision = PreReviewResult


class ExpensePreReviewResult(BaseModel):
    """AI 报销初审结果。"""

    model_config = ConfigDict(extra="forbid")

    # 1. 核心结论（对应数据库字段 result）
    decision: ExpenseReviewDecision = Field(
        description="初审结论，只能返回：pass（通过）、fail（不通过）、manual_review（需人工介入）"
    )
    risk_level: str = Field(
        description="风险等级：high, medium, low, none"
    )

    # 2. 业务意见（对应数据库字段 summary）
    opinion: str = Field(
        min_length=1,
        description="初审意见，简明说明判断结果及其依据"
    )

    # 3. 问题与证据（打包进 result_data）
    problems: list[str] = Field(
        default_factory=list,
        description="发现的具体问题列表；没有问题时返回空数组"
    )
    # （打包进 result_data）
    evidence: str = Field(
        default="",
        description="支撑判断的直接证据。例如：'发票价税合计为500，报销单填写为600，差异100'"
    )

    # 4. 结构化留痕（打包进 result_data）
    is_document_valid: bool = Field(
        default=True,
        description="上传的图片是否是一张合法的发票/凭证。如果是风景照或无关图片，返回 false"
    )
    # （打包进 result_data）
    extracted_data: dict[str, Any] = Field(
        default_factory=dict,
        description="从发票图片中提取的结构化字段（金额、日期、发票号等）"
    )