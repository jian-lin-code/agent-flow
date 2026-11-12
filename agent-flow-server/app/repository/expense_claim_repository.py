"""报销单 Repository。"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import Select, func, or_, select
from app.models import ApprovalRecord, ExpenseClaim, User, ExpenseItem
from app.models.expense_pre_review import ExpensePreReview
from app.utils.logger import logger
from app.utils.minio_client import get_expense_minio_storage, thumb_object_name

# 附件预签名链接有效期（分钟）
PREVIEW_URL_EXPIRE_MINUTES = 30


def _attach_preview_urls(claim: ExpenseClaim) -> None:
    """为报销单的全部附件生成 MinIO 预签名下载链接。

    私有 Bucket 无法直接匿名访问，前端通过带签名的临时 URL 展示发票预览；
    动态给 Attachment 实例挂载 preview_url / thumb_url 属性（非数据库字段，不落库）。

    图片附件额外签名一份缩略图：列表页缩略图区域只有 36px，
    若直接加载原图（发票照片常见 2-5MB/张），单页会产生几十 MB 下载并拖慢同期其他接口。
    """
    if not claim.attachments:
        return
    storage = get_expense_minio_storage()
    for attachment in claim.attachments:
        attachment.thumb_url = None
        if not attachment.storage_path:
            attachment.preview_url = None
            continue
        try:
            attachment.preview_url = storage.client.presigned_get_object(
                bucket_name=storage.bucket,
                object_name=attachment.storage_path,
                expires=timedelta(minutes=PREVIEW_URL_EXPIRE_MINUTES),
            )
        except Exception as e:
            logger.error(f"生成附件 {attachment.id} 预签名链接失败: {e}")
            attachment.preview_url = None
            continue

        # 缩略图在附件上传时预生成；历史附件缺失时前端会回退到原图
        if (attachment.content_type or "").startswith("image/"):
            try:
                attachment.thumb_url = storage.client.presigned_get_object(
                    bucket_name=storage.bucket,
                    object_name=thumb_object_name(attachment.storage_path),
                    expires=timedelta(minutes=PREVIEW_URL_EXPIRE_MINUTES),
                )
            except Exception as e:
                logger.error(f"生成附件 {attachment.id} 缩略图链接失败: {e}")
                attachment.thumb_url = None


class ExpenseClaimRepository:
    """负责 ExpenseClaim 表的数据访问。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, *, claim_id: int, applicant_id: int | None = None,
                        for_update: bool = False) -> ExpenseClaim | None:
        """根据报销单 ID 查询，可选申请人过滤和行锁。"""

        # 直接在一行内构建 where 条件（利用 SQLAlchemy 的 where 叠加特性）
        stmt = select(ExpenseClaim).where(
            ExpenseClaim.id == claim_id,
            *([ExpenseClaim.applicant_id == applicant_id] if applicant_id is not None else [])
        )

        if for_update:
            stmt = stmt.with_for_update()

        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_claim_no(self, claim_no: str, *, for_update: bool = False) -> ExpenseClaim | None:
        """根据报销单号（claim_no）查询，可选行锁。"""
        stmt = select(ExpenseClaim).where(ExpenseClaim.claim_no == claim_no)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # ---------- 连表辅助 ----------

    @staticmethod
    def _latest_review_id_subquery() -> Select:
        """构造“每个报销单最新一条预审记录 id”的关联子查询。

        expense_pre_reviews.id 为自增主键，最大 id 即最新记录，
        用于列表/待审批查询时与报销单做 outer join，避免 N+1。
        """
        return (
            select(func.max(ExpensePreReview.id))
            .where(ExpensePreReview.claim_id == ExpenseClaim.id)
            .correlate(ExpenseClaim)
            .scalar_subquery()
        )

    # ---------- 普通用户：我的申请 ----------

    async def list_by_applicant(
            self,
            *,
            applicant_id: int | None,
            status: str | None = None,
            statuses: list[str] | None = None,
            keyword: str | None = None,
            date_from: datetime | None = None,
            date_to: datetime | None = None,
            expense_category: str | None = None,
            page: int = 1,
            page_size: int = 7,
    ) -> tuple[list[tuple[ExpenseClaim, ExpensePreReview | None]], int]:
        """
        分页查询指定申请人的报销单，并关联每张单据最新的 AI 预审记录。

        支持条件：
        - status：单个状态筛选
        - statuses：多个状态筛选，优先级高于 status
        - keyword：模糊匹配报销单号和标题
        - date_from/date_to：提交时间范围，date_to 为开区间上界
        - expense_category：费用类别筛选

        注意：
        - applicant_id 必须由后端传入，不能使用 LLM 提取的用户 ID。
        - 费用类别通过 ExpenseItem 关系过滤，避免 JOIN 导致报销单重复。
        """
        conditions: list[Any] = []

        if applicant_id is not None:
            conditions.append(ExpenseClaim.applicant_id == applicant_id)

        # 状态筛选：多个状态优先于单个状态
        if statuses:
            conditions.append(ExpenseClaim.status.in_(statuses))
        elif status:
            conditions.append(ExpenseClaim.status == status)

        # 单号、标题模糊搜索
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            conditions.append(or_(ExpenseClaim.claim_no.ilike(kw), ExpenseClaim.title.ilike(kw)))

        # 提交时间范围
        if date_from:
            conditions.append(ExpenseClaim.submitted_at >= date_from)
        if date_to:
            conditions.append(ExpenseClaim.submitted_at < date_to)

        # 费用类别筛选
        if expense_category:
            conditions.append(ExpenseClaim.items.any(ExpenseItem.category == expense_category))

        # 查询总数
        total_stmt = select(func.count(ExpenseClaim.id)).where(*conditions)
        total = (await self.session.execute(total_stmt)).scalar_one()

        # 查询报销单及最新 AI 初审记录
        stmt = (
            select(ExpenseClaim, ExpensePreReview)
            .outerjoin(ExpensePreReview, ExpensePreReview.id == self._latest_review_id_subquery())
            .where(*conditions)
            .options(selectinload(ExpenseClaim.items))
            .order_by(ExpenseClaim.submitted_at.desc().nulls_last(), ExpenseClaim.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows], total

    async def find_active_users_by_name(
            self,
            *,
            name: str,
    ) -> list[User]:
        """根据昵称或登录账号查找启用用户。"""
        keyword = name.strip()

        if not keyword:
            return []

        stmt = (
            select(User)
            .where(
                User.is_active.is_(True),
                or_(
                    User.nickname == keyword,
                    User.username == keyword,
                ),
            )
            .order_by(User.id.asc())
            .limit(2)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_applicant_stats(
        self,
        *,
        applicant_id: int | None,
        month_start: datetime,
        exclude_applicant_id: int | None = None,
    ) -> dict[str, Any]:
        """统计单据数量分布与本月累计申请。

        - applicant_id 为 None 时统计全部用户；
        - exclude_applicant_id 用于在统计全部用户时排除本人提交的单据
          （如管理员工作台口径：全局统计但不把管理员自己的申请计入）。
        """

        user_filter = (
            [ExpenseClaim.applicant_id == applicant_id] if applicant_id else []
        )
        if exclude_applicant_id is not None and not applicant_id:
            user_filter.append(ExpenseClaim.applicant_id != exclude_applicant_id)

        rows = (
            await self.session.execute(
                select(ExpenseClaim.status, func.count(ExpenseClaim.id))
                .where(*user_filter)
                .group_by(ExpenseClaim.status)
            )
        ).all()

        month_count, month_amount = (
            await self.session.execute(
                select(
                    func.count(ExpenseClaim.id),
                    func.coalesce(func.sum(ExpenseClaim.total_amount), Decimal("0.00")),
                ).where(
                    *user_filter,
                    ExpenseClaim.submitted_at >= month_start,
                )
            )
        ).one()

        return {
            "status_counts": {status: count for status, count in rows},
            "month_count": month_count,
            "month_amount": month_amount,
        }

    # ---------- 详情 ----------

    async def get_claim_with_applicant(
        self, *, claim_no: str, applicant_id: int | None = None
    ) -> tuple[ExpenseClaim, User] | None:
        """按 claim_no 查询报销单详情并携带申请人信息，加载明细/附件/预审历史。

        applicant_id 传 None 时不做申请人过滤（管理员查看任意单据）。
        """
        conditions = [ExpenseClaim.claim_no == claim_no]
        if applicant_id is not None:
            conditions.append(ExpenseClaim.applicant_id == applicant_id)

        stmt = (
            select(ExpenseClaim, User)
            .outerjoin(User, User.id == ExpenseClaim.applicant_id)
            .where(*conditions)
            .options(
                selectinload(ExpenseClaim.items),
                selectinload(ExpenseClaim.attachments),
                selectinload(ExpenseClaim.pre_reviews),
            )
        )

        row = (await self.session.execute(stmt)).first()
        if row:
            # 详情页（抽屉）需要展示发票预览，同样生成预签名链接
            _attach_preview_urls(row[0])
        return (row[0], row[1]) if row else None

    # ---------- 管理员：待我审批 ----------

    async def list_pending_for_approver(
        self, *, status: str | None = None, keyword: str | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
        page: int = 1, page_size: int = 20,
        exclude_applicant_id: int | None = None,
    ) -> tuple[list[tuple[ExpenseClaim, ExpensePreReview | None, User]], int]:
        """分页查询报销单（status 为 None 时返回全部状态），连表返回最新预审记录与申请人信息。

        keyword 模糊匹配单号 / 标题 / 申请人昵称 / 用户名；date_from/date_to 为提交时间范围。
        exclude_applicant_id 用于过滤审批人自己提交的单据（"待我审批"不含本人的申请）。
        """

        conditions: list[Any] = []
        if exclude_applicant_id is not None:
            conditions.append(ExpenseClaim.applicant_id != exclude_applicant_id)
        if status:
            conditions.append(ExpenseClaim.status == status)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    ExpenseClaim.claim_no.ilike(pattern),
                    ExpenseClaim.title.ilike(pattern),
                    User.nickname.ilike(pattern),
                    User.username.ilike(pattern),
                )
            )
        if date_from:
            conditions.append(ExpenseClaim.submitted_at >= date_from)
        if date_to:
            conditions.append(ExpenseClaim.submitted_at < date_to)

        total = (
            await self.session.execute(
                select(func.count(ExpenseClaim.id)).where(*conditions)
            )
        ).scalar_one()

        stmt = (
            select(ExpenseClaim, ExpensePreReview, User)
            .outerjoin(ExpensePreReview, ExpensePreReview.id == self._latest_review_id_subquery())
            .outerjoin(User, User.id == ExpenseClaim.applicant_id)
            .where(*conditions)
            .options(selectinload(ExpenseClaim.items),selectinload(ExpenseClaim.attachments))
            .order_by(
                ExpenseClaim.submitted_at.desc().nulls_last(),
                ExpenseClaim.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.session.execute(stmt)).all()
        # 待审批列表需要展示发票缩略图：为每单附件生成预签名 URL
        for row in rows:
            _attach_preview_urls(row[0])

        return [(row[0], row[1], row[2]) for row in rows], total

    # ---------- 审批动作 ----------

    async def add_approval_without_commit(self, record: ApprovalRecord) -> ApprovalRecord:
        """在当前事务中写入一条审批记录（不 commit）。"""
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_latest_review_by_claim_id(self, claim_id: int) -> ExpensePreReview | None:
        """查询报销单最新一条预审记录。"""
        return (
            await self.session.execute(
                select(ExpensePreReview)
                .where(ExpensePreReview.claim_id == claim_id)
                .order_by(ExpensePreReview.created_at.desc(), ExpensePreReview.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get_approvals_with_approver(
        self, *, claim_id: int
    ) -> list[tuple[ApprovalRecord, User | None]]:
        """查询报销单的审批记录，连表带出审批人信息（最新在前）。

        详情抽屉需要展示"人工审核结果 + 审批人附言"，审批人可能已被删除，
        因此用 outer join 并允许 User 为 None。
        """
        stmt = (
            select(ApprovalRecord, User)
            .outerjoin(User, User.id == ApprovalRecord.approver_id)
            .where(ApprovalRecord.claim_id == claim_id)
            .order_by(
                ApprovalRecord.decided_at.desc().nulls_last(),
                ApprovalRecord.id.desc(),
            )
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def get_expense_statistics(
            self,
            *,
            applicant_id: int | None,
            start_at: datetime | None,
            end_at: datetime | None,
    ) -> dict[str, Any]:
        """查询报销统计数据。

        applicant_id=None 表示不限制申请人，由调用方根据角色决定。
        时间条件基于 ExpenseClaim.submitted_at，金额按币种分组避免直接相加。
        """
        filters = [
            cond for cond in (
                ExpenseClaim.applicant_id == applicant_id if applicant_id is not None else None,
                ExpenseClaim.submitted_at.is_not(None),
                ExpenseClaim.submitted_at >= start_at if start_at is not None else None,
                ExpenseClaim.submitted_at < end_at if end_at is not None else None,
            )
            if cond is not None
        ]

        # 1. 按币种统计：单量、总金额、平均金额
        currency_rows = (await self.session.execute(
            select(
                ExpenseClaim.currency,
                func.count(ExpenseClaim.id).label("claim_count"),
                func.coalesce(func.sum(ExpenseClaim.total_amount), Decimal("0.00")).label("total_amount"),
                func.coalesce(func.avg(ExpenseClaim.total_amount), Decimal("0.00")).label("average_amount"),
            ).where(*filters).group_by(ExpenseClaim.currency).order_by(ExpenseClaim.currency)
        )).all()

        # 2. 按状态统计分布
        status_rows = (await self.session.execute(
            select(
                ExpenseClaim.status,
                func.count(ExpenseClaim.id).label("claim_count"),
            ).where(*filters).group_by(ExpenseClaim.status).order_by(ExpenseClaim.status)
        )).all()

        # 3. 按类别+币种统计明细
        category_rows = (await self.session.execute(
            select(
                ExpenseItem.category,
                ExpenseClaim.currency,
                func.count(ExpenseItem.id).label("item_count"),
                func.coalesce(func.sum(ExpenseItem.amount), Decimal("0.00")).label("total_amount"),
            ).join(
                ExpenseClaim, ExpenseClaim.id == ExpenseItem.claim_id
            ).where(*filters).group_by(
                ExpenseItem.category, ExpenseClaim.currency
            ).order_by(
                ExpenseItem.category, ExpenseClaim.currency
            )
        )).all()

        return {
            "currency_statistics": [
                {
                    "currency": r.currency, "claim_count": r.claim_count,
                    "total_amount": r.total_amount, "average_amount": r.average_amount,
                } for r in currency_rows
            ],
            "status_counts": {r.status: r.claim_count for r in status_rows},
            "category_statistics": [
                {
                    "category": r.category, "currency": r.currency,
                    "item_count": r.item_count, "total_amount": r.total_amount,
                } for r in category_rows
            ],
        }



    async def commit(self) -> None:
        """提交当前事务。"""
        await self.session.commit()

    async def rollback(self) -> None:
        """回滚当前事务。"""
        await self.session.rollback()



