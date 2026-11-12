"""报销记录列表"""

from copy import deepcopy
from typing import Any
from sqlalchemy import select

from app.agent_graph.schemas.business_query import BusinessQueryScope
from app.agent_graph.schemas.intents import BusinessQueryParams
from app.agent_graph.state import AgentState
from app.core import database
from app.models import Conversation
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.services.expense_claim_service import ExpenseClaimService
from app.utils.logger import logger
from app.utils.task_ui import _build_expense_claim_list_payload
from app.utils.time_parser import resolve_time_expression

# 对话内默认每页条数：卡片一次展示 7 条，剩余的分页信息写进 answer
DEFAULT_PAGE_SIZE = 7


async def handle_expense_list(state: AgentState) -> dict[str, Any]:
    """查询当前登录用户的报销单列表。"""

    # 1. 基础上下文校验
    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")
    user_role = state.get("user_role")

    if user_id is None:
        logger.error("业务查询失败：AgentState 中缺少 user_id")
        return {
            "answer": "无法获取当前用户身份，请重新登录后再试。"
        }

    # 2. 解析和校验查询参数
    raw_params = state.get("query_params") or {}
    if isinstance(raw_params, dict):
        params = BusinessQueryParams.model_validate(raw_params)
    elif isinstance(raw_params, BusinessQueryParams):
        params = raw_params
    else:
        raise ValueError(
            f"不支持的业务查询参数类型：{type(raw_params).__name__}"
        )
    try:

        time_range = resolve_time_expression(params.time_expression)

        if not time_range.recognized:
            return {
                "answer": (
                    f"暂时无法识别时间范围「{params.time_expression}」。"
                    "请尝试使用今天、昨天、本周、上周、本月、上个月、"
                    "今年、去年、最近、最近7天或具体年月等表达。"
                )
            }

    except Exception:
        logger.exception("业务查询参数校验失败")
        return {
            "answer": "我没有正确理解你的查询条件，请换一种方式描述。"
        }
    # 4. 执行业务逻辑
    try:
        async with database.async_session() as session:
            repository = ExpenseClaimRepository(session)
            service = ExpenseClaimService(repository)
            target_user_id = None
            # 3. 根据当前用户角色校验查询范围
            if params.scope == BusinessQueryScope.SELF:
                # 所有角色都可以查询自己的报销记录
                target_user_id = user_id

            elif params.scope == BusinessQueryScope.ALL:
                if user_role != "admin":
                    logger.warning(
                        "普通用户尝试查询全局报销数据，user_id=%s",
                        user_id,
                    )
                    return {
                        "answer": "抱歉，你没有权限查询企业全局报销记录。"
                    }

            elif params.scope == BusinessQueryScope.USER:
                if user_role != "admin":
                    return {
                        "answer": "抱歉，你没有权限查询其他员工的报销记录。"
                    }

                if not params.target_user_name:
                    return {
                        "answer": "请告诉我需要查询哪位员工的报销记录。"
                    }
                try:
                    target_user = await service.resolve_target_user(
                        params.target_user_name
                    )
                except ValueError as exc:
                    return {
                        "answer": str(exc)
                    }

                target_user_id = target_user.id

            requested_page = params.page or 1
            page_size = params.page_size or DEFAULT_PAGE_SIZE

            # 防止异常分页参数
            if requested_page < 1:
                requested_page = 1

            if page_size < 1:
                page_size = DEFAULT_PAGE_SIZE

            # 4.1 第一次查询
            async def query_claims(page: int) -> dict[str, Any]:
                """根据已校验的查询范围执行报销列表查询。"""

                query_kwargs = {
                    "statuses": params.statuses,
                    "date_from": time_range.date_from,
                    "date_to": time_range.date_to,
                    "expense_category": params.expense_category,
                    "page": page,
                    "page_size": page_size,
                }

                if params.scope == BusinessQueryScope.ALL:
                    return await service.list_all_claims(
                        user_role=user_role,
                        **query_kwargs,
                    )

                return await service.list_my_claims(
                    user_id=target_user_id,
                    **query_kwargs,
                )

            result = await query_claims(requested_page)
            total = result.get("total", 0)
            page = result.get("page", requested_page)
            page_size = result.get("page_size", page_size)

            # 4.2 计算总页数
            total_pages = (
                (total + page_size - 1) // page_size
                if total > 0 and page_size > 0
                else 0
            )

            # 4.3 分页越界兜底
            max_valid_page = max(total_pages, 1)

            if page > max_valid_page:
                logger.warning(
                    "报销记录分页越界，user_id=%s, scope=%s, "
                    "requested_page=%s, total_pages=%s，将调整到第 %s 页",
                    user_id,
                    params.scope.value,
                    page,
                    total_pages,
                    max_valid_page,
                )

                page = max_valid_page

                # 重新查询时仍然使用原来的查询范围
                result = await query_claims(page)

                total = result.get("total", 0)
                page = result.get("page", page)
                page_size = result.get("page_size", page_size)

                total_pages = (
                    (total + page_size - 1) // page_size
                    if total > 0 and page_size > 0
                    else 0
                )

            # 4.4 构造最新查询参数
            saved_query_params = params.model_dump(
                mode="json",
                exclude_none=True,
            )
            saved_query_params["page"] = page
            saved_query_params["page_size"] = page_size

            # 4.5 更新会话上下文
            conversation_result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )

            conversation = conversation_result.scalar_one_or_none()

            if conversation:
                # 深拷贝，避免 JSON 字段变更追踪问题
                context = deepcopy(conversation.agent_context or {})

                context["business_query"] = {
                    "query_type": "expense_list",
                    "query_params": saved_query_params,
                    "total": total,
                    "total_pages": total_pages,
                }

                conversation.agent_context = context

                await session.commit()

        # 5. 构造前端卡片
        ui_payload = _build_expense_claim_list_payload(result)

        # 6. 没有查询结果
        if total == 0:
            query_conditions = []

            if params.statuses:
                query_conditions.append(
                    f"状态为 {', '.join(params.statuses)}"
                )

            if params.expense_category:
                query_conditions.append(
                    f"费用类别为「{params.expense_category}」"
                )

            if params.time_expression:
                query_conditions.append(
                    f"时间范围是「{params.time_expression}」"
                )

            condition_str = "、".join(query_conditions)

            condition_msg = (
                f"（条件：{condition_str}）"
                if condition_str
                else ""
            )
            if params.scope == BusinessQueryScope.ALL:
                subject = "企业范围内的"

            elif params.scope == BusinessQueryScope.USER:
                subject = f"员工「{params.target_user_name}」的"

            else:
                subject = "你的"

            answer = (
                f"没有找到符合要求的{subject}报销记录{condition_msg}。\n\n"
                "你可以尝试：\n"
                "1. 放宽查询条件，例如不限定时间或类别重新查询；\n"
                "2. 直接对我说『我要报销』，开始发起一笔新的报销申请。"
            )

            return {
                "answer": answer,
                "ui_payload": ui_payload,
            }
        if params.scope == BusinessQueryScope.ALL:
            subject = "企业范围内的"

        elif params.scope == BusinessQueryScope.USER:
            subject = f"员工「{params.target_user_name}」的"

        else:
            subject = "你的"

        # 7. 返回查询结果
        answer = f"已查询到{subject} {total} 条报销记录。"

        if total_pages > 0:
            answer += f"当前显示第 {page}/{total_pages} 页。"

        return {
            "answer": answer,
            "ui_payload": ui_payload,
        }

    except Exception:
        logger.exception(
            "报销单列表查询失败，user_id=%s",
            user_id,
        )

        return {
            "answer": "查询报销单时出现异常，请稍后再试。"
        }