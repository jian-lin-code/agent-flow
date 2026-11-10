# 职责：对话业务编排，数据查询和持久化由 Repository 负责
from typing import Any

from arq.connections import ArqRedis
from app.models.workflow import WorkflowRun, WorkflowRunStatus
from app.core.config import settings
from app.core.exceptions import BizException, ErrorCode
from app.models.conversation import Conversation, Message
from app.repository.conversations_repository import ConversationsRepository
from app.schemas.chat import (
    MessageItem,
    MessageListResponse,
    MessageSendRequest,
    MessageSendResponse,
    ConversationListResponse,
    ConversationResponse,
    RunInfo, WorkflowRunStatusResponse,
)
from app.utils.datetime_helper import utc_now


class ConversationMessageService:
    """处理对话的业务类。"""

    def __init__(
        self,
        repository: ConversationsRepository,
        redis: ArqRedis | None
    ):
        self.repository = repository
        self.redis = redis

    async def create_conversation(self, user_id: int, title: str) -> ConversationResponse:
        """创建会话。"""
        clean_title = title.strip() if title and title.strip() else "新对话"
        conversation = Conversation(
            user_id=user_id,
            title=clean_title[:20],
        )
        conversation = await self.repository.create_conversation(conversation)
        return ConversationResponse.model_validate(conversation)

    # 修改会话标题
    async def update_conversation_title(
            self,
            *,
            user_id: int,
            conversation_uid: str,
            title: str,
    ) -> ConversationResponse:
        """修改当前用户指定会话的标题。"""

        clean_title = (title or "").strip()

        if not clean_title:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="会话标题不能为空",
            )

        conversation = await self.repository.get_conversation_for_update(
            conversation_uid,
            user_id,
        )

        if conversation is None:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="会话不存在或无权访问",
            )

        conversation = await self.repository.update_conversation_title(
            conversation,
            clean_title[:20],
        )

        return ConversationResponse.model_validate(conversation)

    async def search_conversations(
            self,
            *,
            user_id: int,
            keyword: str,
            page: int = 1,
            page_size: int = 20,
    ) -> ConversationListResponse:
        """按标题模糊搜索当前用户的会话。"""

        clean_keyword = (keyword or "").strip()

        if not clean_keyword:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="搜索关键词不能为空",
            )

        total = await self.repository.count_conversations_by_keyword(
            user_id=user_id,
            keyword=clean_keyword,
        )

        offset = (page - 1) * page_size
        conversations = await self.repository.search_conversations(
            user_id=user_id,
            keyword=clean_keyword,
            offset=offset,
            limit=page_size,
        )

        return ConversationListResponse(
            items=[
                ConversationResponse.model_validate(item)
                for item in conversations
            ],
            total=total,
        )


    # 删除会话
    async def delete_conversation(
            self,
            *,
            user_id: int,
            conversation_uid: str,
    ) -> dict[str, Any]:
        """删除当前用户指定会话。

        会话不存在或无权访问时返回 deleted=False（幂等，不报错），
        避免前端重复删除时报错，也不泄露 uid 是否存在。
        """

        conversation = await self.repository.get_conversation_for_update(
            conversation_uid,
            user_id,
        )

        if conversation is None:
            return {
                "conversation_uid": conversation_uid,
                "deleted": False,
            }

        await self.repository.delete_conversation(conversation)

        return {
            "conversation_uid": conversation_uid,
            "deleted": True,
        }




    # 处理用户消息
    async def trigger_conversation(
        self,
        user_id: int,
        conversation_uid: str,
        data: MessageSendRequest,
    ) -> MessageSendResponse:
        """处理会话消息"""
        # 1.拿到当前用户这条会话信息
        conversation = await self.repository.get_conversation(
            conversation_uid,
            user_id,
        )

        if conversation is None:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="会话不存在或无权访问",
            )

        content = data.content.strip()
        if not content:
            raise BizException(
                code=ErrorCode.BAD_REQUEST,
                msg="消息内容不能为空",
            )

        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=content,
            extra_data={
                key: value
                for key, value in {
                    "action": data.action,
                    "selected_task_uid": (
                        str(data.selected_task_uid)
                        if data.selected_task_uid
                        else None
                    ),
                }.items()
                if value is not None
            },
            created_at=utc_now(),
        )

        # 先 flush 获取 user_message.id，不在这里提交。
        await self.repository.add_message_without_commit(user_message)

        workflow_run = WorkflowRun(
            conversation_id=conversation.id,
            trigger_message_id=user_message.id,
            triggered_by=user_id,
            status=WorkflowRunStatus.PENDING.value,
        )

        await self.repository.add_workflow_run_without_commit(workflow_run)

        conversation.updated_at = utc_now()

        # 用户消息和工作流记录一起持久化。
        await self.repository.commit()

        # 数据库提交成功后再投递任务（任务参数使用对外 uid，不暴露自增 id）。
        try:
            await self.redis.enqueue_job(
                "process_chat_workflow",
                workflow_run.uid,
                _queue_name="agent-flow",
            )
        except Exception:
            # 投递失败时保留用户消息，并把运行记录标记为失败。
            await self.repository.mark_run_enqueue_failed(
                workflow_run.uid,
                "后台任务提交失败，请稍后重试。",
            )
            status = WorkflowRunStatus.FAILED.value
        else:
            status = WorkflowRunStatus.PENDING.value

        return MessageSendResponse(
            conversation_uid=conversation.uid,
            user_message=MessageItem.model_validate(user_message),
            assistant_message=None,
            run=RunInfo(
                uid=workflow_run.uid,
                status=status,
            ),
        )

    async def get_workflow_run(
            self,
            conversation_uid: str,
            run_uid: str,
            user_id: int,
    ) -> WorkflowRun | None:
        """查询指定用户在指定会话中的工作流运行记录，无权限或不存在时返回 None。"""
        return await self.repository.get_workflow_run_by_uid(
            conversation_uid=conversation_uid,
            run_uid=run_uid,
            user_id=user_id,
        )

    async def list_conversations(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 10,
    ) -> ConversationListResponse:
        """分页查询当前用户的会话列表。"""
        total = await self.repository.count_conversations(user_id)
        offset = (page - 1) * page_size
        conversations = await self.repository.list_conversations(
            user_id, offset=offset, limit=page_size
        )
        return ConversationListResponse(
            items=[
                ConversationResponse.model_validate(item)
                for item in conversations
            ],
            total=total,
        )

    async def get_conversation_messages(
        self,
        user_id: int,
        conversation_uid: str,
        page: int = 1,
        page_size: int = 100,
    ) -> MessageListResponse:
        """加载某会话的历史消息（校验归属）。"""
        conversation = await self.repository.get_conversation(conversation_uid, user_id)
        if conversation is None:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="会话不存在或无权访问",
            )

        total = await self.repository.count_messages(conversation.id)
        offset = (page - 1) * page_size
        messages = await self.repository.list_messages(
            conversation.id, offset=offset, limit=page_size
        )

        return MessageListResponse(
            conversation_uid=conversation.uid,
            items=[
                MessageItem.model_validate(message)
                for message in messages
            ],
            total=total,
        )

    async def get_workflow_run_status(
            self,
            *,
            user_id: int,
            conversation_uid: str,
            run_uid: str,
    ) -> WorkflowRunStatusResponse:
        run = await self.repository.get_workflow_run_by_uid(
            conversation_uid=conversation_uid,
            run_uid=run_uid,
            user_id=user_id,
        )

        if run is None:
            raise BizException(
                code=ErrorCode.NOT_FOUND,
                msg="工作流运行记录不存在或无权访问",
            )

        duration_ms = None
        if run.started_at is not None and run.finished_at is not None:
            duration_ms = max(
                int((run.finished_at - run.started_at).total_seconds() * 1000),
                0,
            )

        return WorkflowRunStatusResponse(
            conversation_uid=conversation_uid,
            run_uid=run.uid,
            status=run.status,
            error_message=run.error_message,
            started_at=run.started_at,
            finished_at=run.finished_at,
            model_name=settings.LLM_DEFAULT_MODEL,
            duration_ms=duration_ms,
        )