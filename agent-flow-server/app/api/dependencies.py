# 依赖注入定义：集中组装 session → repository → engine → service 的依赖链
# 使用方式：路由函数通过 Depends 声明需要的 repository / service 即可
from typing import Annotated
from fastapi import Depends,Request
from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.repository.conversations_repository import ConversationsRepository
from app.repository.dashboard_repository import DashboardRepository
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.repository.expense_pre_review_repository import ExpensePreReviewRepository
from app.services.conversations_service import ConversationMessageService
from app.repository.knowledge_repository import KnowledgeRepository
from app.services.dashboard_service import DashboardService
from app.services.expense_claim_service import ExpenseClaimService
from app.services.expense_pre_review_service import ExpensePreReviewService
from app.services.knowledge_service import KnowledgeService
from app.repository.business_task_repository import BusinessTaskRepository
from app.services.business_task_service import BusinessTaskService

async def get_arq_redis(request: Request) -> ArqRedis:
    return request.app.state.arq_redis

# ---------- Repository ----------

async def get_conversations_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConversationsRepository:
    """
    创建 ConversationsRepository 实例。

    依赖链执行顺序：
        1. get_session() 打开 session 并 yield
        2. 这里拿到 session，创建 Repository
        3. Repository 被 Service 使用，Service 被路由函数使用
        4. 路由函数返回后，get_session() 继续执行，自动关闭 session
    """
    return ConversationsRepository(session=session)

async def get_knowledge_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> KnowledgeRepository:
    return KnowledgeRepository(session=session)

async def get_business_task_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BusinessTaskRepository:
    return BusinessTaskRepository(session=session)


async def get_expense_claim_repository(
        session: Annotated[AsyncSession, Depends(get_session)],
) -> ExpenseClaimRepository:
    return ExpenseClaimRepository(session=session)


async def get_dashboard_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardRepository:
    return DashboardRepository(session=session)


async def get_expense_pre_review_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ExpensePreReviewRepository:

    return ExpensePreReviewRepository(session=session)

# ---------- Engine ----------



# ---------- Service ----------

async def get_conversation_service(
    repository: Annotated[
        ConversationsRepository, Depends(get_conversations_repository)
    ],
    redis: Annotated[ArqRedis, Depends(get_arq_redis)]
) -> ConversationMessageService:
    """创建 ConversationMessageService 实例（注入 repository 与 engine）。"""
    return ConversationMessageService(repository=repository, redis=redis)


async def get_knowledge_service(
    repository: Annotated[KnowledgeRepository, Depends(get_knowledge_repository)],
) -> KnowledgeService:
    return KnowledgeService(repository=repository)

async def get_business_task_service() -> BusinessTaskService:
    """BusinessTaskService 在方法内部自行开启事务 Session，无需注入请求级 session。"""
    return BusinessTaskService()

async def get_expense_pre_review_service(
    repository: Annotated[ExpensePreReviewRepository, Depends(get_expense_pre_review_repository)],
    claim_repository: Annotated[ExpenseClaimRepository, Depends(get_expense_claim_repository)],
    redis: Annotated[ArqRedis, Depends(get_arq_redis)]
) -> ExpensePreReviewService:
    """BusinessTaskService 在方法内部自行开启事务 Session，无需注入请求级 session。"""
    return ExpensePreReviewService(repository=repository,claim_repository=claim_repository,redis=redis)

async def get_expense_claim_service(
    repository: Annotated[ExpenseClaimRepository, Depends(get_expense_claim_repository)],
) -> "ExpenseClaimService":
    """报销单业务服务（查询、统计、审批决策）。"""
    from app.services.expense_claim_service import ExpenseClaimService

    return ExpenseClaimService(repository=repository)


async def get_dashboard_service(
    repository: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    redis: Annotated[ArqRedis, Depends(get_arq_redis)],
) -> DashboardService:
    """管理员工作台聚合服务（数据库统计 + 队列心跳 + 系统指标）。"""
    return DashboardService(repository=repository, redis=redis)