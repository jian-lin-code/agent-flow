"""报销单 AI 初审业务服务。"""

import base64
import json
from typing import Any

from arq.connections import ArqRedis
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent_graph.prompt_manager import render_prompt
from app.core import database
from app.core.config import settings
from app.core.exceptions import BizException, ErrorCode
from app.models.expense_pre_review import PreReviewStatus
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.repository.expense_pre_review_repository import ExpensePreReviewRepository
from app.schemas.expense_review import ExpensePreReviewResult
from app.utils.llm import get_llm_model


class ExpensePreReviewService:
    """负责报销单 AI 初审业务，包括记录创建、任务投递和结果查询。"""

    PROMPT_VERSION, QUEUE_NAME, JOB_NAME = "v1", "expense-review", "process_expense_pre_review"

    def __init__(
        self,
        repository: ExpensePreReviewRepository,
        claim_repository: ExpenseClaimRepository,
        redis: ArqRedis,
    ):
        self.repository, self.claim_repository, self.redis = repository, claim_repository, redis
        self.system_prompt = render_prompt("review/pre_review.j2")

    async def create_review_record(self, *, claim_id: int):
        """在当前数据库事务中创建初审记录（不 commit、不 rollback、不投递 ARQ）。"""
        claim = await self.claim_repository.get_by_id(claim_id=claim_id, for_update=True)
        if not claim or claim.status != "pending_approval":
            raise ValueError(f"报销单不存在或状态不允许初审，当前状态：{claim.status if claim else 'None'}")

        if active_review := await self.repository.get_active_by_claim_id(claim_id):
            raise ValueError(f"已有初审任务正在执行，review_uid={active_review.uid}")

        return await self.repository.create(
            claim_id=claim_id, model_name=settings.VL_PLUS_MODEL, prompt_version=self.PROMPT_VERSION
        )

    async def enqueue_review(self, *, review_uid: str) -> None:
        """将已有初审记录投递到独立 ARQ 队列。"""
        try:
            job = await self.redis.enqueue_job(
                self.JOB_NAME,
                review_uid,
                _queue_name=self.QUEUE_NAME,
                _job_id=f"expense-pre-review:{review_uid}",
            )
            if job is None:
                raise RuntimeError("ARQ 任务投递未成功，任务 ID 已存在")
        except Exception as exc:
            raise RuntimeError(f"初审记录已创建，但 ARQ 投递失败：{exc}") from exc

    async def mark_enqueue_failed(self, *, review_uid: str, error_message: str) -> None:
        """使用独立数据库 Session 标记 ARQ 投递失败。"""
        if (session_factory := database.async_session) is None:
            raise RuntimeError("数据库 Session 尚未初始化")

        async with session_factory() as session, session.begin():
            repository = ExpensePreReviewRepository(session)
            if not (review := await repository.get_by_uid(review_uid)):
                raise RuntimeError(f"初审记录不存在：{review_uid}")
            if review.status != PreReviewStatus.COMPLETED.value:
                await repository.mark_failed(review, error_message=error_message)

    async def submit_review(self, *, claim_id: int):
        """独立创建初审记录并投递 ARQ 任务。"""
        review = await self.create_review_record(claim_id=claim_id)
        await self.repository.commit()
        await self.enqueue_review(review_uid=review.uid)
        return review

    async def retry_review(self, *, claim_id: int, user) -> dict[str, Any]:
        """重新触发一次 AI 初审。

        初审失败（模型超时、发票图片异常等）后 status=failed 即终态，
        原先没有任何重试入口，该单据会永远没有预审结果。这里允许在
        单据仍处于 pending_approval 时手动重跑。
        """
        applicant_id = None if user.role == "admin" else user.id
        claim = await self.claim_repository.get_by_id(
            claim_id=claim_id, applicant_id=applicant_id
        )
        if not claim:
            raise BizException(
                "报销单不存在，或无权查看该报销单。",
                code=ErrorCode.NOT_FOUND,
            )

        if claim.status != "pending_approval":
            raise BizException(
                "当前报销单状态不允许重新初审。",
                code=ErrorCode.CONFLICT,
            )

        latest = await self.repository.get_latest_by_claim_id(claim_id=claim_id)
        if latest is not None and latest.status in (
            PreReviewStatus.PENDING.value,
            PreReviewStatus.RUNNING.value,
        ):
            raise BizException(
                "AI 初审正在进行中，请稍后再试。",
                code=ErrorCode.CONFLICT,
            )

        try:
            review = await self.create_review_record(claim_id=claim_id)
        except ValueError as exc:
            raise BizException(str(exc), code=ErrorCode.CONFLICT) from exc

        await self.repository.commit()

        try:
            await self.enqueue_review(review_uid=review.uid)
        except Exception as exc:
            try:
                await self.mark_enqueue_failed(
                    review_uid=review.uid, error_message=str(exc)
                )
            except Exception:
                pass
            raise BizException(
                "初审任务投递失败，请稍后重试。",
                code=ErrorCode.INTERNAL_ERROR,
            ) from exc

        return {
            "claim_id": claim.id,
            "claim_no": claim.claim_no,
            "review": {
                "uid": review.uid,
                "status": PreReviewStatus.PENDING.value,
                "enqueued": True,
            },
        }

    async def get_latest_review(self, *, claim_id: int, user) -> dict[str, Any]:
        """查询指定报销单的最新 AI 初审结果。

        普通用户只能查看自己的报销单；admin 可查看任意报销单
        （待审批页面的 AI 预审抽屉需要）。
        """
        applicant_id = None if user.role == "admin" else user.id
        claim = await self.claim_repository.get_by_id(claim_id=claim_id, applicant_id=applicant_id)
        if not claim:
            raise BizException(
                "报销单不存在，或无权查看该报销单。",
                code=ErrorCode.NOT_FOUND,
            )

        review = await self.repository.get_latest_by_claim_id(claim_id=claim_id)

        return {
            "claim_id": claim.id,
            "claim_no": claim.claim_no,
            "review": {
                "uid": review.uid, "status": review.status, "result": review.result,
                "risk_level": review.risk_level,
                "summary": review.summary, "result_data": review.result_data or {},
                "model_name": review.model_name, "prompt_version": review.prompt_version,
                "started_at": review.started_at, "finished_at": review.finished_at,
                "error_message": review.error_message, "created_at": review.created_at, "updated_at": review.updated_at,
            } if review else None,
        }

    async def review_expense(
        self, *, expense_data: dict[str, Any], images: list[dict[str, Any]]
    ) -> ExpensePreReviewResult:
        """调用视觉模型完成报销单 AI 初审。"""
        if not expense_data or not images:
            raise ValueError("报销单业务数据或初审发票图片不能为空。")

        supported_types = {"image/jpeg", "image/png", "image/webp"}

        # 构建文本部分
        content = [
            {
                "type": "text",
                "text": f"以下是报销单业务数据，请结合后续发票图片进行初审：\n{json.dumps(expense_data, ensure_ascii=False, indent=2)}"
            }
        ]

        # 构建图片部分
        for image in images:
            image_bytes = image.get("image_bytes")
            content_type = (image.get("content_type") or "").split(";")[0].strip().lower()

            if not image_bytes:
                raise ValueError(f"发票图片内容为空：{image.get('file_name')}")
            if content_type not in supported_types:
                raise ValueError(f"不支持的发票图片格式：{content_type}")

            # 【修复点1：增加 bytes 类型校验，防止 minio 返回文件句柄/流】
            if not isinstance(image_bytes, bytes):
                try:
                    image_bytes = image_bytes.read()
                except AttributeError:
                    raise ValueError(f"无法处理的图片数据类型：{type(image_bytes)}")

            base64_data = base64.b64encode(image_bytes).decode("utf-8")

            content.extend([
                {
                    "type": "text",
                    "text": f"发票图片：{image.get('file_name')}\n关联费用明细 ID：{image.get('expense_item_uid') or '整单附件'}"
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{content_type};base64,{base64_data}", "detail": "high"}
                }
            ])

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

        llm = get_llm_model(temp=0, model_name=settings.VL_PLUS_MODEL)
        structured_llm = llm.with_structured_output(ExpensePreReviewResult)

        result = await structured_llm.ainvoke(messages)

        # 如果底层已经返回了 Pydantic 实例，直接返回；否则兜底做一次验证
        return result if isinstance(result, ExpensePreReviewResult) else ExpensePreReviewResult.model_validate(result)