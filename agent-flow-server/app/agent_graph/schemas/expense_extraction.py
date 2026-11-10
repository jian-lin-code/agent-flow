
"""报销费用信息提取 Schema。"""

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class ExpenseItemExtraction(BaseModel):
    """单条报销费用操作。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["add", "update", "delete"] = Field(
        description=(
            "操作类型："
            "add 表示新增费用；"
            "update 表示补充或修改已有费用；"
            "delete 表示删除已有费用。"
        )
    )

    target_item_id: str | None = Field(
        default=None,
        description="更新已有费用时必须填写目标费用 ID；新增费用时为 null。",
    )

    category: str | None = Field(
        default=None,
        description="费用类别，例如交通费、住宿费、餐饮费。无法确定时返回 null。",
    )

    amount: str | None = Field(
        default=None,
        description="费用金额，数字字符串，不带货币符号。用户没有明确提供时返回 null。",
    )

    description: str | None = Field(
        default=None,
        description="费用用途或补充说明。用户没有提供时返回 null。",
    )

    expense_date: str | None = Field(
        default=None,
        description=(
            "费用发生日期，格式 YYYY-MM-DD。"
            "明确日期直接转换；今天、昨天、前天、上周五等相对日期"
            "必须结合系统提供的当前日期计算。无法确定时返回 null，禁止默认使用今天。"
        ),
    )

    @model_validator(mode="after")
    def validate_target_item_id(self):
        if self.action == "add" and self.target_item_id is not None:
            raise ValueError("add 操作的 target_item_id 必须为 null")

        if self.action in ("update", "delete") and not self.target_item_id:
            raise ValueError(
                f"{self.action} 操作必须提供 target_item_id"
            )

        return self

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: str | None):
        if value is None:
            return value

        value = value.strip()

        if not value:
            raise ValueError("amount 不能为空字符串")

        if not re.fullmatch(r"\d+(\.\d{1,2})?", value):
            raise ValueError("amount 必须是最多保留两位小数的数字字符串")

        try:
            if Decimal(value) <= 0:
                raise ValueError("amount 必须大于 0")
        except InvalidOperation:
            raise ValueError("amount 不是有效金额")

        return value

    @field_validator("category", "description")
    @classmethod
    def validate_optional_text(cls, value: str | None):
        if value is None:
            return value

        value = value.strip()

        if not value:
            return None  # 👈 空字符串直接转为 None

        return value

    @field_validator("expense_date")
    @classmethod
    def validate_expense_date(cls, value: str | None):
        if value is None:
            return value

        from datetime import date

        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("expense_date 必须是 YYYY-MM-DD 格式的有效日期")

        if parsed.isoformat() != value:
            raise ValueError("expense_date 必须使用 YYYY-MM-DD 格式")

        return value


class ExpenseExtractionResult(BaseModel):
    """当前消息识别出的费用操作。"""

    model_config = ConfigDict(extra="forbid")

    operations: list[ExpenseItemExtraction] = Field(
        default_factory=list,
        description="当前消息产生的费用操作，可以包含多条新增或更新操作。",
    )

    clarification: str | None = Field(
        default=None,
        description="无法确定费用或更新目标时，需要向用户询问的内容。",
    )
