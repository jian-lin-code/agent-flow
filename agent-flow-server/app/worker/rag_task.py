import asyncio
import time
from pathlib import Path
from typing import cast

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import database
from app.core.config import settings
from app.core.exceptions import FileProcessingError
from app.models.knowledge import DocumentStatus
from app.rag.chunker import get_document_chunker
from app.rag.embedding import get_embedding_service, build_embedding_text
from app.rag.parser import get_document_parser
from app.repository.knowledge_repository import KnowledgeRepository
from app.events.document_progress import emit
from app.utils.cache import get_document_cache
from app.utils.datetime_helper import get_beijing_now_str
from app.utils.logger import logger
from app.utils.minio_client import build_object_url, get_minio_storage, parsed_md_object_name

# =========================
# 单例服务
# =========================
document_parser = get_document_parser()
local_cache = get_document_cache()
minio_client = get_minio_storage()
document_chunker = get_document_chunker()
embedding_service = get_embedding_service()


def _size_label(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{max(1, round(size / 1024))} KB"


async def process_document(ctx: dict, document_id: int) -> None:
    """ARQ 文档处理任务：读取文件、解析文档并切分为知识库片段。

    日志约定（前端按此渲染，改动前请先看 document.vue 的日志面板）：
    - 每条日志都带 stage（pending/parsing/chunking/embedding/indexed/failed）
      与 level（info/success/warn/error），前端据此分组、着色；
    - 阶段内用 progress(0-100) 驱动进度条；
    - 一条日志只讲一件事，细节用 "·" 分隔，避免长句刷屏。
    """
    logger.info("[Worker] 开始处理文档任务")

    session_factory = cast(async_sessionmaker[AsyncSession], database.async_session)
    started_at = time.monotonic()
    stage_started_at = started_at
    timings: dict[str, float] = {}

    def mark_stage(stage: str) -> None:
        """记录上一阶段耗时（用于最终的耗时汇总）。"""
        nonlocal stage_started_at
        now = time.monotonic()
        timings[stage] = round(now - stage_started_at, 1)
        stage_started_at = now

    async with session_factory() as session:
        repository = KnowledgeRepository(session)
        document = None

        if ctx is not None:
            ctx["process_logs"] = []

        async def log(
                message: str,
                *,
                stage: str | None = None,
                progress: int | None = None,
                level: str = "info",
                status: str | None = None,
                with_records: bool = False,
        ) -> None:
            """统一的进度输出：阶段/进度/级别一次带齐，前端不用再猜。"""
            await emit(
                message,
                ctx=ctx,
                stage=stage,
                progress=progress,
                level=level,
                status=status,
                stage_records=document.stage_records if (with_records and document) else None,
            )

        try:
            # 1. 加载文档记录
            document = await repository.get_document(document_id)
            if document is None:
                await log("任务异常：数据库中不存在该文档记录", stage="failed", level="error", status=DocumentStatus.FAILED.value)
                raise FileProcessingError("任务异常：数据库中不存在该文档记录")

            # 把对外 uid（文档 + 知识库）写入 ctx，供下游从 ctx 取
            if ctx is not None:
                ctx["document_uid"] = document.uid
                ctx["kb_uid"] = document.knowledge_base.uid

            await log(
                f"任务已接收 · {document.title} · {_size_label(document.file_size or 0)}",
                stage=DocumentStatus.PENDING.value,
                progress=0,
            )
            # 写入 ctx 让 parser/chunker 等下游模块的 emit 自动带上当前阶段
            if ctx is not None:
                ctx["stage"] = DocumentStatus.PENDING.value

            # 2. 读取文件
            file_bytes = await local_cache.read(document.uid, document.title)
            if file_bytes is None:
                await log("本地缓存未命中，正在从对象存储下载源文件", stage=DocumentStatus.PENDING.value, progress=2)
                file_bytes = await minio_client.download(document.storage_path or "")

                if not file_bytes:
                    await log("源文件下载失败：对象存储返回为空", stage="failed", level="error", status=DocumentStatus.FAILED.value)
                    raise FileProcessingError("文件下载失败，MinIO 返回为空")

                await log(
                    f"源文件下载完成 · {_size_label(len(file_bytes))}",
                    stage=DocumentStatus.PENDING.value,
                    progress=5,
                )
            else:
                await log(
                    f"命中本地缓存 · {_size_label(len(file_bytes))}，跳过下载",
                    stage=DocumentStatus.PENDING.value,
                    progress=5,
                )

            # ==========================
            #  RAG 第一阶段 - 文档解析
            # ==========================
            document.status = DocumentStatus.PARSING.value
            document.stage_records.append(
                {
                    "stage": DocumentStatus.PARSING.value,
                    "finished_at": get_beijing_now_str(),
                }
            )
            await repository.update_document(document)
            mark_stage("prepare")
            if ctx is not None:
                ctx["stage"] = DocumentStatus.PARSING.value

            await log(
                f"开始解析文档 · {document.title}",
                stage=DocumentStatus.PARSING.value,
                progress=8,
                status=DocumentStatus.PARSING.value,
                with_records=True,
            )

            parse_result = await document_parser.parse(
                file_bytes=file_bytes,
                filename=document.title,
                ctx=ctx,
            )

            content = parse_result.get("content", "") or ""
            mark_stage("parsing")

            # Word / PDF：MinerU 已产出 Markdown，把 md 落一份到对象存储并把 access_url 指向它。
            # 前端预览直接渲染 md（与 AI 回答同款样式），比 mammoth 转 HTML 更还原、排版更稳。
            #
            # 关键约束：切片的 source_start_line / source_end_line 记的就是这份 md 的行号，
            # 预览必须与切分同源，引用才能定位到原文。因此这里上传的 content 与下面交给
            # chunker 的必须是同一份文本 —— 切勿为了「保留原始排版」改成上传清洗前的版本，
            # 否则行号会与预览全线错位。
            suffix = Path(document.title or "").suffix.lower()
            if suffix in {".docx", ".pdf"} and content.strip():
                try:
                    md_object = parsed_md_object_name(document.uid)
                    md_bytes = content.encode("utf-8")
                    await minio_client.upload(md_object, md_bytes, "text/markdown; charset=utf-8")
                    document.access_url = build_object_url(md_object)
                    await repository.update_document(document)
                    await log(
                        f"已生成 Markdown 预览文件 · {_size_label(len(md_bytes))}",
                        stage=DocumentStatus.PARSING.value,
                        progress=96,
                        level="success",
                    )
                except Exception as exc:
                    # 上传失败不影响后续切块/索引，预览会回退为原文件（Word 转 HTML / 原生 PDF）
                    logger.warning("[Worker] Markdown 预览文件上传失败 %s: %s", document.uid, exc)
                    await log(
                        "Markdown 预览文件上传失败，预览将回退为原文件",
                        stage=DocumentStatus.PARSING.value,
                        progress=96,
                        level="warn",
                    )

            await log(
                f"解析完成 · 提取 {len(content):,} 个字符 · 耗时 {timings['parsing']}s",
                stage=DocumentStatus.PARSING.value,
                progress=100,
                level="success",
            )

            # ==========================
            #  RAG 第二阶段 - 文档切分
            # ==========================
            document.status = DocumentStatus.CHUNKING.value
            document.stage_records.append(
                {
                    "stage": DocumentStatus.CHUNKING.value,
                    "finished_at": get_beijing_now_str(),
                }
            )
            await repository.update_document(document)
            if ctx is not None:
                ctx["stage"] = DocumentStatus.CHUNKING.value

            await log(
                "开始切分：按语义结构生成父子切块",
                stage=DocumentStatus.CHUNKING.value,
                progress=0,
                status=DocumentStatus.CHUNKING.value,
                with_records=True,
            )

            chunk_result = await document_chunker.process(**parse_result)
            parent_chunk = [chunk for chunk in chunk_result if chunk.get("is_parent")]
            child_chunk = [chunk for chunk in chunk_result if not chunk.get("is_parent")]
            mark_stage("chunking")

            await log(
                f"切分完成 · 父块 {len(parent_chunk)} · 子块 {len(child_chunk)} · 耗时 {timings['chunking']}s",
                stage=DocumentStatus.CHUNKING.value,
                progress=100,
                level="success",
            )

            # 重新处理时必须先清掉上一轮的切块，否则新块会追加在旧块后面（检索重复命中）
            removed_chunks = await repository.delete_document_chunks(document_id)
            if removed_chunks:
                await log(
                    f"已清理上一轮遗留切块 {removed_chunks} 条",
                    stage=DocumentStatus.CHUNKING.value,
                    level="warn",
                )

            await log("正在写入切块数据", stage=DocumentStatus.CHUNKING.value, progress=100)
            knowledge_repository = KnowledgeRepository(session)
            saved_data = await knowledge_repository.save_parent_child_chunks(document_id, parent_chunk, child_chunk)
            db_parents = saved_data.get("parent_models", [])
            db_children = saved_data.get("child_models", [])

            await log(
                f"入库完成 · 父块 {len(db_parents)} · 子块 {len(db_children)}",
                stage=DocumentStatus.CHUNKING.value,
                level="success",
            )

            # ==========================
            #  RAG 第三阶段 - 切片向量化
            # ==========================
            document.status = DocumentStatus.EMBEDDING.value
            document.stage_records.append(
                {
                    "stage": DocumentStatus.EMBEDDING.value,
                    "finished_at": get_beijing_now_str(),
                }
            )
            await repository.update_document(document)
            if ctx is not None:
                ctx["stage"] = DocumentStatus.EMBEDDING.value

            await log(
                f"开始向量化 · {len(db_children)} 个子切块",
                stage=DocumentStatus.EMBEDDING.value,
                progress=0,
                status=DocumentStatus.EMBEDDING.value,
                with_records=True,
            )

            # 1. 根据子块正文和元数据构建 Embedding 输入。
            texts = [
                build_embedding_text(
                    content=chunk.content,
                    metadata=chunk.extra_meta,
                )
                for chunk in db_children
            ]

            # 2. 请求 Embedding 模型生成向量。
            vectors = await embedding_service.embed_documents(
                texts,
                ctx=ctx,
            )

            # 3. 组装 (数据库 ID, 向量) 列表。
            chunk_id_vector_pairs = [
                (chunk.id, vector)
                for chunk, vector in zip(db_children, vectors)
            ]

            # 4. 调用 Repository 的批量更新方法，一次性写入数据库
            await repository.bulk_update_embeddings(chunk_id_vector_pairs)
            mark_stage("embedding")

            await log(
                f"向量写入完成 · {len(chunk_id_vector_pairs)} 条 · 耗时 {timings['embedding']}s",
                stage=DocumentStatus.EMBEDDING.value,
                progress=100,
                level="success",
            )

            # 最终完成
            document.status = DocumentStatus.INDEXED.value
            document.stage_records.append(
                {
                    "stage": DocumentStatus.INDEXED.value,
                    "finished_at": get_beijing_now_str(),
                }
            )
            await repository.update_document(document)
            if ctx is not None:
                ctx["stage"] = DocumentStatus.INDEXED.value

            total_elapsed = round(time.monotonic() - started_at, 1)
            await log(
                f"索引构建完成 · 总耗时 {total_elapsed}s · {len(db_children)} 个切片已可检索",
                stage=DocumentStatus.INDEXED.value,
                progress=100,
                level="success",
                status=DocumentStatus.INDEXED.value,
                with_records=True,
            )

        except asyncio.CancelledError:
            # worker 被手动停止 / 任务被取消（CancelledError 不是 Exception 的子类，
            # 必须单独捕获）：把文档标记为失败并广播终态事件，
            # 否则前端的 SSE 进度连接会在没有任何终态事件的情况下一直挂起。
            logger.warning("[Worker] 文档任务被取消（worker 停止或任务被中断）")

            if document is not None:
                try:
                    document.status = DocumentStatus.FAILED.value
                    document.error_message = "后台处理任务被手动终止"
                    document.stage_records.append(
                        {
                            "stage": DocumentStatus.FAILED.value,
                            "finished_at": get_beijing_now_str(),
                        }
                    )
                    await repository.update_document(document)

                    await log(
                        "后台处理任务被手动终止",
                        stage=DocumentStatus.FAILED.value,
                        level="error",
                        status=DocumentStatus.FAILED.value,
                        with_records=True,
                    )
                except Exception:
                    # 停机过程中数据库/Redis 可能已不可用，尽力而为
                    logger.exception("[Worker] 取消任务时写回失败状态异常")

            raise

        except Exception as exc:
            logger.error(
                f"[Worker] 文档任务处理失败：{exc}",
                exc_info=True,
            )

            if document is not None:
                document.status = DocumentStatus.FAILED.value
                document.error_message = str(exc)[:500]
                document.stage_records.append(
                    {
                        "stage": DocumentStatus.FAILED.value,
                        "finished_at": get_beijing_now_str(),
                    }
                )
                await repository.update_document(document)

                try:
                    await log(
                        f"处理失败：{str(exc)[:120]}",
                        stage=DocumentStatus.FAILED.value,
                        level="error",
                        status=DocumentStatus.FAILED.value,
                        with_records=True,
                    )
                except Exception:
                    logger.exception(
                        "[Worker] 推送失败状态时发生异常"
                    )

        finally:
            if document is not None:
                try:
                    await local_cache.remove(document.uid, document.title)
                except Exception:
                    logger.exception(
                        "[Worker] 清理本地缓存失败"
                    )

                try:
                    process_logs = ctx.get("process_logs") if ctx else None
                    if process_logs:
                        document.process_logs = process_logs[-1000:]
                        await repository.update_document(document)
                        logger.info(
                            f"{len(document.process_logs)} 条执行日志已持久化"
                        )
                except Exception:
                    logger.exception(
                        "执行日志持久化失败"
                    )

            logger.info("========== 文档任务处理结束 ==========\n")


# =========================
# ARQ Worker 配置
# =========================
class WorkerSettings:
    """ARQ 命令行启动消费者时读取的配置类。"""

    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
    )
    functions = [process_document]
    max_jobs = 4
    queue_name = "rag-flow"
    max_tries = 1
    job_timeout = 600
    keep_result = 0

    @staticmethod
    async def on_startup(ctx: dict) -> None:
        """ARQ Worker 启动时初始化数据库引擎。"""
        database.init_db_engine()
        logger.info("ARQ Worker 启动完毕，数据库引擎初始化成功，正在监听队列")
