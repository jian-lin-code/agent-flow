"""管理员工作台 API。

仅管理员可访问，一次请求返回工作台所需的全部聚合数据：
- GET /summary：统计卡 / 待审批 / 快捷入口计数 / 最近执行记录
- GET /trend：执行吞吐趋势（1h / 24h / 7d）
- GET /health：CPU、内存、平均响应、数据库/Redis/MinIO 探活、Worker 心跳
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_dashboard_service
from app.core.deps import get_current_user, require_admin
from app.core.response import UnifiedResponseRoute
from app.models import User
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/admin/dashboard",
    tags=["admin-dashboard"],
    route_class=UnifiedResponseRoute,
    dependencies=[Depends(require_admin)],
)


@router.get("/summary", summary="工作台汇总（任务统计 / 待审批 / 快捷入口 / 最近记录）")
async def get_dashboard_summary(
    current_user: Annotated[User, Depends(require_admin)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
):
    return await service.get_summary(admin_user_id=current_user.id)


@router.get("/trend", summary="执行吞吐趋势（1h / 24h / 7d）")
async def get_dashboard_trend(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
    range_key: Annotated[
        str, Query(alias="range", pattern="^(1h|24h|7d)$", description="时间范围")
    ] = "24h",
):
    return await service.get_trend(range_key)


@router.get("/health", summary="系统健康与 Worker 运行状态")
async def get_dashboard_health(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
):
    return await service.get_health()
