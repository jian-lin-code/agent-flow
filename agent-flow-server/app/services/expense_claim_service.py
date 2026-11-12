"""报销单业务服务。

负责普通用户「我的申请」与管理员「待我审批」两条业务线：
列表查询（连表最新 AI 预审）、统计、详情、审批决策。
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core.exceptions import BizException, ErrorCode
from app.models.approval import ApprovalRecord
from app.models.expense_claim import ExpenseClaim, ExpenseClaimStatus
from app.models.expense_pre_review import ExpensePreReview
from app.models.user import User
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.schemas.approval import ApprovalDecision
from app.utils.datetime_helper import utc_now

# 统计口径：进行中 / 已完成 / 异常。
# 进行中包含 needs_info（被退回待补充材料，仍属未结流程）。
IN_PROGRESS_STATUSES = {
    ExpenseClaimStatus.PENDING_APPROVAL.value,
    ExpenseClaimStatus.NEEDS_INFO.value,
    ExpenseClaimStatus.PROCESSING.value,
}
COMPLETED_STATUSES = {
    ExpenseClaimStatus.APPROVED.value,
    ExpenseClaimStatus.COMPLETED.value,
}
ABNORMAL_STATUSES = {
    ExpenseClaimStatus.REJECTED.value,
    ExpenseClaimStatus.FAILED.value,
}

ADMIN_ROLE = "admin"

# 预留：后续若新增专用"审批账号"权限（如 role="approver"），把该角色加入此集合，
# 该角色的待审批列表 / 全局统计将不再排除本人提交的单据（可见全部用户的审批单）。
# 当前集合为空：管理员默认只审批他人的单据，自己的申请走"我的报销"页。
VIEW_ALL_CLAIM_ROLES: set[str] = set()


class ExpenseClaimService:
    """报销单业务服务。"""

    def __init__(self, repository: ExpenseClaimRepository):
        self.repository = repository

    # ---------- 序列化 ----------

    @staticmethod
    def _serialize_review(review: ExpensePreReview | None) -> dict | None:
        """序列化预审记录；列表场景传轻量字段，详情场景自动补全。"""
        if review is None:
            return None
        return {
            "uid": review.uid,
            "status": review.status,
            "result": review.result,
            "risk_level": review.risk_level,
            "summary": review.summary,
            "result_data": review.result_data or {},
            "model_name": review.model_name,
            "prompt_version": review.prompt_version,
            "started_at": review.started_at,
            "finished_at": review.finished_at,
            "error_message": review.error_message,
            "created_at": review.created_at,
            "updated_at": review.updated_at,
        }

    @staticmethod
    def _serialize_claim(
        claim: ExpenseClaim,
        review: ExpensePreReview | None = None,
        applicant: User | None = None,
        include_attachments: bool = False,
    ) -> dict:
        """序列化报销单基础信息。"""
        items = list(claim.items or [])
        data = {
            "id": claim.id,
            "claim_no": claim.claim_no,
            "title": claim.title,
            "description": claim.description,
            "status": claim.status,
            "total_amount": str(claim.total_amount),
            "currency": claim.currency,
            "item_count": len(items),
            "categories": sorted({item.category for item in items}),
            # 费用明细描述（列表「描述」列展示用，去空值）
            "descriptions": [item.description for item in items if item.description],
            "submitted_at": claim.submitted_at,
            "created_at": claim.created_at,
            "updated_at": claim.updated_at,
            "pre_review": ExpenseClaimService._serialize_review(review),
        }

        if applicant is not None:
            data["applicant"] = {
                "id": applicant.id,
                "uid": applicant.uid,
                "username": applicant.username,
                "nickname": applicant.nickname,
            }

        if include_attachments:
            data["attachments"] = [
                {
                    "id": attachment.id,
                    "expense_item_id": attachment.expense_item_id,
                    "original_filename": attachment.original_filename,
                    "content_type": attachment.content_type,
                    "file_size": attachment.file_size,
                    "created_at": attachment.created_at,
                    # MinIO 私有 Bucket 的预签名临时链接（repository 层生成，30 分钟有效）
                    "preview_url": getattr(attachment, "preview_url", None),
                    # 图片缩略图预签名链接（原图可能数 MB，列表页只用缩略图）
                    "thumb_url": getattr(attachment, "thumb_url", None),
                }
                for attachment in (claim.attachments or [])
            ]
            data["items"] = [
                {
                    "id": item.id,
                    "category": item.category,
                    "description": item.description,
                    "amount": str(item.amount),
                    "expense_date": item.expense_date,
                }
                for item in items
            ]

        return data

    @staticmethod
    def _month_start_utc() -> datetime:
        """以上海时区计算本月 1 号 0 点，并转换为 UTC 参与数据库比较。"""
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return month_start.astimezone(timezone.utc)

    @staticmethod
    def _date_range_utc(
            date_from: date | datetime | None,
            date_to: date | datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        """
        将日期范围转换为 UTC 时间范围。

        规则：
        - 按 Asia/Shanghai 时区解释日期。
        - date_from 包含当天，从当天 00:00 开始。
        - date_to 包含当天，结束边界为次日 00:00（开区间）。
        - aware datetime 先转换到上海时区，再取自然日。
        - naive datetime 视为上海本地时间。
        """
        tz = ZoneInfo("Asia/Shanghai")

        def get_local_date(value: date | datetime) -> date:
            if isinstance(value, datetime):
                return (value.astimezone(tz) if value.tzinfo else value).date()
            return value

        start_utc = end_utc = None

        if date_from is not None:
            start_utc = datetime.combine(get_local_date(date_from), time.min, tzinfo=tz).astimezone(timezone.utc)

        if date_to is not None:
            end_date = get_local_date(date_to) + timedelta(days=1)
            end_utc = datetime.combine(end_date, time.min, tzinfo=tz).astimezone(timezone.utc)

        return start_utc, end_utc

    # ---------- 普通用户：我的申请 ----------

    async def list_my_claims(
        self,
        *,
        user_id: int,
        status: str | None = None,
        statuses: list[str] | None = None,
        keyword: str | None = None,
        date_from: date | datetime | None = None,
        date_to: date | datetime | None = None,
        expense_category: str | None = None,
        page: int = 1,
        page_size: int = 7,
    ) -> dict:
        """分页查询当前用户的报销单列表（连表最新预审）。

        日期参数按上海时区自然日解析，date_to 含当天。
        """
        date_from, date_to = self._date_range_utc(date_from, date_to)
        rows, total = await self.repository.list_by_applicant(
            applicant_id=user_id, status=status, statuses=statuses, keyword=keyword,
            date_from=date_from, date_to=date_to, expense_category=expense_category,
            page=page, page_size=page_size,
        )
        return {
            "items": [
                self._serialize_claim(claim, review)
                for claim, review in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def list_all_claims(
            self,
            *,
            user_role: str,
            statuses: list[str] | None = None,
            date_from: date | datetime | None = None,
            date_to: date | datetime | None = None,
            expense_category: str | None = None,
            page: int = 1,
            page_size: int = 20,
    ) -> dict:
        """管理员分页查询企业范围内的报销单。"""

        if user_role != ADMIN_ROLE:
            raise BizException(
                "仅管理员可以查询企业范围内的报销单。",
                code=ErrorCode.FORBIDDEN,
            )

        date_from, date_to = self._date_range_utc(date_from, date_to)

        rows, total = await self.repository.list_by_applicant(
            applicant_id=None,
            statuses=statuses,
            date_from=date_from,
            date_to=date_to,
            expense_category=expense_category,
            page=page,
            page_size=page_size,
        )

        return {
            "items": [
                self._serialize_claim(claim, review)
                for claim, review in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def resolve_target_user(self, name: str) -> User:
        """根据员工昵称或用户名解析目标用户。"""
        users = await self.repository.find_active_users_by_name(name=name)

        if not users:
            raise ValueError(f"没有找到名为「{name}」的企业员工。")

        if len(users) > 1:
            raise ValueError(
                f"「{name}」匹配到多个员工，请使用登录账号进行精确查询。"
            )

        return users[0]

    async def get_claim_stats(self, *, user: User) -> dict:
        """统计进行中 / 已完成 / 异常单据与本月累计申请。

        普通用户统计自己的单据；admin 统计全部用户的单据但排除本人提交的申请
        （与"待我审批"列表口径一致）。将来 VIEW_ALL_CLAIM_ROLES 中的审批角色
        可看到包含本人单据在内的全部统计。
        """
        if user.role in VIEW_ALL_CLAIM_ROLES:
            # 预留：专用审批账号 → 全量统计，不排除本人
            applicant_id, exclude_applicant_id = None, None
        elif user.role == ADMIN_ROLE:
            applicant_id, exclude_applicant_id = None, user.id
        else:
            applicant_id, exclude_applicant_id = user.id, None
        stats = await self.repository.get_applicant_stats(
            applicant_id=applicant_id,
            month_start=self._month_start_utc(),
            exclude_applicant_id=exclude_applicant_id,
        )
        status_counts: dict[str, int] = stats["status_counts"]

        def _sum_status(statuses: set[str]) -> int:
            return sum(count for status, count in status_counts.items() if status in statuses)

        month_amount: Decimal = stats["month_amount"]
        return {
            "in_progress": _sum_status(IN_PROGRESS_STATUSES),
            "completed": _sum_status(COMPLETED_STATUSES),
            "abnormal": _sum_status(ABNORMAL_STATUSES),
            "month_count": stats["month_count"],
            "month_amount": str(month_amount.quantize(Decimal("0.01"))),
            # 各状态原始分布 + 总数，供前端筛选 Tab 的数量徽标使用。
            "status_counts": status_counts,
            "total": sum(status_counts.values()),
        }

    async def get_claim_detail(self, *, user: User, claim_no: str) -> dict:
        """查询报销单详情（按 claim_no 定位）。

        普通用户只能查看自己的单据；admin 可查看任意单据。
        """
        applicant_id = None if user.role == ADMIN_ROLE else user.id
        row = await self.repository.get_claim_with_applicant(
            claim_no=claim_no, applicant_id=applicant_id
        )
        if row is None:
            raise BizException("报销单不存在，或无权查看该报销单。", code=ErrorCode.NOT_FOUND)

        claim, applicant = row
        # pre_reviews 关系按 created_at 倒序排列，第一条即最新。
        latest_review = (claim.pre_reviews or [None])[0]
        data = self._serialize_claim(
            claim, latest_review, applicant=applicant, include_attachments=True
        )
        # 人工审批记录：申请人需要在抽屉里看到审批结论与审批人附言（驳回原因）。
        approvals = await self.repository.get_approvals_with_approver(claim_id=claim.id)
        data["approvals"] = [
            {
                "id": record.id,
                "status": record.status,
                "comment": record.comment,
                "decided_at": record.decided_at,
                "created_at": record.created_at,
                "approver": (
                    {
                        "id": approver.id,
                        "username": approver.username,
                        "nickname": approver.nickname,
                    }
                    if approver is not None
                    else None
                ),
            }
            for record, approver in approvals
        ]
        return data

    # ---------- 管理员：待我审批 ----------

    def _ensure_admin(self, user: User) -> None:
        if user.role != ADMIN_ROLE:
            raise BizException("仅管理员可以执行该操作。", code=ErrorCode.FORBIDDEN)

    async def list_pending_approvals(
        self, *, user: User, status: str | None = None,
        keyword: str | None = None,
        date_from: datetime | None = None, date_to: datetime | None = None,
        page: int = 1, page_size: int = 20
    ) -> dict:
        """分页查询报销单列表（默认全部状态，支持状态/关键词/日期过滤；连表最新预审与申请人信息）。

        默认排除审批人自己提交的单据；进入 VIEW_ALL_CLAIM_ROLES 的角色（预留的
        专用审批账号）可见全部用户的审批单。
        """
        self._ensure_admin(user)
        date_from, date_to = self._date_range_utc(date_from, date_to)
        rows, total = await self.repository.list_pending_for_approver(
            status=status, keyword=keyword, date_from=date_from, date_to=date_to,
            page=page, page_size=page_size,
            # 预留审批账号权限：该集合内的角色不过滤本人单据
            exclude_applicant_id=None if user.role in VIEW_ALL_CLAIM_ROLES else user.id,
        )
        return {
            "items": [
                # 待审批列表需要展示发票缩略图，序列化时带上附件（含预签名 preview_url）
                self._serialize_claim(claim, review, applicant=applicant, include_attachments=True)
                for claim, review, applicant in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def decide_approval(
        self,
        *,
        user: User,
        claim_no: str,
        decision: str,
        comment: str | None = None,
    ) -> dict:
        """审批决策（按 claim_no 定位单据）：写入审批记录并流转报销单状态。

        - 仅 admin 可操作；
        - 只有 pending_approval 状态的单据可审批；
        - 通过 → approved，驳回 → rejected；
        - 行锁防并发重复审批。
        """
        self._ensure_admin(user)

        claim = await self.repository.get_by_claim_no(claim_no, for_update=True)
        if claim is None:
            raise BizException("报销单不存在。", code=ErrorCode.NOT_FOUND)

        if claim.status != ExpenseClaimStatus.PENDING_APPROVAL.value:
            raise BizException(
                f"当前报销单状态为 {claim.status}，不允许审批。",
                code=ErrorCode.CONFLICT,
            )

        # AI 预审已拦截（completed + fail）的单据无需人工复审，服务端同样拒绝审批。
        latest_review = await self.repository.get_latest_review_by_claim_id(claim.id)
        if (
            latest_review is not None
            and latest_review.status == "completed"
            and latest_review.result == "fail"
        ):
            raise BizException(
                "AI 预审已拦截该单据，无需人工复审。",
                code=ErrorCode.CONFLICT,
            )

        if decision == ApprovalDecision.APPROVED.value:
            new_status = ExpenseClaimStatus.APPROVED.value
        else:
            new_status = ExpenseClaimStatus.REJECTED.value

        record = ApprovalRecord(
            claim_id=claim.id,
            approver_id=user.id,
            status=new_status,
            comment=(comment or None),
            decided_at=utc_now(),
        )

        try:
            await self.repository.add_approval_without_commit(record)
            claim.status = new_status
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        latest_review = await self.repository.get_latest_review_by_claim_id(claim.id)
        return {
            "id": claim.id,
            "claim_no": claim.claim_no,
            "status": claim.status,
            "approval_record": {
                "id": record.id,
                "approver_id": record.approver_id,
                "status": record.status,
                "comment": record.comment,
                "decided_at": record.decided_at,
            },
            "pre_review": self._serialize_review(latest_review),
        }

    async def get_expense_statistics(
            self,
            *,
            user: User,
            date_from: date | datetime | None = None,
            date_to: date | datetime | None = None,
    ) -> dict:
        """查询 Agent 使用的报销统计数据。"""

        # 普通用户只能统计自己的报销单；管理员统计全部报销单
        applicant_id = None if user.role == ADMIN_ROLE else user.id

        # 复用日期转换方法
        start_at, end_at = self._date_range_utc(date_from, date_to)

        result = await self.repository.get_expense_statistics(
            applicant_id=applicant_id,
            start_at=start_at,
            end_at=end_at,
        )

        # 精简格式化逻辑，统一转 Decimal 保留两位小数
        def _fmt(val) -> str:
            return str(Decimal(str(val or 0)).quantize(Decimal("0.01")))

        currency_stats = [
            {
                "currency": item["currency"],
                "claim_count": item["claim_count"],
                "total_amount": _fmt(item["total_amount"]),
                "average_amount": _fmt(item["average_amount"]),
            } for item in result["currency_statistics"]
        ]

        category_stats = [
            {
                "category": item["category"],
                "currency": item["currency"],
                "item_count": item["item_count"],
                "total_amount": _fmt(item["total_amount"]),
            } for item in result["category_statistics"]
        ]

        status_counts = result["status_counts"]

        return {
            "total": sum(status_counts.values()),
            "status_counts": status_counts,
            "currency_statistics": currency_stats,
            "category_statistics": category_stats,
            "date_from": date_from,
            "date_to": date_to,
        }
