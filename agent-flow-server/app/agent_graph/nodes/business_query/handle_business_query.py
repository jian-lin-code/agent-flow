"""业务查询意图处理。"""

import re
from typing import Any
from unittest import result

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent_graph import state
from app.agent_graph.history import build_history_messages
from app.agent_graph.prompt_manager import render_prompt
from app.agent_graph.schemas.business_query import (
    BusinessQueryType,
    BusinessQueryExtraction,
    BusinessQueryParams,
    BusinessQueryScope,
)
from app.agent_graph.state import AgentState
from app.agent_graph.token_usage import create_usage_callback, get_token_usage, accumulate_token_usage
from app.utils.datetime_helper import get_beijing_now_str
from app.utils.llm import get_llm_model
from app.utils.logger import logger


# 支持的分页表达
PAGINATION_PHRASES = {
    "下一页",
    "下一张",
    "上一页",
    "上一张",
}

# 中文数字页码
CHINESE_PAGES = {
    "第一页": 1,
    "第二页": 2,
    "第三页": 3,
    "第四页": 4,
    "第五页": 5,
    "第六页": 6,
    "第七页": 7,
    "第八页": 8,
    "第九页": 9,
    "第十页": 10,
}


def _is_explicit_pagination(message: str) -> bool:
    """判断用户是否明确发起分页操作。"""

    message = message.strip()

    if not message:
        return False

    if any(phrase in message for phrase in PAGINATION_PHRASES):
        return True

    # 支持：第 2 页、第10页
    return bool(
        re.fullmatch(
            r"第\s*[0-9一二三四五六七八九十百]+\s*页",
            message,
        )
    )


def _get_pagination_page(
    message: str,
    current_page: int,
) -> int | None:
    """从用户消息中识别分页操作，返回目标页码。"""

    message = message.strip()

    if not message:
        return None

    if "下一页" in message or "下一张" in message:
        return current_page + 1

    if "上一页" in message or "上一张" in message:
        return max(1, current_page - 1)

    # 阿拉伯数字页码
    match = re.fullmatch(
        r"第\s*(\d+)\s*页",
        message,
    )

    if match:
        page = int(match.group(1))
        return page if page >= 1 else None

    # 中文数字页码
    for expression, page in CHINESE_PAGES.items():
        if message == expression:
            return page

    return None


def _get_previous_business_query(
    agent_context: dict[str, Any],
) -> dict[str, Any] | None:
    """获取上一轮业务查询记录。"""

    previous_query = agent_context.get("business_query")

    if not isinstance(previous_query, dict):
        return None

    return previous_query


# 明确指向「本人单据」的表达
SELF_REFERENCE_PATTERN = re.compile(r"我的|我(?:有哪些|有多少|提交的|报销的|这边的|自己的)|本人")

# 口语里的「待审批」，对应本人 pending_approval 状态的单据
PENDING_APPROVAL_PATTERN = re.compile(r"待审批|待审核|待处理|还没审批|未审批|没有审批")

# 状态中文表达 → 数据库状态码
STATUS_ALIASES = {
    "待审批": "pending_approval",
    "待审核": "pending_approval",
    "审批中": "pending_approval",
    "处理中": "processing",
    "已通过": "approved",
    "通过": "approved",
    "已批准": "approved",
    "已驳回": "rejected",
    "驳回": "rejected",
    "被驳回": "rejected",
    "被拒绝": "rejected",
    "草稿": "draft",
    "待补充": "needs_info",
    "已完成": "completed",
    "已完成报销": "completed",
    "失败": "failed",
    "异常": "failed",
}
VALID_STATUSES = {
    "draft", "needs_info", "pending_approval", "processing",
    "approved", "rejected", "completed", "failed",
}


def _normalize_statuses(statuses: list[str] | None) -> list[str] | None:
    """把模型可能返回的中文状态值归一化成数据库状态码。"""
    if not statuses:
        return None

    normalized: list[str] = []

    for status in statuses:
        value = str(status).strip()
        if not value:
            continue
        value = value.lower()
        value = STATUS_ALIASES.get(value, value)
        if value in VALID_STATUSES and value not in normalized:
            normalized.append(value)

    return normalized or None


def _normalize_query_params(
    params: BusinessQueryParams,
    *,
    message: str,
    user_role: str | None,
) -> BusinessQueryParams:
    """纠正模型在查询范围上的误判。

    典型问题：员工问「我有哪些待审批的报销单」时，模型把「待审批」理解成
    管理员视角，抽出 scope=user，导致用户被告知「没有权限查询其他员工」。
    """
    message = message or ""

    # 1. 非管理员只要提到「我的 / 我」，一律按本人数据处理
    if (
        user_role != "admin"
        and params.scope != BusinessQueryScope.SELF
        and SELF_REFERENCE_PATTERN.search(message)
    ):
        logger.info(
            "查询范围纠正：非管理员查询本人单据，scope=%s → self | message=%s",
            params.scope,
            message,
        )
        params.scope = BusinessQueryScope.SELF
        params.target_user_name = None

    # 2. 状态值统一成数据库状态码
    params.statuses = _normalize_statuses(params.statuses)

    # 3. 「待审批」类口语：本人视角默认只看 pending_approval 的单据
    if params.statuses is None and PENDING_APPROVAL_PATTERN.search(message):
        params.statuses = ["pending_approval"]

    return params

async def handle_business_query(
    state: AgentState,
) -> dict[str, Any]:
    """业务查询统一入口。"""

    current_message = (state.get("current_message") or "").strip()
    agent_context = state.get("agent_context") or {}

    # 1. 优先处理上一轮报销列表查询的分页操作
    previous_query = _get_previous_business_query(agent_context)

    if (
        previous_query is not None
        and previous_query.get("query_type")
        == BusinessQueryType.EXPENSE_LIST.value
        and isinstance(previous_query.get("query_params"), dict)
        and _is_explicit_pagination(current_message)
    ):
        previous_params = previous_query["query_params"]

        current_page = previous_params.get("page", 1)

        if (
            not isinstance(current_page, int)
            or isinstance(current_page, bool)
            or current_page < 1
        ):
            current_page = 1

        target_page = _get_pagination_page(
            current_message,
            current_page,
        )

        if target_page is None:
            return {
                "answer": "没有识别出有效的分页操作，请重新尝试。"
            }

        # 用户在第一页请求上一页
        if target_page < 1:
            return {
                "answer": "当前已经是第一页了，没有更早的报销记录。"
            }

        # 2. 校验分页边界
        total_pages = previous_query.get("total_pages")

        if (
            isinstance(total_pages, int)
            and not isinstance(total_pages, bool)
        ):
            if total_pages <= 0:
                return {
                    "answer": "当前查询没有找到报销记录，无需翻页。"
                }

            if target_page > total_pages:
                return {
                    "answer": (
                        f"已经是最后一页了，当前共有 "
                        f"{total_pages} 页，没有更多报销记录。"
                    )
                }

        # 3. 继承上一轮查询条件，只修改页码
        query_params = dict(previous_params)
        query_params["page"] = target_page

        return {
            "query_type": BusinessQueryType.EXPENSE_LIST.value,
            "query_params": query_params,
        }

    # 4. 非分页操作，调用 LLM 抽取查询类型和参数
    usage_callback = create_usage_callback()

    llm = get_llm_model(temp=0)

    structured_llm = llm.with_structured_output(
        BusinessQueryExtraction
    )

    system_prompt = render_prompt(
        "business_query/extract_business_query.j2",
        current_date=get_beijing_now_str(),
    )

    messages = [
        SystemMessage(content=system_prompt),
        *build_history_messages(state.get("history") or [], 4),
        HumanMessage(content=current_message),
    ]

    extraction: BusinessQueryExtraction = await structured_llm.ainvoke(messages, config={"callbacks": [usage_callback]}, )

    usage = get_token_usage(usage_callback)

    # 5. 需要澄清时，直接返回澄清问题
    if extraction.clarification:
        return {
            "answer": extraction.clarification,
        }

    # 6. 纠正查询范围 / 状态值（模型容易把员工的「待审批」误判成管理员视角）
    query_params = _normalize_query_params(
        extraction.query_params,
        message=current_message,
        user_role=state.get("user_role"),
    )

    logger.info(
        "业务查询抽取完成 | type=%s | params=%s",
        extraction.query_type.value,
        query_params.model_dump(exclude_none=True),
    )

    # 7. 返回抽取结果
    return {
        "query_type": extraction.query_type.value,
        "query_params": query_params.model_dump(
            exclude_none=True,
        ),
        **accumulate_token_usage(state, usage),
    }