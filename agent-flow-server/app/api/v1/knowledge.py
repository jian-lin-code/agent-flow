
import asyncio
import json
import time
from typing import Annotated, AsyncIterator

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_knowledge_service
from app.core.deps import get_current_user
from app.core.response import UnifiedResponseRoute
from app.events.document_progress import progress_broker
from app.models.knowledge import DocumentStatus
from app.models.user import User
from app.utils.logger import logger
from app.schemas.knowledge import (
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBasePermissionGrantRequest,
    KnowledgeBasePermissionItem,
    KnowledgeBasePermissionListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseStatsResponse,
    KnowledgeOverviewResponse,
    KnowledgeBaseUpdateRequest,
    KnowledgeUserCandidate,
)
from app.services.knowledge_service import KnowledgeService


router = APIRouter(
    prefix="/knowledge-bases",
    tags=["知识库"],
    route_class=UnifiedResponseRoute,
)


# ==================== 知识库管理 ====================


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base(
    data: KnowledgeBaseCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """创建知识库，默认创建为当前用户的私有知识库。"""
    return await service.create_knowledge_base(
        data=data,
        current_user=current_user,
    )


@router.get(
    "",
    response_model=KnowledgeBaseListResponse,
)
async def list_knowledge_bases(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
):
    """分页获取当前用户有权访问的知识库。"""
    return await service.list_knowledge_bases(
        current_user=current_user,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/overview",
    response_model=KnowledgeOverviewResponse,
)
async def get_knowledge_overview(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """知识库总览统计（当前用户可见范围内）：文档/索引/检索频次聚合与最近解析动态。

    注意：必须注册在 /{kb_uid} 之前，否则会被动态路径吞掉。
    """
    return await service.get_knowledge_overview(current_user=current_user)


@router.get(
    "/users/search",
    response_model=list[KnowledgeUserCandidate],
)
async def search_grantable_users(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    keyword: str | None = Query(default=None, max_length=50),
):
    """按账号或昵称搜索可授权用户（创建知识库时预选成员）。
    注意：必须注册在 /{kb_uid} 之前，否则会被动态路径吞掉。
    """
    return await service.search_grantable_users(keyword=keyword)


@router.get(
    "/{kb_uid}",
    response_model=KnowledgeBaseResponse,
)
async def get_knowledge_base(
    kb_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """获取指定知识库详情，Service 层负责检查读取权限。"""
    return await service.get_knowledge_base(
        kb_uid=kb_uid,
        current_user=current_user,
    )


@router.put(
    "/{kb_uid}",
    response_model=KnowledgeBaseResponse,
)
async def update_knowledge_base(
    kb_uid: str,
    data: KnowledgeBaseUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """修改指定知识库信息，Service 层负责检查管理权限。"""
    return await service.update_knowledge_base(
        kb_uid=kb_uid,
        data=data,
        current_user=current_user,
    )


@router.delete(
    "/{kb_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_knowledge_base(
    kb_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """删除指定知识库，Service 层负责检查管理权限。"""
    await service.delete_knowledge_base(
        kb_uid=kb_uid,
        current_user=current_user,
    )


@router.get(
    "/{kb_uid}/stats",
    response_model=KnowledgeBaseStatsResponse,
)
async def get_knowledge_base_stats(
    kb_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """获取知识库统计信息（文档数/分块数/检索调用频次/物理占用）。"""
    return await service.get_knowledge_base_stats(
        kb_uid=kb_uid,
        current_user=current_user,
    )


# ==================== 知识库授权管理 ====================


@router.get(
    "/{kb_uid}/permissions",
    response_model=KnowledgeBasePermissionListResponse,
)
async def list_knowledge_base_permissions(
    kb_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """获取指定知识库的用户授权列表，仅管理者可见。"""
    return await service.list_permissions(
        kb_uid=kb_uid,
        current_user=current_user,
    )


@router.get(
    "/{kb_uid}/permissions/candidates",
    response_model=list[KnowledgeUserCandidate],
)
async def search_permission_candidates(
    kb_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    keyword: str | None = Query(default=None, max_length=50),
):
    """按账号或昵称搜索可被授权的用户候选。"""
    return await service.search_permission_candidates(
        kb_uid=kb_uid,
        current_user=current_user,
        keyword=keyword,
    )


@router.post(
    "/{kb_uid}/permissions",
    response_model=KnowledgeBasePermissionItem,
    status_code=status.HTTP_201_CREATED,
)
async def grant_knowledge_base_permission(
    kb_uid: str,
    data: KnowledgeBasePermissionGrantRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """为用户授予知识库权限；已存在授权时更新权限级别。"""
    return await service.grant_permission(
        kb_uid=kb_uid,
        data=data,
        current_user=current_user,
    )


@router.delete(
    "/{kb_uid}/permissions/{user_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_knowledge_base_permission(
    kb_uid: str,
    user_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """撤销指定用户对知识库的授权。"""
    await service.revoke_permission(
        kb_uid=kb_uid,
        user_uid=user_uid,
        current_user=current_user,
    )


@router.get(
    "/{kb_uid}/documents",
    response_model=DocumentListResponse,
)
async def list_documents(
    kb_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
):
    """分页获取指定知识库下的文档列表。"""
    return await service.list_documents(
        kb_uid=kb_uid,
        current_user=current_user,
        page=page,
        page_size=page_size,
    )


# ==================== 文档管理 ====================


@router.post(
    "/{kb_uid}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    kb_uid: str,
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    request: Request,
) -> DocumentResponse:
    """上传文档到指定知识库，并提交 ARQ 文档处理任务。"""
    document = await service.upload_document(
        kb_uid=kb_uid,
        file=file,
        current_user=current_user,
    )

    arq_redis = request.app.state.arq_redis

    await arq_redis.enqueue_job(
        "process_document",
        document.id,
        _queue_name="rag-flow",
        _job_id=f"rag-{document.id}",
    )

    # 前端响应仅返回 UID，不暴露内部自增 ID
    response = DocumentResponse.model_validate(document)
    response.knowledge_base_uid = kb_uid

    return response


@router.get(
    "/documents/{document_uid}/progress",
)
async def document_progress(
    document_uid: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> StreamingResponse:
    """通过 SSE 订阅文档处理进度，并检查当前用户的读取权限。

    与 workflow_progress 相同的策略：先建立 Redis 订阅，再查数据库快照，
    避免漏掉订阅建立前产生的事件；任何异常都会推送终态事件并关闭连接，
    保证前端 SSE 不会在报错后一直挂起。
    """

    # 必须在建立 SSE 连接之前完成权限检查。
    # get_document 内部会检查文档所属知识库的 read 权限。
    await service.get_document(
        document_uid=document_uid,
        current_user=current_user,
    )

    terminal_statuses = {
        DocumentStatus.INDEXED.value,
        DocumentStatus.FAILED.value,
    }

    async def events() -> AsyncIterator[str]:
        """先订阅 Redis，再查询数据库，尽量避免漏掉处理期间的事件。"""

        ready_event = asyncio.Event()

        event_iterator = progress_broker.subscribe(
            document_uid,
            ready_event=ready_event,
        )

        next_event_task: asyncio.Task | None = None

        try:
            # 1. 启动订阅，并等待 Redis 确认订阅成功。
            next_event_task = asyncio.create_task(
                anext(event_iterator, None)
            )

            await ready_event.wait()

            # 2. 订阅建立后，重新读取数据库中的最新状态作为快照。
            #    兜底场景：worker 已失败/已完成但没有发出终态事件，
            #    或后端在此期间报错，快照能让连接立即终结而不是无限等待。
            document = await service.get_document(
                document_uid=document_uid,
                current_user=current_user,
            )

            snapshot = {
                "document_uid": document_uid,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": document.status,
                "message": document.error_message or "已连接，正在同步处理进度",
                "stage_records": document.stage_records,
            }

            yield (
                "event: progress\n"
                f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
            )

            # 3. 文档已经处理结束，不再等待 Pub/Sub，直接关闭连接。
            if document.status in terminal_statuses:
                return

            # 4. 文档仍在处理中，继续消费 Redis 事件。
            idle_polls = 0
            while True:
                if await request.is_disconnected():
                    break

                done, _ = await asyncio.wait(
                    {next_event_task},
                    timeout=15,
                )

                if not done:
                    idle_polls += 1

                    # 心跳周期回读数据库：worker 被 kill -9 等异常退出时
                    # 永远不会发布终态事件，以数据库最新状态为准终结连接
                    try:
                        latest = await service.get_document(
                            document_uid=document_uid,
                            current_user=current_user,
                        )

                        if latest.status in terminal_statuses:
                            yield (
                                "event: progress\n"
                                f"data: {json.dumps({
                                    'document_uid': document_uid,
                                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                                    'status': latest.status,
                                    'message': latest.error_message or '文档处理已结束',
                                    'stage_records': latest.stage_records,
                                }, ensure_ascii=False)}\n\n"
                            )
                            return
                    except Exception:
                        logger.warning(
                            "SSE 心跳周期回读文档状态失败：document_uid=%s",
                            document_uid,
                            exc_info=True,
                        )

                    if idle_polls >= 8:
                        # 约 2 分钟没有任何事件且数据库状态未变化，
                        # 判定后台任务大概率已中断，主动断开避免连接无限挂起
                        yield (
                            "event: progress\n"
                            f"data: {json.dumps({
                                'document_uid': document_uid,
                                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                                'status': None,
                                'message': '长时间未收到处理进度，连接已断开，请稍后刷新查看最新状态',
                                'stage_records': None,
                            }, ensure_ascii=False)}\n\n"
                        )
                        return

                    # 定期发送 SSE 注释作为心跳，同时给断连检测留出机会
                    yield ": ping\n\n"
                    continue

                event = next_event_task.result()

                if event is None:
                    break

                idle_polls = 0

                yield (
                    "event: progress\n"
                    f"data: {event.model_dump_json()}\n\n"
                )

                if event.status in terminal_statuses:
                    break

                next_event_task = asyncio.create_task(
                    anext(event_iterator, None)
                )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "文档处理 SSE 推送失败：document_uid=%s",
                document_uid,
            )

            # 后端出错时主动推送失败终态，让前端立即结束等待并断开连接
            error_event = {
                "document_uid": document_uid,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": DocumentStatus.FAILED.value,
                "message": "处理进度连接异常，请刷新页面查看最新状态",
                "stage_records": None,
            }

            try:
                yield (
                    "event: progress\n"
                    f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
                )
            except Exception:
                pass

            # 正常结束生成器关闭连接；响应头已发出，这里不能再抛 HTTPException
            return

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


@router.delete(
    "/documents/{document_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    document_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """删除指定文档，Service 层负责检查所属知识库的管理权限。"""
    await service.delete_document(
        document_uid=document_uid,
        current_user=current_user,
    )


@router.post(
    "/documents/{document_uid}/reprocess",
    response_model=DocumentResponse,
)
async def reprocess_document(
    request: Request,
    document_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """重新处理指定文档：重置状态并向 redis 投递 RAG 处理任务（rag-flow 队列）。"""
    document = await service.reprocess_document(
        document_uid=document_uid,
        current_user=current_user,
    )

    # 往 redis 投递任务，重新执行 RAG 管线（解析 → 分块 → 向量化 → 入库）
    # job_id 带时间戳：ARQ 按 job_id 去重，固定 id 会导致短时间内无法重复重新处理
    arq_redis = request.app.state.arq_redis
    await arq_redis.enqueue_job(
        "process_document",
        document.id,
        _queue_name="rag-flow",
        _job_id=f"rag-re-{document.id}-{int(time.time())}",
    )

    return await service.document_response(document)


@router.get(
    "/documents/{document_uid}/chunks",
    response_model=list[DocumentChunkResponse],
)
async def list_document_chunks(
    document_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """获取指定文档的文本分块，Service 层负责检查读取权限。"""
    return await service.list_chunks(
        document_uid=document_uid,
        current_user=current_user,
    )


@router.get(
    "/documents/{document_uid}/preview",
)
async def get_document_preview(
    document_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """获取文档在线预览内容（docx 转 HTML / pdf 直链 / md 文本）。

    Service 层负责检查读取权限；返回结构按 kind 区分，前端据此选择渲染器。
    """
    return await service.get_document_preview(
        document_uid=document_uid,
        current_user=current_user,
    )


@router.get(
    "/documents/{document_uid}",
    response_model=DocumentResponse,
)
async def get_document(
    document_uid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
):
    """根据文档 UID 获取文档详情，Service 层负责检查读取权限。"""
    return await service.get_document(
        document_uid=document_uid,
        current_user=current_user,
    )
