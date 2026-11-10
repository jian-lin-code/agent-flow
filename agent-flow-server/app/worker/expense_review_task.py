"""报销 AI 初审 ARQ Worker。"""

import mimetypes
from typing import Any
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core import database
from app.core.config import settings
from app.models.expense_claim import ExpenseClaim, ExpenseClaimStatus, Attachment
from app.models.expense_pre_review import ExpensePreReview
from app.services.expense_pre_review_service import ExpensePreReviewService
from app.repository.expense_pre_review_repository import ExpensePreReviewRepository
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.utils.minio_client import get_expense_minio_storage
from app.utils.logger import logger
from datetime import timedelta
from app.utils.datetime_helper import utc_now

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

REVIEW_TIMEOUT = timedelta(minutes=10)


def normalize_content_type(
    content_type: str | None,
    filename: str,
) -> str | None:
    """获取并规范化图片 MIME 类型。"""

    mime_type = (content_type or "").split(";")[0].strip().lower()

    if mime_type in SUPPORTED_IMAGE_TYPES:
        return mime_type

    # 部分文件上传时没有正确填写 Content-Type。
    guessed_type, _ = mimetypes.guess_type(filename)

    if guessed_type in SUPPORTED_IMAGE_TYPES:
        return guessed_type

    # 兼容 image/jpg。
    if mime_type == "image/jpg":
        return "image/jpeg"

    return None


def build_expense_data(claim: ExpenseClaim) -> dict[str, Any]:
    """将报销单及费用明细转换成模型输入数据。"""

    items = []

    for item in claim.items:
        items.append(
            {
                "expense_item_id": item.id,
                "category": item.category,
                "description": item.description,
                "amount": str(item.amount),
                "expense_date": (
                    item.expense_date.isoformat()
                    if item.expense_date
                    else None
                ),
            }
        )

    return {
        "claim_id": claim.id,
        "claim_no": claim.claim_no,
        "title": claim.title,
        "description": claim.description,
        "total_amount": str(claim.total_amount),
        "currency": claim.currency,
        "status": claim.status,
        "items": items,
    }


async def load_review_context(
    review_uid: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """读取报销单业务数据及附件元数据。

    返回普通 Python 数据，避免 ORM 对象脱离 Session 后访问属性。
    """

    async_session_factory = database.async_session

    if async_session_factory is None:
        raise RuntimeError("数据库 Session 尚未初始化")

    async with async_session_factory() as session:
        stmt = (
            select(ExpensePreReview)
            .where(ExpensePreReview.uid == review_uid)
        )

        result = await session.execute(stmt)
        review = result.scalar_one_or_none()

        if review is None:
            raise ValueError(f"初审记录不存在：{review_uid}")

        claim_stmt = (
            select(ExpenseClaim)
            .where(ExpenseClaim.id == review.claim_id)
            .options(
                selectinload(ExpenseClaim.items),
                selectinload(ExpenseClaim.attachments),
            )
        )

        claim_result = await session.execute(claim_stmt)
        claim = claim_result.scalar_one_or_none()

        if claim is None:
            raise ValueError(
                f"初审记录关联的报销单不存在：{review_uid}"
            )

        expense_data = build_expense_data(claim)

        attachments = [
            {
                "attachment_id": attachment.id,
                "expense_item_id": attachment.expense_item_id,
                "storage_path": attachment.storage_path,
                "file_name": attachment.original_filename,
                "content_type": attachment.content_type,
            }
            for attachment in claim.attachments
        ]

        return expense_data, attachments


async def download_expense_images(
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从 MinIO 下载报销单关联的发票图片。"""

    storage = get_expense_minio_storage()
    images: list[dict[str, Any]] = []

    for attachment in attachments:
        file_name = attachment["file_name"]

        content_type = normalize_content_type(
            attachment["content_type"],
            file_name,
        )

        # 第一版只处理视觉模型支持的图片格式。
        # PDF 等非图片附件暂不传给视觉模型。
        if content_type is None:
            logger.warning(
                f"跳过不支持的初审附件：{file_name}"
            )
            continue

        image_bytes = await storage.download(
            attachment["storage_path"]
        )

        if not image_bytes:
            raise ValueError(
                f"附件下载成功但文件内容为空：{file_name}"
            )

        expense_item_id = attachment["expense_item_id"]

        images.append(
            {
                "file_name": file_name,
                "content_type": content_type,
                "image_bytes": image_bytes,

                # ExpenseItem 当前只有 int 类型 id，没有 uid。
                # 这里将其转成字符串作为图片所属明细的标识，
                # 不代表数据库中真的存在 expense_item_uid。
                "expense_item_uid": (
                    str(expense_item_id)
                    if expense_item_id is not None
                    else None
                ),
            }
        )

    return images


async def mark_review_running(review_uid: str) -> bool:
    """使用数据库行锁抢占初审任务，防止重复执行。"""

    async_session_factory = database.async_session

    if async_session_factory is None:
        raise RuntimeError("数据库 Session 尚未初始化")

    async with async_session_factory() as session:
        repo = ExpensePreReviewRepository(session)

        stmt = (
            select(ExpensePreReview)
            .where(ExpensePreReview.uid == review_uid)
            .with_for_update()
        )

        result = await session.execute(stmt)
        review = result.scalar_one_or_none()

        if review is None:
            raise ValueError(f"初审记录不存在：{review_uid}")

        if review.status == "completed":
            logger.info(f"初审任务已经完成，跳过：{review_uid}")
            return False

        if review.status == "failed":
            logger.warning(f"初审任务已经失败，跳过：{review_uid}")
            return False

        if review.status == "running":
            started_at = review.started_at

            if started_at is None:
                logger.warning(
                    f"初审任务处于 running，但没有 started_at：{review_uid}"
                )
                return False

            elapsed = utc_now() - started_at

            if elapsed > REVIEW_TIMEOUT:
                await repo.mark_failed(
                    review,
                    error_message=(
                        f"初审任务执行超时，已超过 "
                        f"{REVIEW_TIMEOUT.total_seconds() / 60:.0f} 分钟。"
                    ),
                )
                await session.commit()

                logger.error(
                    f"初审任务执行超时，已标记 failed：{review_uid}"
                )

            else:
                logger.warning(
                    f"初审任务仍在执行，跳过重复任务：{review_uid}"
                )

            return False

        if review.status != "pending":
            raise ValueError(
                f"不支持的初审任务状态：{review.status}"
            )

        await repo.mark_running(review)
        await session.commit()

    return True


async def save_review_result(
    review_uid: str,
    *,
    decision: str,
    opinion: str,
    problems: list[str],
    model_name: str,
    risk_level: str | None = None,
    evidence: str | None = None,
    is_document_valid: bool = True,
    extracted_data: dict | None = None,
) -> None:
    """保存 AI 初审结果。

    AI 预审结论为 fail（拦截）时，直接把报销单流转为 rejected（自动驳回）：
    预审都没通过的单据不再进入人工审批环节，管理员也无法再对该单据审批
    （审批接口对非 pending_approval 状态返回 409）。AI 预审记录本身
    （result/problems/opinion）即驳回依据，approver_id 非空约束下
    不伪造人工审批记录。
    """

    async_session_factory = database.async_session

    if async_session_factory is None:
        raise RuntimeError("数据库 Session 尚未初始化")

    async with async_session_factory() as session:
        repo = ExpensePreReviewRepository(session)

        review = await repo.get_by_uid(review_uid)

        if review is None:
            raise ValueError(f"初审记录不存在：{review_uid}")

        await repo.mark_completed(
            review,
            result=decision,
            risk_level=risk_level,
            summary=opinion,
            result_data={
                "problems": problems,
                "evidence": evidence,
                "is_document_valid": is_document_valid,
                "extracted_data": extracted_data or {},
            },
            model_name=model_name,
        )

        # AI 拦截 → 自动驳回（行锁防并发；仅 pending_approval 状态流转，
        # 避免覆盖已完结单据的异常场景）。
        if decision == "fail":
            claim_result = await session.execute(
                select(ExpenseClaim)
                .where(ExpenseClaim.id == review.claim_id)
                .with_for_update()
            )
            claim = claim_result.scalar_one_or_none()

            if claim is None:
                logger.error(
                    f"AI 预审拦截后未找到关联报销单：claim_id={review.claim_id}"
                )
            elif claim.status == ExpenseClaimStatus.PENDING_APPROVAL.value:
                claim.status = ExpenseClaimStatus.REJECTED.value
                logger.info(
                    f"AI 预审拦截，报销单自动驳回："
                    f"claim_id={claim.id} claim_no={claim.claim_no}"
                )
            else:
                logger.warning(
                    f"AI 预审拦截，但报销单状态为 {claim.status}，"
                    f"跳过自动驳回：claim_id={review.claim_id}"
                )

        await session.commit()


async def mark_review_failed(
    review_uid: str,
    error_message: str,
) -> None:
    """记录初审任务失败。"""

    async_session_factory = database.async_session

    if async_session_factory is None:
        raise RuntimeError("数据库 Session 尚未初始化")

    async with async_session_factory() as session:
        repo = ExpensePreReviewRepository(session)

        review = await repo.get_by_uid(review_uid)

        if review is None:
            logger.error(
                f"无法记录初审失败，记录不存在：{review_uid}"
            )
            return

        # 已完成的任务不能被后续异常覆盖成 failed。
        if review.status == "completed":
            logger.warning(
                f"初审记录已经完成，不覆盖状态：{review_uid}"
            )
            return

        await repo.mark_failed(
            review,
            error_message=error_message[:4000],
        )

        await session.commit()


async def process_expense_pre_review(
    ctx: dict[str, Any],
    review_uid: str,
) -> dict[str, Any]:
    """执行一条报销 AI 初审任务。"""

    logger.info(
        f"开始执行报销 AI 初审：{review_uid}"
    )

    # 1. 抢占任务，防止重复执行。
    should_run = await mark_review_running(review_uid)

    if not should_run:
        return {
            "success": True,
            "skipped": True,
            "review_uid": review_uid,
        }

    try:
        # 2. 加载报销单和附件元数据。
        expense_data, attachments = await load_review_context(
            review_uid
        )

        # 3. 下载发票图片。
        images = await download_expense_images(attachments)

        model_name = settings.VL_PLUS_MODEL

        # 【修复点：所有变量提供默认值，防止分支遗漏导致 UnboundLocalError】
        decision = "manual_review"
        opinion = ""
        problems = []
        risk_level = None
        evidence = None
        is_document_valid = True
        extracted_data = {}

        # 4. 没有可用图片时，明确记录人工复核。
        # 缺少初审材料不属于模型调用异常。
        if not images:
            opinion = (
                "未找到支持的发票图片，无法完成自动初审，"
                "请人工检查报销附件。"
            )
            problems = [
                "没有可供视觉模型识别的发票图片"
            ]

        else:
            async_session_factory = database.async_session

            if async_session_factory is None:
                raise RuntimeError("数据库 Session 尚未初始化")

            async with async_session_factory() as session:
                pre_review_service = ExpensePreReviewService(
                    repository=ExpensePreReviewRepository(session),
                    claim_repository=ExpenseClaimRepository(session),
                    redis=ctx["redis"],
                )

                review_result = await pre_review_service.review_expense(
                    expense_data=expense_data,
                    images=images,
                )

            # 处理枚举或字符串兼容
            decision = review_result.decision.value if hasattr(review_result.decision, "value") else review_result.decision
            opinion = review_result.opinion
            risk_level = review_result.risk_level
            problems = review_result.problems
            evidence = review_result.evidence
            is_document_valid = review_result.is_document_valid
            extracted_data = review_result.extracted_data

        # 6. 持久化初审结果。
        await save_review_result(
            review_uid,
            decision=decision,
            opinion=opinion,
            problems=problems,
            model_name=model_name,
            risk_level=risk_level,
            evidence=evidence,
            is_document_valid=is_document_valid,
            extracted_data=extracted_data,
        )

        logger.info(
            f"报销 AI 初审完成 | "
            f"review_uid={review_uid} | "
            f"decision={decision} | "
            f"risk_level={risk_level} | "
            f"is_document_valid={is_document_valid} | "
            f"problems={problems} | "
            f"evidence={evidence} | "
            f"extracted_data={extracted_data} | "
            f"opinion={opinion}"
        )

        return {
            "success": True,
            "review_uid": review_uid,
            "decision": decision,
        }

    except Exception as exc:
        logger.exception(
            f"报销 AI 初审执行失败：{review_uid}"
        )

        try:
            await mark_review_failed(
                review_uid,
                error_message=str(exc),
            )
        except Exception:
            logger.exception(
                f"保存初审失败状态时发生异常：{review_uid}"
            )

        # 任务失败已经写入数据库，不让 ARQ 再次重复执行。
        raise


class WorkerSettings:
    """报销 AI 初审独立 Worker 配置。"""

    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
    )

    functions = [
        process_expense_pre_review,
    ]

    queue_name = "expense-review"

    max_jobs = 2
    max_tries = 1
    job_timeout = 300
    keep_result = 0

    @staticmethod
    async def on_startup(ctx: dict[str, Any]) -> None:
        database.init_db_engine()

        logger.info("Expense Review Worker 已启动")

    @staticmethod
    async def on_shutdown(ctx: dict[str, Any]) -> None:
        await database.close_db_engine()

        logger.info("Expense Review Worker 已关闭")