# conversations / messages 数据访问层（Repository）
# 职责：封装所有 ORM 数据访问，不包含业务逻辑
# 注入方式：session 由 api/dependencies.get_conversations_repository 注入
from copy import deepcopy

from app.models import BusinessTask
from app.utils.datetime_helper import utc_now
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.conversation import Conversation, Message
from app.models.workflow import WorkflowRun, WorkflowRunStatus


class ConversationsRepository:
    """Conversation / Message 表的读写封装。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------- 会话 ----------

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        """写入新会话，并刷新出自增 id。"""
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_conversation_for_update(
            self,
            conversation_uid: str,
            user_id: int,
    ) -> Conversation | None:
        """按 uid + 归属用户查询会话，并对该行加锁（FOR UPDATE）。

        用于修改/删除会话前的并发保护。
        """
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.uid == conversation_uid,
                Conversation.user_id == user_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    # 修改会话标题
    async def update_conversation_title(
            self,
            conversation: Conversation,
            title: str,
    ) -> Conversation:
        """更新会话标题并提交事务。"""
        conversation.title = title
        conversation.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    # 统计标题匹配关键词的会话总数
    async def count_conversations_by_keyword(
            self,
            *,
            user_id: int,
            keyword: str,
    ) -> int:
        """统计标题匹配关键词的会话总数。"""
        pattern = f"%{keyword}%"
        result = await self.session.execute(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.title.ilike(pattern),
            )
        )
        return result.scalar_one()

    # 搜索会话
    async def search_conversations(
            self,
            *,
            user_id: int,
            keyword: str,
            offset: int,
            limit: int,
    ) -> list[Conversation]:
        """按标题模糊搜索会话，最近更新的排在前面。"""
        pattern = f"%{keyword}%"
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.title.ilike(pattern),
            )
            .order_by(
                Conversation.updated_at.desc(),
                Conversation.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_conversation(
            self,
            conversation: Conversation,
    ) -> None:
        """删除会话并提交事务。

        关联的 message / workflow_run 依赖模型关系上的
        cascade="all, delete-orphan" 或数据库外键 ON DELETE CASCADE。
        """
        # 1. 先删依赖 business_task 的记录（如 workflow_run 引用了 business_task_id）
        #    具体顺序取决于你的外键依赖关系
        await self.session.execute(
            delete(WorkflowRun).where(
                WorkflowRun.conversation_id == conversation.id
            )
        )

        # 2. 删业务任务
        await self.session.execute(
            delete(BusinessTask).where(
                BusinessTask.conversation_id == conversation.id
            )
        )

        # 3. 删消息
        await self.session.execute(
            delete(Message).where(
                Message.conversation_id == conversation.id
            )
        )

        # 4. 最后删会话
        await self.session.delete(conversation)
        await self.session.commit()

    async def get_conversation(
        self, conversation_uid: str, user_id: int
    ) -> Conversation | None:
        """按 uid + 归属用户查询会话（用于权限校验，不暴露自增 id）。"""
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.uid == conversation_uid,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def count_conversations(self, user_id: int) -> int:
        """统计当前用户的会话总数。"""
        result = await self.session.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
        )
        return result.scalar_one()

    async def list_conversations(
        self, user_id: int, offset: int, limit: int
    ) -> list[Conversation]:
        """分页查询会话，最近更新的排在前面。"""
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(
                Conversation.updated_at.desc(),
                Conversation.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def touch_conversation(self, conversation: Conversation) -> None:
        """更新会话的最近活动时间（updated_at）。"""
        self.session.add(conversation)
        await self.session.commit()



    # ---------- 消息 ----------

    async def count_messages(self, conversation_id: int) -> int:
        """统计某会话的消息总数。"""
        result = await self.session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
        return result.scalar_one()

    async def list_messages(
            self,
            conversation_id: int,
            offset: int,
            limit: int,
    ) -> list[Message]:
        """分页查询消息，优先查询最新消息，返回结果按时间正序。"""

        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(
                Message.created_at.desc(),
                Message.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        messages = result.scalars().all()

        return list(reversed(messages))

    async def add_message(self, message: Message) -> Message:
        """写入一条消息，并刷新出自增 id。"""
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def add_messages(self, messages: list[Message]) -> list[Message]:
        """批量写入多条消息（同一事务提交）。"""
        self.session.add_all(messages)
        await self.session.commit()
        for m in messages:
            await self.session.refresh(m)
        return messages

    async def add_message_without_commit(
            self,
            message: Message,
    ) -> Message:
        """
        将消息对象添加到 Session 中，并执行 flush 操作（获取自增 ID），但不提交事务。

        :param message: 待保存的 Message ORM 对象
        :return: 已被 Session 追踪并回填了主键的 Message 对象
        """
        self.session.add(message)
        await self.session.flush()
        return message

    async def add_workflow_run_without_commit(
            self,
            run: WorkflowRun,
    ) -> WorkflowRun:
        """
        将工作流执行记录添加到 Session 中，并执行 flush 操作，但不提交事务。

        :param run: 待保存的 WorkflowRun ORM 对象
        :return: 已被 Session 追踪并回填了主键的 WorkflowRun 对象
        """
        self.session.add(run)
        await self.session.flush()
        return run

    async def commit(self) -> None:
        """
        统一提交当前 Session 中的事务。
        通常用于协调多个 'without_commit' 方法后，进行最终的数据落盘。
        """
        await self.session.commit()

    async def mark_run_enqueue_failed(
            self,
            run_uid: str,
            error_message: str,
    ) -> None:
        """
        当工作流入队失败（如 Redis 抛出异常）时，根据 run_uid 将该任务标记为失败状态。

        :param run_uid: 对外暴露的工作流运行唯一标识
        :param error_message: 失败的具体错误信息
        """
        result = await self.session.execute(
            select(WorkflowRun).where(WorkflowRun.uid == run_uid)
        )
        run = result.scalar_one_or_none()

        if run is None:
            return

        run.status = WorkflowRunStatus.FAILED.value
        run.finished_at = utc_now()
        run.error_message = error_message

        await self.session.commit()

    async def get_workflow_run_by_uid(
            self,
            *,
            conversation_uid: str,
            run_uid: str,
            user_id: int,
    ) -> WorkflowRun | None:
        """
        根据会话 UID 和工作流运行 UID 获取工作流执行记录，并强制校验数据归属权。

        该方法通过 JOIN 会话表，确保当前查询的工作流属于指定的用户，防止越权访问（IDOR）。

        :param conversation_uid: 会话对外暴露的唯一标识
        :param run_uid: 工作流运行对外暴露的唯一标识
        :param user_id: 当前登录用户的内部数据库 ID（用于校验数据归属）
        :return: 如果找到匹配且属于该用户的记录，返回 WorkflowRun 对象；否则返回 None
        """
        stmt = (
            select(WorkflowRun)
            .join(
                Conversation,
                WorkflowRun.conversation_id == Conversation.id,
            )
            .where(
                Conversation.uid == conversation_uid,
                Conversation.user_id == user_id,
                WorkflowRun.uid == run_uid,
            )
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


