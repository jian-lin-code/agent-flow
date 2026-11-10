import re
import uuid
from copy import deepcopy
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any, Callable
from uuid import uuid4

from arq import ArqRedis
from fastapi import UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from app.services.conversations_service import ConversationMessageService
from app.models.expense_claim import ExpenseClaimStatus
from app.models.expense_pre_review import PreReviewStatus
from app.repository.conversations_repository import ConversationsRepository
from app.core import database
from app.core.exceptions import BizException, ErrorCode
from app.models import ExpenseClaim, ExpenseItem, Conversation, Attachment, User, Message
from app.models.business_task import (
    BusinessTask,
    BusinessTaskStatus,
    BusinessTaskType, BusinessTaskAttachment,
)
from app.repository.business_task_repository import BusinessTaskRepository
from app.repository.expense_claim_repository import ExpenseClaimRepository
from app.repository.workflow_repository import WorkflowRepository
from app.utils.datetime_helper import utc_now
from app.utils.logger import logger
from app.utils.minio_client import get_expense_minio_storage
from app.utils.task_ui import _build_task_ui_payload
from app.repository.expense_pre_review_repository import (
    ExpensePreReviewRepository,
)
from app.services.expense_pre_review_service import (
    ExpensePreReviewService,
)

UPLOADABLE_STATUSES = {
    BusinessTaskStatus.COLLECTING.value,
    BusinessTaskStatus.WAITING_CONFIRMATION.value,
}

# 这些状态的任务在组装响应时实时重算 missing_fields（附件增删后保证准确）。
# cancelled 也纳入：取消时数据库 missing_fields 已被清空，恢复任务时必须重算才能还原真实缺失。
REALTIME_MISSING_STATUSES = UPLOADABLE_STATUSES | {
    BusinessTaskStatus.CANCELLED.value,
}

ALLOWED_FILES = {
    ".pdf": {"content_type": "application/pdf", "signature": lambda data: data.startswith(b"%PDF-")},
    ".jpg": {"content_type": "image/jpeg", "signature": lambda data: data.startswith(b"\xff\xd8\xff")},
    ".jpeg": {"content_type": "image/jpeg", "signature": lambda data: data.startswith(b"\xff\xd8\xff")},
    ".png": {"content_type": "image/png", "signature": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")},
}

MAX_FILE_SIZE = 10 * 1024 * 1024

def calculate_expense_total(expense_items: list[dict]) -> str:
    """根据有效金额计算费用总额，保留两位小数。"""
    total = Decimal("0.00")
    for item in expense_items:
        try:
            amount = Decimal(str(item.get("amount")))
            if amount.is_finite() and amount > 0:
                total += amount
        except (InvalidOperation, TypeError, ValueError):
            continue
    return str(total.quantize(Decimal("0.01")))


class BusinessTaskService:
    """报销业务服务，负责协调报销相关的数据操作。"""

    def __init__(self, session_factory: Callable[[], AsyncSession] | None = None,redis: ArqRedis | None = None,):
        self.session_factory = session_factory
        self.redis = redis
    def _get_session_factory(self):
        session_factory = self.session_factory or database.async_session
        if session_factory is None:
            raise RuntimeError("数据库尚未初始化。")
        return session_factory

    # ================= 对象存储清理 =================

    async def _remove_storage_objects(self, storage_paths: list[str]) -> None:
        """事务提交后清理 MinIO 对象。

        清理失败只记录日志：数据库记录已经删除，残留对象不影响业务，
        由后续的对象存储生命周期策略兜底。
        """
        paths = list(dict.fromkeys(path for path in storage_paths if path))
        if not paths:
            return

        try:
            storage = get_expense_minio_storage()
        except Exception:
            logger.exception("初始化对象存储失败，跳过附件文件清理：%s", paths)
            return

        for path in paths:
            try:
                await storage.remove(path)
            except Exception:
                logger.exception("清理附件对象存储文件失败：%s", path)

    @staticmethod
    def _normalize_category(value: Any) -> str:
        """归一化费用类别，便于占位明细与新增明细的比较。"""
        if value is None:
            return ""
        return re.sub(r"\s+", "", str(value)).strip()

    @staticmethod
    def _item_has_amount(item: dict[str, Any]) -> bool:
        """判断明细是否已经填写了有效金额。"""
        try:
            amount = Decimal(str(item.get("amount")))
        except (InvalidOperation, TypeError, ValueError):
            return False
        return amount.is_finite() and amount > 0

    def _find_mergeable_placeholder(
        self,
        current_items: list[dict[str, Any]],
        *,
        category: str | None,
        exclude_ids: set[str],
    ) -> dict[str, Any] | None:
        """找出可以被本次新增信息补全的「占位明细」。

        场景：用户第一句「我要报销打车费」会生成一条金额为空的交通费明细，
        第二句「打车 120 元」时模型倾向于再新增一条，导致重复条目。
        这里优先把金额等字段补进已有的占位明细，避免出现两条同类费用。
        """
        placeholders = [
            item
            for item in current_items
            if item.get("id")
            and str(item["id"]) not in exclude_ids
            and not self._item_has_amount(item)
        ]

        if not placeholders:
            return None

        normalized_category = self._normalize_category(category)

        if normalized_category:
            same_category = [
                item for item in placeholders
                if self._normalize_category(item.get("category")) == normalized_category
            ]
            if same_category:
                return same_category[0]

            no_category = [
                item for item in placeholders
                if not self._normalize_category(item.get("category"))
            ]
            # 只有唯一一条无类别占位时才敢合并，避免把金额填错明细。
            if len(placeholders) == 1 and len(no_category) == 1:
                return no_category[0]

            return None

        # 用户没有给出类别时，仅在唯一的占位明细上合并。
        if len(placeholders) == 1:
            return placeholders[0]

        return None

    # ================= 核心复用工具函数 =================

    async def _get_locked_conversation(self, session: AsyncSession, conversation_id: int, user_id: int) -> Conversation:
        """通用方法：锁定会话并校验归属。"""
        result = await session.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .with_for_update()
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise RuntimeError("会话不存在，或不属于当前用户。")
        return conversation

    # 新计算缺失字段、更新任务状态并保存
    async def _refresh_task_state(self,session: AsyncSession,task: BusinessTask,expense_items: list[dict]) -> list[str]:
        """
        通用方法：重新计算缺失字段、更新任务状态并保存。
        （替代了你在多个方法里重复写的计算+赋值逻辑）
        """
        missing_fields = await self._calculate_missing_fields_with_attachments(
            session=session,
            business_task_id=task.id,
            expense_items=expense_items,
        )
        task.missing_fields = missing_fields
        task.status = (
            BusinessTaskStatus.COLLECTING.value
            if missing_fields
            else BusinessTaskStatus.WAITING_CONFIRMATION.value
        )
        # 注意：调用方负责设置 draft_data 并调用 await repository.update(task)
        return missing_fields

    # ================= 业务方法 =================

    # 根据工作流执行记录创建报销业务草稿。
    async def create_business_task_from_workflow(self, *, user_id: int, conversation_id: int, workflow_run_uid: str) -> dict[str, Any]:
        session_factory = self._get_session_factory()
        async with session_factory() as session:
            async with session.begin():
                conversation = await self._get_locked_conversation(session, conversation_id, user_id)
                workflow_repo = WorkflowRepository(session)
                task_repo = BusinessTaskRepository(session)

                workflow_run = await workflow_repo.get_by_uid(
                    run_uid=workflow_run_uid, user_id=user_id,
                    conversation_id=conversation_id, for_update=True
                )
                if workflow_run is None:
                    raise RuntimeError("当前工作流不存在，或不属于当前用户和会话。")

                if workflow_run.business_task_id is not None:
                    existing_task = await task_repo.get_by_id(
                        task_id=workflow_run.business_task_id, user_id=user_id,
                        conversation_id=conversation_id
                    )
                    if existing_task is None:
                        raise RuntimeError("当前工作流已关联业务任务，但任务记录不存在。")
                    conversation.active_business_task_uid = existing_task.uid
                    return {"selected_business_task": await self._build_business_task_response(session, existing_task)}

                task = BusinessTask(
                    conversation_id=conversation_id,
                    created_by=user_id,
                    task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT.value,
                    title="报销申请",
                    status=BusinessTaskStatus.COLLECTING.value,
                    draft_data={},
                    missing_fields=[],
                )
                await task_repo.add_without_commit(task)
                conversation.active_business_task_uid = task.uid
                workflow_run.business_task_id = task.id
                await workflow_repo.update(workflow_run)

                selected_task = await self._build_business_task_response(session, task)
        return {"selected_business_task": selected_task}

    # 获取报销草稿快照并同步任务状态。
    async def get_task_snapshot(self, *, task_uid: str, user_id: int, conversation_id: int, trigger_message_uid: str | None = None) -> dict[str, Any]:
        session_factory = self._get_session_factory()
        async with session_factory() as session:
            async with session.begin():
                task_repo = BusinessTaskRepository(session)
                task = await task_repo.get_by_uid(
                    task_uid=task_uid, user_id=user_id, conversation_id=conversation_id,
                    task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT, for_update=True
                )
                if task is None or task.status not in UPLOADABLE_STATUSES:
                    raise RuntimeError("报销任务不存在、不属于当前会话，或当前状态不允许继续补充信息。")

                draft_data = deepcopy(task.draft_data or {})
                expense_items = draft_data.get("expense_items") or []

                # 校验明细格式
                if not isinstance(expense_items, list) or any(not isinstance(i, dict) for i in expense_items):
                    raise ValueError("报销费用明细格式不正确。")

                # 刷新状态
                real_missing = await self._refresh_task_state(session, task, expense_items)
                task.draft_data = draft_data
                await task_repo.update(task)

                processed_message_uids = draft_data.get("_processed_message_uids", [])
                already_processed = bool(trigger_message_uid) and trigger_message_uid in processed_message_uids

                return {
                    "task_uid": task.uid,
                    "uid": task.uid,
                    "title": task.title,
                    "task_type": task.task_type,
                    "status": task.status,
                    "missing_fields": real_missing,
                    "draft_data": draft_data,
                    "selected_business_task": await self._build_business_task_response(
                        session, task, missing_fields=real_missing    # 传进去
                    ),
                    "already_processed": already_processed,
                }

    # 查询会话内的全部业务任务，供前端"相关任务"面板展示。
    async def list_conversation_tasks(
        self,
        *,
        conversation_uid: str,
        user_id: int,
    ) -> dict[str, Any]:
        session_factory = self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.uid == conversation_uid,
                    Conversation.user_id == user_id,
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation is None:
                raise BizException(
                    code=ErrorCode.NOT_FOUND,
                    msg="会话不存在或无权访问。",
                )

            task_repo = BusinessTaskRepository(session)
            tasks = await task_repo.list_by_conversation(
                user_id=user_id,
                conversation_id=conversation.id,
            )

            items: list[dict[str, Any]] = []
            for task in tasks:
                claim = None
                if task.claim_id is not None:
                    claim = await task_repo.get_claim_by_id(
                        claim_id=task.claim_id,
                        applicant_id=user_id,
                    )
                try:
                    items.append(
                        await self._build_business_task_response(
                            session,
                            task,
                            claim=claim,
                        )
                    )
                except Exception:
                    # 单条任务数据异常不应拖垮整个面板，跳过并记录。
                    logger.exception(
                        "构造会话任务卡片失败：task_uid=%s",
                        task.uid,
                    )

            return {
                "conversation_uid": conversation_uid,
                "active_business_task_uid": conversation.active_business_task_uid,
                "total": len(items),
                "items": items,
            }

    # 将 LLM 提取的费用操作应用到报销草稿。
    async def apply_expense_operations(self, *, task_uid: str, user_id: int, conversation_id: int,trigger_message_uid: str | None, operations: list[dict[str, Any]]) -> dict[str, Any]:
        session_factory = self._get_session_factory()
        # 事务提交后再清理的对象存储文件（被删除明细的附件）
        removed_storage_paths: list[str] = []
        async with session_factory() as session:
            async with session.begin():
                task_repo = BusinessTaskRepository(session)
                task = await task_repo.get_by_uid(
                    task_uid=task_uid, user_id=user_id, conversation_id=conversation_id,
                    task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT, for_update=True
                )
                if task is None or task.status not in UPLOADABLE_STATUSES:
                    raise RuntimeError("报销任务不存在、不属于当前会话，或当前状态不允许继续补充信息。")

                draft_data = deepcopy(task.draft_data or {})
                processed_message_uids = list(draft_data.get("_processed_message_uids", []))
                current_items = list(draft_data.get("expense_items", []) or [])

                # 幂等检查
                if trigger_message_uid and trigger_message_uid in processed_message_uids:
                    return {"already_processed": True, "added_count": 0, "updated_count": 0,
                            "added_items": [], "updated_items": [],"deleted_items": [],"deleted_count": 0,
                            "total_amount": draft_data.get("total_amount", "0.00"),
                            "expense_items": current_items,
                            "selected_business_task": await self._build_business_task_response(session, task)}

                if not operations:
                    return {"already_processed": False, "added_count": 0, "updated_count": 0,
                            "added_items": [], "updated_items": [],"deleted_items": [],"deleted_count": 0,
                            "total_amount": draft_data.get("total_amount", "0.00"),
                            "expense_items": current_items,
                            "selected_business_task": await self._build_business_task_response(session, task)}

                # 建立 ID 映射
                item_map, item_ids = {}, []
                for item in current_items:
                    item_id = str(item.get("id"))
                    if not item_id or item_id in item_ids:
                        raise ValueError("报销草稿中存在格式错误或重复的费用明细 ID。")
                    item_ids.append(item_id)
                    item_map[item_id] = item

                added_items = []
                updated_items = []
                merged_items = []
                deleted_items = []

                updated_target_ids = set()
                deleted_target_ids = set()

                # 处理操作 (精简了冗长的校验)
                for operation in operations:
                    action = operation.get("action")
                    if action == "add":
                        raw_amount = operation.get("amount")
                        amount = Decimal(str(raw_amount)).quantize(Decimal("0.01")) if raw_amount and str(
                            raw_amount).strip() else None
                        # 只有在 amount 不为空的时候，才去判断它是否合法
                        if amount is not None and (not amount.is_finite() or amount <= 0):
                            raise ValueError("新增费用的金额必须大于 0。")

                        new_item = {
                            "id": str(uuid.uuid4()),
                            "category": str(operation["category"]).strip() or None if operation.get(
                                "category") else None,
                            "amount": str(amount) if amount else None,
                            "description": str(operation["description"]).strip() or None if operation.get(
                                "description") else None,
                            "expense_date": date.fromisoformat(
                                str(operation["expense_date"]).strip()).isoformat() if operation.get(
                                "expense_date") and str(operation["expense_date"]).strip() else None
                        }

                        # 优先补全已有的「占位明细」，而不是新增重复条目。
                        merge_target = None
                        if amount is not None:
                            merge_target = self._find_mergeable_placeholder(
                                current_items,
                                category=new_item["category"],
                                exclude_ids=updated_target_ids | deleted_target_ids,
                            )

                        if merge_target is not None:
                            merge_target["amount"] = str(amount)
                            for field in ("category", "description", "expense_date"):
                                if new_item.get(field) and not merge_target.get(field):
                                    merge_target[field] = new_item[field]
                            updated_target_ids.add(str(merge_target["id"]))
                            merged_items.append(deepcopy(merge_target))
                            continue

                        current_items.append(new_item)
                        item_map[new_item["id"]] = new_item
                        added_items.append(new_item)

                    elif action == "update":
                        target_id = str(operation.get("target_item_id"))
                        if target_id not in item_map or target_id in updated_target_ids:
                            raise ValueError("需要更新的费用不存在或重复更新。")

                        target_item = item_map[target_id]
                        changed = False
                        for field in ["category", "amount", "description", "expense_date"]:
                            if operation.get(field) is not None:
                                val = operation[field]
                                if field == "amount":
                                    val = str(Decimal(str(val)).quantize(Decimal("0.01"))) if str(val).strip() else None
                                    if val:
                                        updated_amount = Decimal(val)
                                        if not updated_amount.is_finite() or updated_amount <= 0:
                                            raise ValueError("修改后的金额必须大于 0。")
                                elif field == "expense_date":
                                    val = date.fromisoformat(str(val).strip()).isoformat() if str(val).strip() else None
                                else:
                                    val = str(val).strip() or None
                                target_item[field] = val
                                changed = True
                        if not changed:
                            raise ValueError("更新费用时没有提供需要修改的字段。")
                        updated_target_ids.add(target_id)
                        updated_items.append(deepcopy(target_item))
                    elif action == "delete":
                        target_id = operation.get("target_item_id")
                        if not target_id:
                            raise ValueError("删除费用时必须提供目标费用 ID。")
                        target_id = str(target_id)
                        if target_id not in item_map:
                            raise ValueError("需要删除的费用明细不存在，请刷新后重试。")
                        if target_id in deleted_target_ids:
                            raise ValueError("同一条费用明细不能重复删除。")
                        # 不允许先修改后删除，避免同一条明细在一次操作中被重复处理。
                        if target_id in updated_target_ids:
                            raise ValueError("同一条费用明细不能同时修改和删除。")
                        target_item = item_map[target_id]
                        # 记录被删除的原始明细
                        deleted_items.append(deepcopy(target_item))
                        # 从当前费用明细中删除
                        current_items.remove(target_item)
                        # 从 ID 映射中移除，防止后续操作继续引用
                        del item_map[target_id]
                        deleted_target_ids.add(target_id)

                        # 级联删除该明细的附件，避免遗留孤儿附件导致单据永久无法提交。
                        removed_attachments = await task_repo.delete_attachments_by_task_and_item(
                            business_task_id=task.id,
                            expense_item_uid=target_id,
                        )
                        removed_storage_paths.extend(
                            attachment.storage_path
                            for attachment in removed_attachments
                            if attachment.storage_path
                        )

                # 重新计算并保存
                real_missing = await self._refresh_task_state(session, task, current_items)

                # 更新总金额
                total_amount = sum((Decimal(str(i["amount"])) for i in current_items if i.get("amount")),
                                   Decimal("0.00")).quantize(Decimal("0.01"))
                draft_data["expense_items"] = current_items
                draft_data["total_amount"] = str(total_amount)

                if trigger_message_uid:
                    processed_message_uids.append(trigger_message_uid)
                draft_data["_processed_message_uids"] = processed_message_uids
                task.draft_data = draft_data
                await task_repo.update(task)

                result = {
                    "already_processed": False,
                    "added_count": len(added_items), "updated_count": len(updated_items),"deleted_count": len(deleted_items),
                    "added_items": added_items, "updated_items": updated_items,
                    "merged_items": merged_items, "merged_count": len(merged_items),
                    "deleted_items": deleted_items,
                    "total_amount": str(total_amount), "expense_items": current_items,
                    "selected_business_task":  await self._build_business_task_response(
                        session, task, missing_fields=real_missing
                    ),
                }

            # 事务已提交，再清理被删除附件在 MinIO 中的文件（失败不影响业务）。
            await self._remove_storage_objects(removed_storage_paths)

        return result

    # 确认报销草稿并创建正式报销单。
    async def confirm_business_task(self, *, task_uid: str, user_id: int, conversation_id: int) -> dict[str, Any]:
        session_factory = self._get_session_factory()
        # 事务提交后再清理的孤儿附件（明细已删除但附件记录残留）
        orphan_storage_paths: list[str] = []
        async with session_factory() as session:
            async with session.begin():
                conversation = await self._get_locked_conversation(session, conversation_id, user_id)
                task_repo = BusinessTaskRepository(session)
                task = await task_repo.get_by_uid(
                    task_uid=task_uid, user_id=user_id, conversation_id=conversation_id,
                    task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT, for_update=True
                )
                if task is None:
                    raise RuntimeError("报销任务不存在，或不属于当前用户和会话。")

                if task.claim_id is not None:
                    existing_claim = await task_repo.get_claim_by_id(claim_id=task.claim_id, applicant_id=user_id)
                    if existing_claim is None:
                        raise RuntimeError("当前报销任务已关联报销单，但正式报销单不存在。")
                    return {"already_confirmed": True, "claim_id": existing_claim.id,
                            "claim_no": existing_claim.claim_no,
                            "status": existing_claim.status, "claim_status": existing_claim.status,
                            "total_amount": str(existing_claim.total_amount),
                            "selected_business_task": await self._build_business_task_response(session, task,
                                                                                               existing_claim)}

                if task.status != BusinessTaskStatus.WAITING_CONFIRMATION.value:
                    raise RuntimeError("当前报销任务尚未完成信息收集，或已经处理，不能确认提交。")

                draft_data = deepcopy(task.draft_data or {})
                expense_items = draft_data.get("expense_items") or []

                missing_fields = await self._calculate_missing_fields_with_attachments(
                    session=session, business_task_id=task.id, expense_items=expense_items
                )
                if missing_fields:
                    raise ValueError("报销信息不完整，不能提交：" + "、".join(missing_fields))

                total_amount = sum((Decimal(str(item["amount"])) for item in expense_items), Decimal("0.00")).quantize(
                    Decimal("0.01"))
                if not total_amount.is_finite() or total_amount <= 0:
                    raise ValueError("报销总金额必须大于 0。")

                now = utc_now()
                claim_no = f"BX{now.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"

                claim = ExpenseClaim(
                    claim_no=claim_no, applicant_id=user_id,
                    title=str(draft_data.get("title") or task.title or "报销申请").strip(),
                    description=draft_data.get("description"), total_amount=total_amount,
                    currency=draft_data.get("currency") or "CNY", status=ExpenseClaimStatus.PENDING_APPROVAL.value, submitted_at=now,
                )
                await task_repo.add_claim_without_commit(claim)

                formal_items, formal_item_map = [], {}
                for item in expense_items:
                    expense_date = date.fromisoformat(str(item["expense_date"]))
                    expense_datetime = datetime.combine(expense_date, time.min, tzinfo=timezone.utc)
                    formal_item = ExpenseItem(
                        claim_id=claim.id, category=str(item["category"]).strip(),
                        description=str(item["description"]).strip() or None if item.get(
                            "description") is not None else None,
                        amount=Decimal(str(item["amount"])).quantize(Decimal("0.01")), expense_date=expense_datetime,
                    )
                    formal_items.append(formal_item)
                    formal_item_map[str(item["id"])] = formal_item
                await task_repo.add_claim_items_without_commit(formal_items)

                draft_attachments = await task_repo.list_attachments_by_task(business_task_id=task.id)
                formal_attachments = []
                orphan_attachments = []
                for attachment in draft_attachments:
                    formal_item = formal_item_map.get(str(attachment.expense_item_uid))
                    if formal_item is None:
                        # 历史数据里可能存在「明细已删除、附件未删」的孤儿附件。
                        # 这类附件无法挂到正式单据上，直接清理掉，避免整张单据永久无法提交。
                        orphan_attachments.append(attachment)
                        continue
                    formal_attachments.append(Attachment(
                        claim_id=claim.id, expense_item_id=formal_item.id, uploaded_by=attachment.uploaded_by,
                        original_filename=attachment.original_filename, storage_path=attachment.storage_path,
                        content_type=attachment.content_type, file_size=attachment.file_size
                    ))

                if orphan_attachments:
                    logger.warning(
                        "提交报销单时清理孤儿附件：task_uid=%s claim_no=%s files=%s",
                        task.uid,
                        claim.claim_no,
                        [attachment.original_filename for attachment in orphan_attachments],
                    )
                    orphan_storage_paths.extend(
                        attachment.storage_path
                        for attachment in orphan_attachments
                        if attachment.storage_path
                    )
                    await task_repo.delete_attachments_by_ids(orphan_attachments)

                session.add_all(formal_attachments)
                await session.flush()

                task.claim_id = claim.id
                task.status = BusinessTaskStatus.COMPLETED.value
                task.missing_fields = []
                await task_repo.update(task)
                if conversation.active_business_task_uid == task.uid:
                    conversation.active_business_task_uid = None

                # 实例化 Repository 和 Service 在当前数据库事务中创建初审记录  此方法不会 commit，也不会投递 Redis 任务。
                pre_review_service = ExpensePreReviewService(
                    repository=ExpensePreReviewRepository(session),
                    claim_repository=ExpenseClaimRepository(session),
                    redis=self.redis
                )
                review_uid = (await pre_review_service.create_review_record(claim_id=claim.id)).uid

                selected_task = await self._build_business_task_response(session, task, claim)
                response_data = {
                    "already_confirmed": False, "claim_id": claim.id, "claim_no": claim.claim_no,
                    "status": claim.status, "claim_status": claim.status, "description": claim.description,
                    "total_amount": str(claim.total_amount), "item_count": len(formal_items),
                    "selected_business_task": selected_task,"pre_review": {"uid": review_uid,"status": PreReviewStatus.PENDING.value,},
                }
            # 正式报销单事务已经提交，再清理孤儿附件文件并投递初审任务。
            await self._remove_storage_objects(orphan_storage_paths)
            try:
                await pre_review_service.enqueue_review(
                    review_uid=review_uid
                )
                response_data["pre_review"]["enqueued"] = True

            except Exception as exc:
                response_data["pre_review"].update({"status": PreReviewStatus.FAILED.value, "enqueued": False , "error": str(exc)})
                try:
                    await pre_review_service.mark_enqueue_failed(review_uid=review_uid, error_message=str(exc))
                except Exception:
                    logger.exception("更新初审投递失败状态失败，review_uid=%s", review_uid)

            return response_data

    # 取消尚未提交的报销业务草稿。
    async def cancel_business_task(self, *, task_uid: str, user_id: int, conversation_id: int) -> dict[str, Any]:
        session_factory = self._get_session_factory()
        async with session_factory() as session:
            async with session.begin():
                conversation = await self._get_locked_conversation(session, conversation_id, user_id)
                task_repo = BusinessTaskRepository(session)
                task = await task_repo.get_by_uid(
                    task_uid=task_uid, user_id=user_id, conversation_id=conversation_id,
                    task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT, for_update=True
                )
                if task is None:
                    raise RuntimeError("报销任务不存在，或不属于当前用户和会话。")
                if task.claim_id is not None:
                    raise RuntimeError("当前报销任务已经生成正式报销单，不能取消。")
                if task.status == BusinessTaskStatus.CANCELLED.value:
                    return {"cancelled": True, "already_cancelled": True,
                            "selected_business_task": await self._build_business_task_response(session, task)}

                if task.status not in UPLOADABLE_STATUSES:
                    raise RuntimeError("当前报销任务状态不允许取消。")

                task.status = BusinessTaskStatus.CANCELLED.value
                task.missing_fields = []
                await task_repo.update(task)
                if conversation.active_business_task_uid == task.uid:
                    conversation.active_business_task_uid = None

                return {"cancelled": True, "already_cancelled": False,
                        "selected_business_task": await self._build_business_task_response(session, task)}

    # 查询最近取消10个报销任务
    async def list_cancelled_business_tasks(self,*,user_id: int,conversation_id: int,limit: int = 10,offset: int = 0) -> list[dict[str, Any]]:
        """查询当前用户在当前会话中已取消的报销任务列表。"""

        session_factory = self._get_session_factory()

        async with session_factory() as session:
            conversation = await self._get_locked_conversation(session, conversation_id, user_id)
            task_repo = BusinessTaskRepository(session)
            tasks = await task_repo.list_by_status(
                user_id=user_id,
                conversation_id=conversation_id,
                task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT,
                status=BusinessTaskStatus.CANCELLED,
                limit=limit,
                offset=offset,
            )
            if len(tasks) == 1:
                # 只有一个可以恢复的任务直接绑定到会话中
                # 深拷贝，防止原地修改导致 SQLAlchemy 无法侦测变化
                context = deepcopy(conversation.agent_context or {})
                if not isinstance(context, dict):
                    context = {}

                context["pending_action"] = {
                    "type": "resume_business_task",
                    "business_task_uid": tasks[0].uid
                }
                conversation.agent_context = context
                await session.commit()
            # 使用原有的完整响应组装方法，保证前端拿到 display、
            # expense_summary、附件列表等数据。
            return [
                await self._build_business_task_response(
                    session=session,
                    task=task,
                )
                for task in tasks
            ]

    # 根据 UID 获取指定的已取消报销任务，不修改任务状态。
    async def get_cancelled_business_task(self,*,task_uid: str,user_id: int,conversation_id: int) -> dict[str, Any]:
        """根据 UID 获取指定的已取消报销任务，不修改任务状态。"""

        session_factory = self._get_session_factory()

        async with session_factory() as session:
            conversation = await self._get_locked_conversation(session, conversation_id, user_id)
            task_repo = BusinessTaskRepository(session)

            task = await task_repo.get_by_uid(
                task_uid=task_uid,
                user_id=user_id,
                conversation_id=conversation_id,
                task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT,
                status=BusinessTaskStatus.CANCELLED,
            )

            if task is None:
                raise ValueError(
                    "这笔报销任务不存在、不属于当前会话，"
                    "或已经不处于可恢复状态。请重新查看已取消的任务。"
                )

            if task.claim_id is not None:
                raise ValueError("该任务已经关联正式报销单，不能恢复。")

            context = deepcopy(conversation.agent_context or {})
            if not isinstance(context, dict):
                context = {}

            context["pending_action"] = {
                "type": "resume_business_task",
                "business_task_uid": task.uid
            }
            conversation.agent_context = context
            await session.commit()

            return await self._build_business_task_response(
                session=session,
                task=task,
            )

    # 恢复已取消的报销任务
    async def restore_cancelled_business_task(self,*,source_task_uid: str,user_id: int,conversation_id: int,) -> dict:
        """
        恢复已取消的报销任务。

        不修改原任务，而是复制原任务草稿创建一个新的 BusinessTask。
        同一个原任务只能恢复一次，重复请求返回之前创建的新任务。
        """

        session_factory = self._get_session_factory()

        async with session_factory() as session:
            async with session.begin():
                # 1. 先锁定 Conversation，保持与确认、取消操作一致的锁顺序
                result = await session.execute(
                    select(Conversation)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                    .with_for_update()
                )
                conversation = result.scalar_one_or_none()

                if conversation is None:
                    raise ValueError("会话不存在或无权访问。")

                task_repo = BusinessTaskRepository(session)

                # 2. 锁定原任务，只允许恢复已取消的报销任务
                source_task = await task_repo.get_by_uid(
                    task_uid=source_task_uid,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT,
                    status=BusinessTaskStatus.CANCELLED,
                    for_update=True,
                )

                if source_task is None:
                    raise ValueError("原报销任务不存在，或当前状态不允许恢复。")

                if source_task.claim_id is not None:
                    raise ValueError("该任务已经关联正式报销单，不能恢复。")

                # 3. 检查是否已经恢复过
                source_draft = deepcopy(source_task.draft_data or {})
                restored_task_uid = source_draft.get("_restored_to_task_uid")

                if restored_task_uid:
                    restored_task = await task_repo.get_by_uid(
                        task_uid=restored_task_uid,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT,
                    )

                    if restored_task is None:
                        raise RuntimeError(
                            "原任务记录了恢复目标，但目标任务不存在，"
                            "请检查业务数据，不能重复创建恢复任务。"
                        )

                    return {
                        "already_restored": True,
                        "source_business_task": await self._build_business_task_response(
                            session=session,
                            task=source_task,
                        ),
                        "selected_business_task": await self._build_business_task_response(
                            session=session,
                            task=restored_task,
                        ),
                    }

                # 4. 不允许覆盖当前正在办理的其他业务任务
                active_uid = conversation.active_business_task_uid

                if active_uid and active_uid != source_task.uid:
                    raise RuntimeError(
                        "当前已有其他正在办理的业务任务，请先完成或取消。"
                    )

                # 5. 深拷贝草稿，避免修改原任务数据
                new_draft = deepcopy(source_draft)

                expense_items = new_draft.get("expense_items", [])

                if not isinstance(expense_items, list):
                    raise ValueError("原报销草稿中的费用明细格式不正确。")

                # 6. 校验每条费用明细都有 ID，恢复时保留原 ID，
                # 以便继续关联原任务的附件。
                for item in expense_items:
                    if not isinstance(item, dict):
                        raise ValueError("原报销草稿中存在格式不正确的费用明细。")

                    if not item.get("id"):
                        raise ValueError("原报销草稿中存在缺少 ID 的费用明细。")

                # 清理原消息幂等记录，避免新任务受到旧消息影响
                new_draft.pop("_processed_message_uids", None)

                # 7. 根据草稿内容重新计算缺失字段
                missing_fields = await self._calculate_missing_fields_with_attachments(
                    session=session,
                    business_task_id=source_task.id,
                    expense_items=expense_items,
                )

                new_status = (
                    BusinessTaskStatus.COLLECTING
                    if missing_fields
                    else BusinessTaskStatus.WAITING_CONFIRMATION
                )

                # 8. 创建新的 BusinessTask
                restored_task = BusinessTask(
                    uid=str(uuid4()),
                    conversation_id=source_task.conversation_id,
                    created_by=source_task.created_by,
                    task_type=source_task.task_type,
                    title=source_task.title,
                    status=new_status,
                    draft_data=new_draft,
                    missing_fields=missing_fields,
                    claim_id=None,
                )

                # 先将新任务加入 Session
                await task_repo.add_without_commit(restored_task)

                # 必须先 flush，确保 restored_task.id 已经生成
                await session.flush()

                # 9. 复制原任务附件，复用 MinIO 对象
                attachment_result = await session.execute(
                    select(BusinessTaskAttachment).where(
                        BusinessTaskAttachment.business_task_id == source_task.id
                    )
                )

                source_attachments = attachment_result.scalars().all()

                # 校验附件关联的费用明细仍然存在
                expense_item_uids = {
                    str(item["id"])
                    for item in expense_items
                }

                for attachment in source_attachments:
                    if str(attachment.expense_item_uid) not in expense_item_uids:
                        # 历史遗留的孤儿附件（明细已删除、附件残留）不应阻断恢复。
                        logger.warning(
                            "恢复报销任务时跳过孤儿附件：task_uid=%s file=%s",
                            source_task.uid,
                            attachment.original_filename,
                        )
                        continue

                    restored_attachment = BusinessTaskAttachment(
                        uid=str(uuid4()),
                        business_task_id=restored_task.id,
                        expense_item_uid=attachment.expense_item_uid,
                        uploaded_by=attachment.uploaded_by,
                        original_filename=attachment.original_filename,
                        storage_path=attachment.storage_path,
                        content_type=attachment.content_type,
                        file_size=attachment.file_size,
                    )

                    session.add(restored_attachment)

                await session.flush()

                # 10. 在原任务中记录恢复目标，保证幂等
                source_draft["_restored_to_task_uid"] = restored_task.uid
                source_task.draft_data = source_draft

                await task_repo.update(source_task)

                # 11. 将会话活动任务指向新任务
                conversation.active_business_task_uid = restored_task.uid
                context = deepcopy(conversation.agent_context or {})
                if not isinstance(context, dict): context = {}
                # 直接删除 pending_action，而不是把它留个空壳
                context.pop("pending_action", None)
                conversation.agent_context = context

                return {
                    "already_restored": False,
                    "source_business_task": await self._build_business_task_response(
                        session=session,
                        task=source_task,
                    ),
                    "selected_business_task": await self._build_business_task_response(
                        session=session,
                        task=restored_task,
                    ),

                }

    # 清除会话中「等待确认恢复」的待办动作。
    async def clear_pending_resume(self, *, user_id: int, conversation_id: int) -> bool:
        """用户拒绝恢复后清空 agent_context.pending_action，避免状态残留。"""

        session_factory = self._get_session_factory()

        async with session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(Conversation)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                    .with_for_update()
                )
                conversation = result.scalar_one_or_none()

                if conversation is None:
                    return False

                context = deepcopy(conversation.agent_context or {})
                if not isinstance(context, dict):
                    context = {}

                if "pending_action" not in context:
                    return False

                context.pop("pending_action", None)
                conversation.agent_context = context

        return True

    # 验证并设置当前会话的活动业务任务。
    async def select_business_task(self,*,task_uid: str,user_id: int,conversation_id: int,) -> dict[str, Any]:
        """验证并设置当前会话的活动业务任务。"""

        session_factory = self._get_session_factory()

        async with session_factory() as session:
            async with session.begin():

                # 先锁会话，再锁任务，统一事务加锁顺序。
                conversation_result = await session.execute(
                    select(Conversation)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                    .with_for_update()
                )
                conversation = conversation_result.scalar_one_or_none()

                if conversation is None:
                    raise RuntimeError("会话不存在，或不属于当前用户。")

                # 查询并锁定允许继续操作的任务。
                task_result = await session.execute(
                    select(BusinessTask)
                    .where(
                        BusinessTask.uid == task_uid,
                        BusinessTask.created_by == user_id,
                        BusinessTask.conversation_id == conversation_id,
                        BusinessTask.status.in_(
                            (
                                BusinessTaskStatus.COLLECTING.value,
                                BusinessTaskStatus.WAITING_CONFIRMATION.value,
                            )
                        ),
                        BusinessTask.claim_id.is_(None),
                    )
                    .with_for_update()
                )
                task = task_result.scalar_one_or_none()

                if task is None:
                    raise RuntimeError(
                        "任务不存在、不属于当前会话，"
                        "或当前状态不允许继续操作。"
                    )

                conversation.active_business_task_uid = task.uid

                selected_task = await self._build_business_task_response(
                    session=session,
                    task=task,
                )

        return selected_task

    # 只读获取任务的完整前端响应，不加锁、不校验状态、无副作用。
    async def get_task_response(self, *, task_uid: str, user_id: int, conversation_id: int) -> dict[str, Any] | None:
        """按 UID 读取任务并返回经 _build_business_task_response 包装的完整数据。

        供节点失败兜底等场景使用：任何状态下都可读取（含 cancelled），
        保证前端拿到 display、expense_summary、附件等完整字段。
        任务不存在或不属于当前会话时返回 None。
        """

        session_factory = self._get_session_factory()

        async with session_factory() as session:
            task_repo = BusinessTaskRepository(session)
            task = await task_repo.get_by_uid(
                task_uid=task_uid,
                user_id=user_id,
                conversation_id=conversation_id,
                task_type=BusinessTaskType.EXPENSE_REIMBURSEMENT,
            )

            if task is None:
                return None

            return await self._build_business_task_response(session=session, task=task)

    # 清除当前会话的活动业务任务绑定。
    async def clear_active_business_task(self,*,user_id: int,conversation_id: int,expected_task_uid: str | None = None,) -> bool:
        """
        清除当前会话的活动任务绑定。

        expected_task_uid 不为空时，只有当前绑定仍然是该任务才清除，
        避免旧任务的完成操作误清除用户后来选择的新任务。
        """

        session_factory = self._get_session_factory()

        async with session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(Conversation)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                    .with_for_update()
                )
                conversation = result.scalar_one_or_none()

                if conversation is None:
                    raise RuntimeError("会话不存在，或不属于当前用户。")

                if not conversation.active_business_task_uid:
                    return False

                if (
                    expected_task_uid is not None
                    and conversation.active_business_task_uid != expected_task_uid
                ):
                    return False

                conversation.active_business_task_uid = None

        return True

    # 查询任务附件，并构造完整的前端任务响应。
    async def _build_business_task_response(self, session: AsyncSession, task: BusinessTask, claim=None,missing_fields: list[str] | None = None,) -> dict:
        """
        查询任务附件，并构造完整的前端任务响应。
        【核心优化】：每次组装响应时，动态计算缺失字段，确保数据绝对实时。
        """

        repository = BusinessTaskRepository(session)
        attachments = await repository.list_attachments_by_task(business_task_id=task.id)

        draft_data = deepcopy(task.draft_data or {})
        draft_data.pop("_processed_message_uids", None)
        expense_items = draft_data.get("expense_items") or []

        # 1. 动态计算缺失字段（优先用传入的，避免重复查库）
        if missing_fields is not None:
            real_time_missing_fields = missing_fields
        elif task.status in REALTIME_MISSING_STATUSES:
            real_time_missing_fields = await self._calculate_missing_fields_with_attachments(
                session=session, business_task_id=task.id, expense_items=expense_items
            )
        else:
            real_time_missing_fields = task.missing_fields or []

        # 2. 组装附件映射
        attachments_by_item: dict[str, list[dict]] = {}
        for attachment in (attachments or []):
            item_uid = str(attachment.expense_item_uid)
            attachments_by_item.setdefault(item_uid, []).append({
                "uid": attachment.uid,
                "filename": attachment.original_filename,
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
                "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
            })

        # 3. 组装明细摘要
        expense_summary = []
        for item in expense_items:
            raw_item_uid = item.get("id")
            if not raw_item_uid:
                raise ValueError("费用明细缺少唯一 ID。")
            item_uid = str(raw_item_uid)
            item_attachments = attachments_by_item.get(item_uid, [])
            expense_summary.append({
                "id": item_uid,
                "category": item.get("category"),
                "description": item.get("description"),
                "amount": item.get("amount"),
                "expense_date": item.get("expense_date"),
                "invoice_uploaded": len(item_attachments) > 0,
                "invoice_count": len(item_attachments),
                "attachments": item_attachments,
            })

        return {
            "uid": task.uid,
            "title": task.title,
            "task_type": task.task_type,
            "status": task.status,
            "missing_fields": real_time_missing_fields,  # 使用实时计算的值
            "claim_status": claim.status if claim else None,
            "display": {
                "display_title": task.title,
                "total_amount": calculate_expense_total(expense_items),
                "currency": draft_data.get("currency") or "CNY",
                "item_count": len(expense_summary),
                "expense_summary": expense_summary,
                "claim_no": claim.claim_no if claim else None,
                "created_at": task.created_at.isoformat() if task.created_at else None,
            },
        }

    # ================= 静态辅助方法 =================
    # 根据费用明细计算缺失的必填字段。
    @staticmethod
    def _calculate_missing_fields(expense_items: list[dict[str, Any]]) -> list[str]:
        missing_fields: list[str] = []
        if not expense_items:
            return ["expense_items"]
        for item in expense_items:
            item_id = item.get("id")
            if not item_id:
                raise ValueError("费用明细缺少唯一 ID。")
            item_id = str(item_id)
            if not isinstance(item.get("category"), str) or not item.get("category").strip():
                missing_fields.append(f"expense_items.{item_id}.category")
            try:
                amount = Decimal(str(item.get("amount")))
                if not amount.is_finite() or amount <= 0:
                    raise InvalidOperation
            except (InvalidOperation, TypeError, ValueError):
                missing_fields.append(f"expense_items.{item_id}.amount")
            raw_expense_date = item.get("expense_date")
            if not raw_expense_date:
                missing_fields.append(f"expense_items.{item_id}.expense_date")
            else:
                try:
                    date_string = str(raw_expense_date)
                    parsed_date = date.fromisoformat(date_string)
                    if parsed_date.isoformat() != date_string:
                        raise ValueError
                except (ValueError, TypeError):
                    missing_fields.append(f"expense_items.{item_id}.expense_date")
        return missing_fields

    # 在原有费用字段校验基础上，增加发票附件校验。
    async def _calculate_missing_fields_with_attachments(self, session: AsyncSession, business_task_id: int, expense_items: list[dict]) -> list[str]:
        missing_fields = self._calculate_missing_fields(expense_items)
        repository = BusinessTaskRepository(session)
        attachments = await repository.list_attachments_by_task(business_task_id=business_task_id)
        attachment_counts = {}
        for attachment in attachments:
            item_uid = str(attachment.expense_item_uid)
            attachment_counts[item_uid] = attachment_counts.get(item_uid, 0) + 1
        for item in expense_items:
            item_uid = item.get("id")
            if not item_uid: continue
            if attachment_counts.get(str(item_uid), 0) == 0:
                missing_fields.append(f"expense_items.{item_uid}.invoice")
        return missing_fields

    # 获取文件名称
    @staticmethod
    def _get_safe_filename(filename: str | None) -> str:
        """清理文件名，只保留文件名部分。"""
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件名不能为空",
            )

        # 同时处理 Windows 和 Linux 路径分隔符
        filename = filename.replace("\\", "/")
        safe_name = PurePosixPath(filename).name.strip()

        if not safe_name or safe_name in {".", ".."}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件名无效",
            )

        return safe_name[:255]

    # 校验文件格式
    @staticmethod
    def _validate_file(*,filename: str,content_type: str | None,content: bytes,) -> str:
        """校验扩展名、声明 MIME 和文件签名。"""
        suffix = PurePosixPath(filename).suffix.lower()
        file_config = ALLOWED_FILES.get(suffix)

        if file_config is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="仅支持 PDF、JPG、JPEG、PNG 文件",
            )

        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能上传空文件",
            )

        expected_type = file_config["content_type"]

        # 允许浏览器无法识别 MIME 时使用 application/octet-stream
        if content_type not in (None, "", expected_type, "application/octet-stream"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="文件 MIME 类型与扩展名不匹配",
            )

        if not file_config["signature"](content):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="文件内容与声明的文件格式不匹配",
            )

        return expected_type

    # 上传发票
    async def upload_expense_item_attachment(self,*,conversation_uid: str,task_uid: str,expense_item_uid: str,file: UploadFile,current_user: User,) -> dict:
        """上传报销草稿费用明细附件，并返回最新任务数据。"""

        safe_filename = self._get_safe_filename(file.filename)

        # 最多读取 10 MB + 1 字节，以便识别超限文件
        content = await file.read(MAX_FILE_SIZE + 1)

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="文件大小不能超过 10 MB",
            )

        actual_content_type = self._validate_file(
            filename=safe_filename,
            content_type=file.content_type,
            content=content,
        )

        # 1. 校验会话归属
        session_factory = self._get_session_factory()

        async with session_factory() as session:
            async with session.begin():
                conversations_repository = ConversationsRepository(session)
                repository = BusinessTaskRepository(session)

                conversation = await conversations_repository.get_conversation(
                    conversation_uid=conversation_uid,
                    user_id=current_user.id,
                )

                if conversation is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="会话不存在",
                    )

                # 2. 校验任务归属，并锁定任务行
                task = await repository.get_by_uid(
                    task_uid=task_uid,
                    user_id=current_user.id,
                    conversation_id=conversation.id,
                    for_update=True,
                )

                if task is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="业务任务不存在",
                    )

                if task.claim_id is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="该任务已经生成正式报销单，不能再上传草稿附件",
                    )

                if task.status not in UPLOADABLE_STATUSES:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="当前任务状态不允许上传附件",
                    )

                # 3. 校验费用明细 UID 是否属于当前草稿
                draft_data = task.draft_data or {}
                expense_items = draft_data.get("expense_items", [])

                if not isinstance(expense_items, list):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="报销草稿费用明细数据格式异常",
                    )

                item_exists = any(
                    isinstance(item, dict)
                    and str(item.get("id")) == str(expense_item_uid)
                    for item in expense_items
                )

                if not item_exists:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="报销费用明细不存在",
                    )

                # 4. 使用服务端生成的对象路径，不使用用户文件名
                object_name = (
                    f"business-tasks/{task.uid}/"
                    f"{expense_item_uid}/{uuid.uuid4().hex}"
                    f"{PurePosixPath(safe_filename).suffix.lower()}"
                )

                uploaded = False

                try:
                    # 5. 先上传 MinIO
                    storage = get_expense_minio_storage()
                    await storage.upload(
                        object_name=object_name,
                        content=content,
                        content_type=actual_content_type,
                    )
                    uploaded = True

                    # 5.1 图片附件顺带生成缩略图（列表页只加载缩略图，避免单页几十 MB 原图下载）
                    #     缩略图失败不阻断上传，前端会回退到原图
                    if actual_content_type.startswith("image/"):
                        await storage.upload_image_thumbnail(object_name, content)

                    # 6. 创建附件记录
                    attachment = BusinessTaskAttachment(
                        uid=str(uuid.uuid4()),
                        business_task_id=task.id,
                        expense_item_uid=expense_item_uid,
                        uploaded_by=current_user.id,
                        original_filename=safe_filename,
                        storage_path=object_name,
                        content_type=actual_content_type,
                        file_size=len(content),
                    )

                    await repository.add_attachment_without_commit(attachment)

                    # 确保附件记录已经写入当前事务，
                    # 后续重新计算缺失字段时能够查询到它。
                    await session.flush()

                    # 7+8. 用统一的刷新方法（内部会算 missing_fields 并更新 status）
                    real_missing = await self._refresh_task_state(
                        session, task, expense_items
                    )
                    await repository.update(task)


                    # 注意：这里不需要手动 commit，因为 async with session.begin()
                    # 会在退出时自动 commit。如果你写了 commit，会导致事务提前结束。

                    # 9. 构造完整任务响应（放在事务内，方便复用 session）
                    selected_business_task = await self._build_business_task_response(
                        session, task, missing_fields=real_missing
                    )

                    # 9.1 更新当前会话正在处理的业务任务
                    conversation.active_business_task_uid = task.uid

                    # 9.2 根据最新任务状态构建助手消息
                    if task.status == BusinessTaskStatus.WAITING_CONFIRMATION.value:
                        assistant_content = (
                            "发票上传成功，报销信息已完整。"
                            "请确认是否提交报销申请。"
                        )
                    else:
                        assistant_content = (
                            "发票上传成功，我已经更新了报销信息。"
                            "目前还有部分信息需要补充，请继续完善。"
                        )

                    # 9.3 构建消息上下文
                    assistant_extra_data = {
                        **_build_task_ui_payload(selected_business_task)

                    }
                    previous_assistant_result = await session.execute(
                        select(Message.extra_data)
                        .where(
                            Message.conversation_id == conversation.id,
                            Message.role == "assistant",
                        )
                        .order_by(Message.id.desc())
                        .limit(1)
                    )
                    previous_assistant_extra_data = (
                        previous_assistant_result.scalar_one_or_none()
                    )
                    if isinstance(previous_assistant_extra_data, dict):
                        agent_context = (
                                previous_assistant_extra_data.get("_agent_context") or {}
                        )
                        pending_resume_task_uid = None
                        if isinstance(agent_context, dict):
                            pending_resume_task_uid = agent_context.get(
                                "pending_resume_task_uid"
                            )

                        assistant_extra_data["_agent_context"] = {
                            "pending_resume_task_uid": pending_resume_task_uid,
                        }
                    # 9.4 保存助手消息
                    assistant_message = Message(
                        uid=str(uuid.uuid4()),
                        conversation_id=conversation.id,
                        role="assistant",
                        content=assistant_content,
                        extra_data=assistant_extra_data,
                    )

                    await conversations_repository.add_message_without_commit(
                        assistant_message
                    )

                    # 在 try 内部就把返回结果准备好
                    upload_result = {
                        "success": True,
                        "uploaded_file": {
                            "uid": attachment.uid,
                            "filename": safe_filename,
                            "file_size": len(content),
                        },
                    }

                except Exception:
                    # 数据库操作失败时，补偿删除 MinIO 对象
                    if uploaded:
                        try:
                            await storage.remove(object_name)
                        except Exception:
                            logger.exception(
                                "报销附件上传失败后的 MinIO 补偿清理失败: %s",
                                object_name,
                            )
                    raise

        return upload_result