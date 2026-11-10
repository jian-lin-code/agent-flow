from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class BusinessQueryType(str, Enum):
    """业务查询子类型。"""

    EXPENSE_LIST = "expense_list"
    """查询报销记录列表。"""

    EXPENSE_DETAIL = "expense_detail"
    """查询报销单详情。"""

    EXPENSE_PROGRESS = "expense_progress"
    """查询报销审批进度。"""

    EXPENSE_APPROVAL_HISTORY = "expense_approval_history"
    """查询报销审批历史。"""

    EXPENSE_PRE_REVIEW = "expense_pre_review"
    """查询报销 AI 初审结果。"""

    EXPENSE_STATISTICS = "expense_statistics"
    """查询报销统计数据。"""

class BusinessQueryScope(str, Enum):
    """业务数据查询范围。"""

    SELF = "self"
    """查询当前登录用户自己的数据。"""

    ALL = "all"
    """查询企业全局数据。"""

    USER = "user"
    """查询指定用户的数据。"""

class BusinessQueryParams(BaseModel):
    """业务查询统一参数。"""

    model_config = ConfigDict(extra="forbid")

    scope: BusinessQueryScope = Field(
        default=BusinessQueryScope.SELF,
        description=(
            "数据查询范围。默认 self。"
            "用户查询自己的数据时使用 self；"
            "管理员明确要求查询企业全部数据时使用 all；"
            "管理员明确指定某个员工时使用 user。"
            "不能仅根据用户角色判断查询范围。"
        ),
    )

    target_user_name: str | None = Field(
        default=None,
        description=(
            "指定查询的员工姓名。"
            "仅当 scope=user 时使用，"
            "例如查询张三的报销记录时提取张三。"
            "不得自行推测用户姓名。"
        ),
    )
    claim_no: str | None = Field(
        default=None,
        description="报销单业务编号，例如 BX20261106001。查询指定报销单详情、进度或审批记录时使用。",
    )

    time_expression: str | None = Field(
        default=None,
        description=(
            "用户原始时间表达，例如上个月、今年、最近七天、"
            "2026年10月。不负责计算具体日期。"
        ),
    )

    statuses: list[str] | None = Field(
        default=None,
        description="用户明确指定的报销单状态筛选条件。",
    )

    expense_category: str | None = Field(
        default=None,
        description="费用类别筛选条件，例如交通费、餐饮费。",
    )

    group_by: str | None = Field(
        default=None,
        description="统计分组维度，例如 month、category、status。",
    )


    page: int | None = Field(
        default=None,
        ge=1,
        description="列表查询页码，从 1 开始。",
    )

    page_size: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="每页记录数量，最大 100。",
    )


class BusinessQueryExtraction(BaseModel):
    """业务查询信息抽取结果。"""

    model_config = ConfigDict(extra="forbid")

    query_type: BusinessQueryType = Field(
        description="用户当前业务查询的具体类型。",
    )

    query_params: BusinessQueryParams = Field(
        default_factory=BusinessQueryParams,
        description="从用户当前消息和历史上下文中提取的查询参数。",
    )

    clarification: str | None = Field(
        default=None,
        description="无法确定查询对象或缺少必要信息时，向用户提出的澄清问题。",
    )

