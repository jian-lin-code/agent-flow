"""管理员工作台数据聚合 Repository。

数据来源（全部为现有表，不新增表结构）：
- workflow_runs / run_steps：AI 工作流执行的任务量、成功率、趋势、最近记录
- expense_claims / expense_items / users：待审批单据
- documents / knowledge_bases / users：快捷入口计数
"""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Conversation,
    Document,
    ExpenseClaim,
    KnowledgeBase,
    User,
    WorkflowRun,
)
from app.models.expense_claim import ExpenseClaimStatus
from app.models.expense_pre_review import ExpensePreReview
from app.models.knowledge import DocumentStatus
from app.utils.datetime_helper import utc_now

# 任务口径：与前端「总任务 / 已完成 / 实时运行中 / 失败」四卡一一对应。
# running 覆盖等待用户补充、等待确认、等待审批等未终结状态。
RUNNING_STATUSES = {
    "pending",
    "running",
    "waiting_input",
    "waiting_confirmation",
    "waiting_approval",
}
FAILED_STATUSES = {"failed", "cancelled"}

# 统计周期：概览卡与环比均以最近 7 天为当前周期，前 7 天为对比周期
STATS_PERIOD_DAYS = 7

BUSINESS_TZ = ZoneInfo("Asia/Shanghai")

# 服务端时区换算：timestamptz -> 指定时区的 naive 时间，便于按业务日/小时分桶
LOCAL_TS = func.timezone("Asia/Shanghai", WorkflowRun.started_at)


class DashboardRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------- 任务统计 ----------

    async def get_task_stats(self) -> dict[str, Any]:
        """最近 7 天任务状态分布 + 前 7 天环比 + 今日新增 + 近 24h 平均耗时。"""

        now = utc_now()
        current_start = now - timedelta(days=STATS_PERIOD_DAYS)
        previous_start = current_start - timedelta(days=STATS_PERIOD_DAYS)

        async def _count_by_status(start: datetime, end: datetime | None = None) -> dict[str, int]:
            conditions = [WorkflowRun.started_at >= start]
            if end is not None:
                conditions.append(WorkflowRun.started_at < end)
            rows = (
                await self.session.execute(
                    select(WorkflowRun.status, func.count(WorkflowRun.id))
                    .where(*conditions)
                    .group_by(WorkflowRun.status)
                )
            ).all()
            return {status: int(count) for status, count in rows}

        current = await _count_by_status(current_start)
        previous = await _count_by_status(previous_start, current_start)

        def _split(counts: dict[str, int]) -> tuple[int, int, int, int]:
            completed = counts.get("success", 0)
            running = sum(counts.get(s, 0) for s in RUNNING_STATUSES)
            abnormal = sum(counts.get(s, 0) for s in FAILED_STATUSES)
            return sum(counts.values()), completed, running, abnormal

        total, completed, running, abnormal = _split(current)
        prev_total, prev_completed, _, prev_abnormal = _split(previous)

        # 今日（北京时间自然日）新增任务
        today_local_start = datetime.now(BUSINESS_TZ).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_total = (
            await self.session.execute(
                select(func.count(WorkflowRun.id)).where(
                    WorkflowRun.started_at >= today_local_start
                )
            )
        ).scalar_one()

        # 近 24 小时成功任务的平均耗时（毫秒）
        avg_duration_ms = await self.get_avg_duration_ms()

        return {
            "total": total,
            "completed": completed,
            "running": running,
            "abnormal": abnormal,
            "success_rate": round(completed / total * 100, 1) if total else 0.0,
            "total_delta": self._delta(total, prev_total),
            "completed_delta": self._delta(completed, prev_completed),
            "abnormal_delta": self._delta(abnormal, prev_abnormal),
            "today_total": int(today_total),
            "avg_duration_ms": avg_duration_ms,
        }

    async def get_avg_duration_ms(self, hours: int = 24) -> int | None:
        """近 N 小时成功任务的平均耗时（毫秒）。"""
        avg_seconds = (
            await self.session.execute(
                select(
                    func.avg(
                        func.extract("epoch", WorkflowRun.finished_at - WorkflowRun.started_at)
                    )
                ).where(
                    WorkflowRun.status == "success",
                    WorkflowRun.finished_at.is_not(None),
                    WorkflowRun.started_at >= utc_now() - timedelta(hours=hours),
                )
            )
        ).scalar_one()
        return int(avg_seconds * 1000) if avg_seconds is not None else None

    @staticmethod
    def _delta(current: int, previous: int) -> float | None:
        """环比百分比；上一周期为 0 时无法计算，返回 None 由前端隐藏。"""
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    # ---------- 待审批 ----------

    async def get_approval_summary(
        self, limit: int = 3, exclude_applicant_id: int | None = None
    ) -> dict[str, Any]:
        """工作台待审批汇总；exclude_applicant_id 用于排除管理员本人提交的单据。"""
        self_filter = (
            [ExpenseClaim.applicant_id != exclude_applicant_id]
            if exclude_applicant_id is not None
            else []
        )
        status_rows = (
            await self.session.execute(
                select(ExpenseClaim.status, func.count(ExpenseClaim.id))
                .where(*self_filter)
                .group_by(
                    ExpenseClaim.status
                )
            )
        ).all()
        counts = {status: int(count) for status, count in status_rows}

        pending_total = counts.get(ExpenseClaimStatus.PENDING_APPROVAL.value, 0)
        pending_amount = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(ExpenseClaim.total_amount), Decimal("0.00"))
                ).where(
                    *self_filter,
                    ExpenseClaim.status == ExpenseClaimStatus.PENDING_APPROVAL.value
                )
            )
        ).scalar_one()

        stmt = (
            select(ExpenseClaim, User)
            .outerjoin(User, User.id == ExpenseClaim.applicant_id)
            .where(
                *self_filter,
                ExpenseClaim.status == ExpenseClaimStatus.PENDING_APPROVAL.value
            )
            .options(selectinload(ExpenseClaim.items))
            .order_by(
                ExpenseClaim.submitted_at.desc().nulls_last(),
                ExpenseClaim.id.desc(),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()

        items = [
            {
                "claim_no": claim.claim_no,
                "title": claim.title,
                "applicant": (user.nickname or user.username) if user else "—",
                "category": claim.items[0].category if claim.items else None,
                "status": claim.status,
                "amount": str(Decimal(claim.total_amount).quantize(Decimal("0.01"))),
                "currency": claim.currency or "CNY",
                "submitted_at": claim.submitted_at,
            }
            for claim, user in rows
        ]

        return {
            "pending_count": pending_total,
            "processing_count": counts.get(ExpenseClaimStatus.PROCESSING.value, 0),
            "pending_amount": str(Decimal(pending_amount).quantize(Decimal("0.01"))),
            "items": items,
        }

    # ---------- 快捷入口计数 ----------

    async def get_quick_stats(
        self, exclude_applicant_id: int | None = None
    ) -> dict[str, int | str | None]:
        """快捷入口实时角标；exclude_applicant_id 用于待审批计数排除管理员本人单据。

        同时返回解析异常 / 解析中文档数量最多的知识库 uid，供前端快捷入口直达对应文档列表。
        """
        kb_count = (
            await self.session.execute(select(func.count(KnowledgeBase.id)))
        ).scalar_one()
        doc_rows = (
            await self.session.execute(
                select(Document.status, func.count(Document.id)).group_by(Document.status)
            )
        ).all()
        doc_counts = {status: int(count) for status, count in doc_rows}
        user_count = (
            await self.session.execute(select(func.count(User.id)))
        ).scalar_one()
        pending_approvals = (
            await self.session.execute(
                select(func.count(ExpenseClaim.id)).where(
                    *(
                        [ExpenseClaim.applicant_id != exclude_applicant_id]
                        if exclude_applicant_id is not None
                        else []
                    ),
                    ExpenseClaim.status == ExpenseClaimStatus.PENDING_APPROVAL.value
                )
            )
        ).scalar_one()

        processing = sum(
            count
            for status, count in doc_counts.items()
            if status not in (DocumentStatus.INDEXED, DocumentStatus.FAILED)
        )

        async def _top_kb_uid_by_status(status: DocumentStatus) -> str | None:
            """返回该状态下文档最多的知识库 uid（无文档时为 None）。"""
            row = (
                await self.session.execute(
                    select(KnowledgeBase.uid, func.count(Document.id))
                    .join(Document, Document.knowledge_base_id == KnowledgeBase.id)
                    .where(Document.status == status.value)
                    .group_by(KnowledgeBase.uid)
                    .order_by(func.count(Document.id).desc())
                    .limit(1)
                )
            ).first()
            return row[0] if row else None

        failed_kb_uid = await _top_kb_uid_by_status(DocumentStatus.FAILED)
        processing_kb_uid = (
            None
            if processing == 0
            else await self._top_kb_uid_by_processing()
        )
        return {
            "pending_approvals": int(pending_approvals),
            "kb_count": int(kb_count),
            "doc_total": sum(doc_counts.values()),
            "doc_processing": processing,
            "doc_failed": doc_counts.get(DocumentStatus.FAILED, 0),
            "user_count": int(user_count),
            "failed_kb_uid": failed_kb_uid,
            "processing_kb_uid": processing_kb_uid,
        }

    async def _top_kb_uid_by_processing(self) -> str | None:
        """解析中文档最多的知识库 uid（状态为 processing/parsing 等非终态）。"""
        row = (
            await self.session.execute(
                select(KnowledgeBase.uid, func.count(Document.id))
                .join(Document, Document.knowledge_base_id == KnowledgeBase.id)
                .where(
                    Document.status.not_in(
                        (DocumentStatus.INDEXED, DocumentStatus.FAILED)
                    )
                )
                .group_by(KnowledgeBase.uid)
                .order_by(func.count(Document.id).desc())
                .limit(1)
            )
        ).first()
        return row[0] if row else None

    # ---------- 最近执行记录 ----------

    async def get_recent_runs(self, limit: int = 8) -> tuple[list[dict[str, Any]], int]:
        total = (
            await self.session.execute(select(func.count(WorkflowRun.id)))
        ).scalar_one()

        stmt = (
            select(WorkflowRun, User, Conversation.title)
            .outerjoin(User, User.id == WorkflowRun.triggered_by)
            .outerjoin(Conversation, Conversation.id == WorkflowRun.conversation_id)
            .order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()

        records = []
        for run, user, conversation_title in rows:
            duration_ms = None
            if run.finished_at and run.started_at:
                duration_ms = max(
                    int((run.finished_at - run.started_at).total_seconds() * 1000), 0
                )
            records.append(
                {
                    "uid": run.uid,
                    "name": conversation_title or f"工作流 {run.uid[:8]}",
                    "executor": (user.nickname or user.username) if user else "系统",
                    "status": run.status,
                    "started_at": run.started_at,
                    "duration_ms": duration_ms,
                }
            )
        return records, int(total)

    # ---------- 趋势 ----------

    async def get_hourly_trend(self, start: datetime) -> dict[str, dict[str, int]]:
        """按北京时间小时分桶聚合（24h 视图）。"""
        bucket = func.date_trunc("hour", LOCAL_TS).label("bucket")
        rows = (
            await self.session.execute(
                select(
                    bucket,
                    func.count(WorkflowRun.id),
                    func.count(WorkflowRun.id).filter(WorkflowRun.status == "success"),
                    func.count(WorkflowRun.id).filter(
                        WorkflowRun.status.in_(FAILED_STATUSES)
                    ),
                )
                .where(WorkflowRun.started_at >= start)
                .group_by(bucket)
            )
        ).all()
        return {
            row[0].strftime("%Y-%m-%d %H:%M"): {
                "total": int(row[1]),
                "success": int(row[2]),
                "failed": int(row[3]),
            }
            for row in rows
        }

    async def get_daily_trend(self, start: datetime) -> dict[str, dict[str, int]]:
        """按北京时间自然日分桶聚合（7d 视图）。"""
        bucket = func.date_trunc("day", LOCAL_TS).label("bucket")
        rows = (
            await self.session.execute(
                select(
                    bucket,
                    func.count(WorkflowRun.id),
                    func.count(WorkflowRun.id).filter(WorkflowRun.status == "success"),
                    func.count(WorkflowRun.id).filter(
                        WorkflowRun.status.in_(FAILED_STATUSES)
                    ),
                )
                .where(WorkflowRun.started_at >= start)
                .group_by(bucket)
            )
        ).all()
        return {
            row[0].strftime("%Y-%m-%d"): {
                "total": int(row[1]),
                "success": int(row[2]),
                "failed": int(row[3]),
            }
            for row in rows
        }

    async def get_raw_runs(self, start: datetime) -> list[tuple[datetime, str]]:
        """1 小时视图数据量很小，直接取原始时间戳在内存分桶（5 分钟粒度）。"""
        rows = (
            await self.session.execute(
                select(WorkflowRun.started_at, WorkflowRun.status)
                .where(WorkflowRun.started_at >= start)
                .order_by(WorkflowRun.started_at)
            )
        ).all()
        return [(row[0], row[1]) for row in rows]

    # ---------- 服务最近活动时间 ----------

    async def get_service_last_active(self) -> dict[str, datetime | None]:
        workflow_last = (
            await self.session.execute(select(func.max(WorkflowRun.started_at)))
        ).scalar_one()
        document_last = (
            await self.session.execute(select(func.max(Document.updated_at)))
        ).scalar_one()
        review_last = (
            await self.session.execute(select(func.max(ExpensePreReview.created_at)))
        ).scalar_one()
        return {
            "agent-flow": workflow_last,
            "rag-flow": document_last,
            "expense-review": review_last,
        }
