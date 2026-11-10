# AI 对话路由：只负责 HTTP 收发，业务逻辑全部委托给 Service
import asyncio
import json
from typing import Annotated, AsyncIterator
from fastapi import APIRouter, Depends, Query, status, HTTPException, UploadFile, File
from starlette.requests import Request
from starlette.responses import StreamingResponse
from app.api.dependencies import get_conversation_service, get_business_task_service
from app.core.deps import get_current_user
from app.core.response import UnifiedResponseRoute
from app.models.user import User
from app.models.workflow import WorkflowRunStatus
from app.schemas.chat import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageSendRequest,
    MessageSendResponse, WorkflowRunStatusResponse, ConversationUpdateRequest, ConversationDeleteResponse,
    ConversationBusinessTaskListResponse,
)
from app.events.chat_progress import progress_broker, ChatProgressEvent
from app.services.business_task_service import BusinessTaskService
from app.services.conversations_service import ConversationMessageService
from app.utils.logger import logger

router = APIRouter(
    prefix="/conversations",
    tags=["AI 对话"],
    route_class=UnifiedResponseRoute,
)


# 创建会话接口
@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    data: ConversationCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ConversationMessageService, Depends(get_conversation_service)
    ],
):
    return await service.create_conversation(
        user_id=current_user.id, title=data.title
    )

# 修改会话标题
@router.patch(
    "/{conversation_uid}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
)
async def update_conversation_title(
    conversation_uid: str,
    data: ConversationUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ConversationMessageService, Depends(get_conversation_service)
    ],
):
    return await service.update_conversation_title(
        user_id=current_user.id,
        conversation_uid=conversation_uid,
        title=data.title,
    )

# 搜索会话（按标题模糊匹配）
@router.get(
    "/search",
    response_model=ConversationListResponse,
)
async def search_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ConversationMessageService, Depends(get_conversation_service)
    ],
    keyword: str = Query(..., min_length=1, max_length=50, description="搜索关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return await service.search_conversations(
        user_id=current_user.id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )



# 删除会话
@router.delete(
    "/{conversation_uid}",
    response_model=ConversationDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_conversation(
    conversation_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ConversationMessageService, Depends(get_conversation_service)
    ],
):
    return await service.delete_conversation(
        user_id=current_user.id,
        conversation_uid=conversation_uid,
    )

# 获取当前用户的所有会话
@router.get(
    "",
    response_model=ConversationListResponse,
)
async def get_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ConversationMessageService, Depends(get_conversation_service)
    ],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return await service.list_conversations(
        user_id=current_user.id, page=page, page_size=page_size
    )

# 返回指定会话的近100条聊天消息
@router.get(
    "/{conversation_uid}/messages",
    response_model=MessageListResponse,
)
async def get_conversation_messages(
    conversation_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ConversationMessageService, Depends(get_conversation_service)
    ],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
):
    return await service.get_conversation_messages(
        user_id=current_user.id,
        conversation_uid=conversation_uid,
        page=page,
        page_size=page_size,
    )

# 查询会话内的业务任务（右侧"相关任务"面板）
@router.get(
    "/{conversation_uid}/business-tasks",
    response_model=ConversationBusinessTaskListResponse,
)
async def list_conversation_business_tasks(
    conversation_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        BusinessTaskService, Depends(get_business_task_service)
    ],
):
    return await service.list_conversation_tasks(
        conversation_uid=conversation_uid,
        user_id=current_user.id,
    )


# 获取工作流状态
@router.get(
    "/{conversation_uid}/runs/{run_uid}",
    response_model=WorkflowRunStatusResponse,
)
async def get_workflow_run_status(
    conversation_uid: str,
    run_uid: str,
    current_user=Depends(get_current_user),
    service=Depends(get_conversation_service),
):
    return await service.get_workflow_run_status(
        user_id=current_user.id,
        conversation_uid=conversation_uid,
        run_uid=run_uid,
    )


# 接收用户消息
@router.post(
    "/{conversation_uid}/messages",
    response_model=MessageSendResponse,
    status_code=status.HTTP_200_OK,
)
async def trigger_conversation(
    conversation_uid: str,
    data: MessageSendRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ConversationMessageService, Depends(get_conversation_service)
    ],
):
    return await service.trigger_conversation(
        user_id=current_user.id,
        conversation_uid=conversation_uid,
        data=data,
    )


# 建立会话 SSE 连接
@router.get("/{conversation_uid}/runs/{run_uid}/events")
async def workflow_progress(
    conversation_uid: str,
    run_uid: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        ConversationMessageService,
        Depends(get_conversation_service),
    ],
) -> StreamingResponse:
    """订阅工作流进度，先建立订阅，再读取最新工作流状态。"""

    # 第一次查询：提前校验工作流是否存在，以及当前用户是否有权访问。
    run = await service.get_workflow_run(
        conversation_uid=conversation_uid,
        run_uid=run_uid,
        user_id=current_user.id,
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="工作流不存在或无权访问",
        )

    terminal_statuses = {
        WorkflowRunStatus.SUCCESS.value,
        WorkflowRunStatus.FAILED.value,
        WorkflowRunStatus.CANCELLED.value,
    }

    async def events() -> AsyncIterator[str]:
        """先订阅 Redis，再查询数据库，尽量避免漏掉运行期间的事件。"""

        ready_event = asyncio.Event()

        event_iterator = progress_broker.subscribe(
            run_uid,
            ready_event=ready_event,
        )

        next_event_task: asyncio.Task | None = None

        try:
            # 1. 启动订阅，并等待 Redis 确认订阅成功。
            next_event_task = asyncio.create_task(
                anext(event_iterator, None)
            )

            await ready_event.wait()

            # 2. 订阅建立后，重新读取数据库中的最新状态。
            latest_run = await service.get_workflow_run(
                conversation_uid=conversation_uid,
                run_uid=run_uid,
                user_id=current_user.id,
            )

            if latest_run is None:
                yield (
                    "event: run_failed\n"
                    f"data: {json.dumps({'run_uid': run_uid, 'message': '工作流不存在或无权访问'}, ensure_ascii=False)}\n\n"
                )
                return

            snapshot = {
                "run_uid": run_uid,
                "status": latest_run.status,
                "error_message": latest_run.error_message,
            }

            yield (
                "event: run_snapshot\n"
                f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
            )

            # 3. 如果工作流已经结束，不再等待 Pub/Sub。
            # 前端应通过消息列表接口加载最终 AI 回复。
            if latest_run.status in terminal_statuses:
                return

            # 4. 工作流仍在执行，继续消费 Redis 事件。
            while True:
                if await request.is_disconnected():
                    break

                done, _ = await asyncio.wait(
                    {next_event_task},
                    timeout=15,
                )

                if not done:
                    yield ": ping\n\n"
                    continue

                event = next_event_task.result()

                if event is None:
                    break

                event_name = event.get("event", "progress")

                yield (
                    f"event: {event_name}\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )

                if event_name in {
                    ChatProgressEvent.RUN_COMPLETED.value,
                    ChatProgressEvent.RUN_FAILED.value,
                    ChatProgressEvent.RUN_CANCELLED.value,
                }:
                    break

                next_event_task = asyncio.create_task(
                    anext(event_iterator, None)
                )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "聊天工作流 SSE 推送失败：conversation_uid=%s, run_uid=%s",
                conversation_uid,
                run_uid,
            )

        finally:
            if next_event_task is not None and not next_event_task.done():
                next_event_task.cancel()
                await asyncio.gather(
                    next_event_task,
                    return_exceptions=True,
                )

            await event_iterator.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{conversation_uid}/{task_uid}/expense-items/{expense_item_uid}/attachments",
    status_code=status.HTTP_201_CREATED,
    summary="上传报销费用明细附件",
)
async def upload_expense_item_attachment(
    conversation_uid: str,
    task_uid: str,
    expense_item_uid: str,
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        BusinessTaskService,
        Depends(get_business_task_service),
    ],
):
    return await service.upload_expense_item_attachment(
        conversation_uid=conversation_uid,
        task_uid=task_uid,
        expense_item_uid=expense_item_uid,
        file=file,
        current_user=current_user,
    )