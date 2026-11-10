
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import WorkflowRun


class WorkflowRepository:
    """WorkflowRun 表的数据访问封装。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_uid(
        self,
        *,
        run_uid: str,
        user_id: int,
        conversation_id: int,
        for_update: bool = False,
    ) -> WorkflowRun | None:
        """
        根据工作流 UID 查询执行记录，
        同时校验触发用户和所属会话。
        """

        stmt = select(WorkflowRun).where(
            WorkflowRun.uid == run_uid,
            WorkflowRun.triggered_by == user_id,
            WorkflowRun.conversation_id == conversation_id,
        )

        if for_update:
            stmt = stmt.with_for_update()  # with_for_update 是 SQLAlchemy 中给查询行加悲观锁的方法，防止其他事务在提交前修改这些数据。

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_without_commit(
        self,
        run: WorkflowRun,
    ) -> WorkflowRun:
        """添加工作流执行记录并 flush，不提交事务。"""

        self.session.add(run)
        await self.session.flush()
        return run

    async def update(
        self,
        run: WorkflowRun,
    ) -> WorkflowRun:
        """
        更新已被 Session 跟踪的工作流执行记录。

        不主动提交事务。
        """

        await self.session.flush()
        return run

    async def flush(self) -> None:
        """刷新当前 Session，不提交事务。"""

        await self.session.flush()
