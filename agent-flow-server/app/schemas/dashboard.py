"""管理员工作台（Dashboard）响应模型。

三个接口的数据结构：
- summary：统计卡 / 审批待办 / 快捷入口计数 / 最近执行记录
- trend：按时间分桶的执行吞吐趋势
- health：系统指标与服务运行状态
"""

from datetime import datetime

from pydantic import BaseModel


class DashboardTaskStats(BaseModel):
    """概览统计四卡（基于 workflow_runs）。"""

    total: int
    completed: int
    running: int
    abnormal: int
    success_rate: float
    # 与上一等长周期相比的百分比变化；上一周期无数据时为 None
    total_delta: float | None = None
    completed_delta: float | None = None
    abnormal_delta: float | None = None
    # 今日新增任务数
    today_total: int
    # 近 24 小时成功任务的平均耗时（毫秒）
    avg_duration_ms: int | None = None


class DashboardApprovalItem(BaseModel):
    """待审批报销单据（工作台仅展示前几条）。"""

    claim_no: str
    title: str
    applicant: str
    category: str | None = None
    status: str
    amount: str
    currency: str
    submitted_at: datetime | None = None


class DashboardApprovalSummary(BaseModel):
    pending_count: int
    processing_count: int
    pending_amount: str
    items: list[DashboardApprovalItem]


class DashboardQuickStats(BaseModel):
    """快捷入口的实时角标计数。"""

    pending_approvals: int
    kb_count: int
    doc_total: int
    doc_processing: int
    doc_failed: int
    user_count: int
    # 解析异常 / 解析中文档最多的知识库 uid（前端快捷入口直达其文档列表）
    failed_kb_uid: str | None = None
    processing_kb_uid: str | None = None


class DashboardRecordItem(BaseModel):
    uid: str
    name: str
    executor: str
    status: str
    started_at: datetime
    duration_ms: int | None = None


class DashboardSummaryResponse(BaseModel):
    tasks: DashboardTaskStats
    approvals: DashboardApprovalSummary
    quick: DashboardQuickStats
    records: list[DashboardRecordItem]
    # 运行记录总数（表格脚注展示）
    records_total: int
    generated_at: datetime


class TrendPoint(BaseModel):
    label: str
    bucket: datetime
    total: int
    success: int
    failed: int


class DashboardTrendResponse(BaseModel):
    range: str
    points: list[TrendPoint]


class HealthComponent(BaseModel):
    key: str
    name: str
    status: str  # ok / degraded / down
    latency_ms: int | None = None
    detail: str | None = None


class WorkerStatusItem(BaseModel):
    key: str
    name: str
    queue: str
    online: bool
    status: str  # online / busy / offline
    queued: int
    capacity: int
    last_active_at: datetime | None = None
    detail: str | None = None


class DashboardHealthResponse(BaseModel):
    cpu_percent: float
    memory_used_gb: float
    memory_total_gb: float
    memory_percent: float
    avg_response_ms: int | None
    components: list[HealthComponent]
    workers: list[WorkerStatusItem]
    checked_at: datetime
