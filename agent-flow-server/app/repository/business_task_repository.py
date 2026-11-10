
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.business_task import (
    BusinessTask,
    BusinessTaskAttachment,
    BusinessTaskStatus,
    BusinessTaskType,
)
from app.models.expense_claim import ExpenseClaim, ExpenseItem


class BusinessTaskRepository:
    """BusinessTask / BusinessTaskAttachment / ExpenseClaim / ExpenseItem 的数据访问封装。

    报销草稿（BusinessTask）与提交后的正式报销单（ExpenseClaim / ExpenseItem）
    属于同一条业务链路，统一放在这里维护，避免两个 Repository 交叉依赖。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_uid(
        self,
        *,
        task_uid: str,
        user_id: int,
        conversation_id: int,
        task_type: BusinessTaskType | str | None = None,
        status: BusinessTaskStatus | str | None = None,
        for_update: bool = False,
    ) -> BusinessTask | None:
        """根据 UID 查询任务，同时校验用户和会话归属。"""

        stmt = select(BusinessTask).where(
            BusinessTask.uid == task_uid,
            BusinessTask.created_by == user_id,
            BusinessTask.conversation_id == conversation_id,
        )

        if task_type is not None:
            value = (
                task_type.value
                if isinstance(task_type, BusinessTaskType)
                else task_type
            )
            stmt = stmt.where(BusinessTask.task_type == value)

        if status is not None:
            value = (
                status.value
                if isinstance(status, BusinessTaskStatus)
                else status
            )
            stmt = stmt.where(BusinessTask.status == value)

        if for_update:
            stmt = stmt.with_for_update() #with_for_update() 就是查询数据时顺手给这几行加一把锁，别的事务想改或锁同一行就得排队等当前事务结束。

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # 查询指定状态下最近创建的业务任务。
    async def get_latest_by_status(
            self,
            *,
            user_id: int,
            conversation_id: int,
            task_type: BusinessTaskType | str,
            status: BusinessTaskStatus | str,
            for_update: bool = False,
    ) -> BusinessTask | None:
        """查询指定状态下最近创建的业务任务。"""

        task_type_value = (
            task_type.value
            if isinstance(task_type, BusinessTaskType)
            else task_type
        )

        status_value = (
            status.value
            if isinstance(status, BusinessTaskStatus)
            else status
        )

        stmt = (
            select(BusinessTask)
            .where(
                BusinessTask.created_by == user_id,
                BusinessTask.conversation_id == conversation_id,
                BusinessTask.task_type == task_type_value,
                BusinessTask.status == status_value,
            )
            .order_by(
                BusinessTask.created_at.desc(),
                BusinessTask.id.desc(),
            )
            .limit(1)
        )

        if for_update:
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def list_by_status(
        self,
        *,
        user_id: int,
        conversation_id: int,
        task_type: BusinessTaskType | str,
        status: BusinessTaskStatus | str,
        limit: int = 5,
        offset: int = 0,
    ) -> list[BusinessTask]:
        """查询指定状态下的业务任务列表，按创建时间倒序排列。"""

        if limit < 1 or limit > 20:
            raise ValueError("limit 必须在 1 到 20 之间。")

        if offset < 0:
            raise ValueError("offset 不能小于 0。")

        task_type_value = (
            task_type.value
            if isinstance(task_type, BusinessTaskType)
            else task_type
        )

        status_value = (
            status.value
            if isinstance(status, BusinessTaskStatus)
            else status
        )

        stmt = (
            select(BusinessTask)
            .where(
                BusinessTask.created_by == user_id,
                BusinessTask.conversation_id == conversation_id,
                BusinessTask.task_type == task_type_value,
                BusinessTask.status == status_value,
            )
            .order_by(
                BusinessTask.created_at.desc(),
                BusinessTask.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_conversation(
        self,
        *,
        user_id: int,
        conversation_id: int,
        task_type: BusinessTaskType | str | None = None,
        limit: int = 50,
    ) -> list[BusinessTask]:
        """查询某会话下当前用户创建的全部业务任务，最新的排在前面。"""

        if limit < 1 or limit > 100:
            raise ValueError("limit 必须在 1 到 100 之间。")

        stmt = select(BusinessTask).where(
            BusinessTask.created_by == user_id,
            BusinessTask.conversation_id == conversation_id,
        )

        if task_type is not None:
            stmt = stmt.where(
                BusinessTask.task_type
                == (
                    task_type.value
                    if isinstance(task_type, BusinessTaskType)
                    else task_type
                )
            )

        stmt = (
            stmt.order_by(
                BusinessTask.created_at.desc(),
                BusinessTask.id.desc(),
            )
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_without_commit(
        self,
        task: BusinessTask,    ) -> BusinessTask:
        """添加任务并 flush，不提交事务。"""

        self.session.add(task)
        await self.session.flush()
        return task

    async def update(
        self,
        task: BusinessTask,
    ) -> BusinessTask:
        """
        更新已被 Session 跟踪的任务。

        SQLAlchemy 会自动跟踪 ORM 对象的字段变化，
        因此这里不需要重新执行 UPDATE SQL。
        """

        await self.session.flush()
        return task

    async def get_by_id(
        self,
        *,
        task_id: int,
        user_id: int,
        conversation_id: int,
    ) -> BusinessTask | None:
        """根据主键查询任务，同时校验用户和会话归属。"""

        stmt = select(BusinessTask).where(
            BusinessTask.id == task_id,
            BusinessTask.created_by == user_id,
            BusinessTask.conversation_id == conversation_id,
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_attachment_without_commit(
            self,
            attachment: BusinessTaskAttachment,
    ) -> BusinessTaskAttachment:
        """添加草稿附件记录，不提交事务。"""
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def list_attachments_by_task_and_item(
            self,
            *,
            business_task_id: int,
            expense_item_uid: str,
    ) -> list[BusinessTaskAttachment]:
        """查询指定费用明细的草稿附件。"""
        result = await self.session.execute(
            select(BusinessTaskAttachment)
            .where(
                BusinessTaskAttachment.business_task_id == business_task_id,
                BusinessTaskAttachment.expense_item_uid == expense_item_uid,
            )
            .order_by(BusinessTaskAttachment.created_at.asc())
        )
        return list(result.scalars().all())

    async def delete_attachments_by_task_and_item(
            self,
            *,
            business_task_id: int,
            expense_item_uid: str,
    ) -> list[BusinessTaskAttachment]:
        """删除指定费用明细的草稿附件，返回被删除的记录（供调用方清理对象存储）。

        费用明细被删除时，其附件必须一并删除，否则会遗留「孤儿附件」：
        确认提交时附件无法关联到现存明细，导致整张单据永久无法提交。
        """
        attachments = await self.list_attachments_by_task_and_item(
            business_task_id=business_task_id,
            expense_item_uid=expense_item_uid,
        )

        for attachment in attachments:
            await self.session.delete(attachment)

        if attachments:
            await self.session.flush()

        return attachments

    async def delete_attachments_by_ids(
            self,
            attachments: list[BusinessTaskAttachment],
    ) -> None:
        """批量删除草稿附件记录（供提交前清理历史遗留孤儿附件）。"""
        if not attachments:
            return

        for attachment in attachments:
            await self.session.delete(attachment)

        await self.session.flush()

    async def list_attachments_by_task(
            self,
            business_task_id: int,
    ) -> list[BusinessTaskAttachment]:
        """
        查询业务任务下的全部附件。

        按创建时间升序排列，供费用明细组装附件列表使用。
        """
        stmt = (
            select(BusinessTaskAttachment)
            .where(
                BusinessTaskAttachment.business_task_id == business_task_id
            )
            .order_by(BusinessTaskAttachment.created_at.asc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ===== 以下为原 ExpenseClaimRepository 的方法（合并自 expense_claim_repository.py） =====
    # 注意：BusinessTask 已有 get_by_id / add_without_commit，
    # 这里统一加 claim 前缀区分，避免同名方法语义混淆。

    async def get_claim_by_id(
        self,
        *,
        claim_id: int,
        applicant_id: int | None = None,
        for_update: bool = False,
    ) -> ExpenseClaim | None:
        """根据主键查询报销单，可选校验申请人归属。"""

        stmt = select(ExpenseClaim).where(
            ExpenseClaim.id == claim_id,
        )

        if applicant_id is not None:
            stmt = stmt.where(
                ExpenseClaim.applicant_id == applicant_id,
            )

        if for_update:
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_claim_by_claim_no(
        self,
        claim_no: str,
    ) -> ExpenseClaim | None:
        """根据报销单号查询。"""

        stmt = select(ExpenseClaim).where(
            ExpenseClaim.claim_no == claim_no,
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_claim_without_commit(
        self,
        claim: ExpenseClaim,
    ) -> ExpenseClaim:
        """添加报销单并 flush，不提交事务。"""

        self.session.add(claim)
        await self.session.flush()
        return claim

    async def add_claim_items_without_commit(
        self,
        items: list[ExpenseItem],
    ) -> list[ExpenseItem]:
        """批量添加报销明细并 flush，不提交事务。"""

        if not items:
            return []

        self.session.add_all(items)
        await self.session.flush()
        return items

    async def flush(self) -> None:
        """刷新当前 Session，不提交事务。"""

        await self.session.flush()
