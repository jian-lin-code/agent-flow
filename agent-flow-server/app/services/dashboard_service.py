"""管理员工作台业务服务。

负责把 Repository 的数据库聚合结果、Redis 队列心跳、psutil 系统指标
组装成前端工作台需要的三份数据：summary / trend / health。
"""

import asyncio
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psutil
from arq.connections import ArqRedis
from sqlalchemy import text

from app.repository.dashboard_repository import DashboardRepository
from app.utils.datetime_helper import utc_now
from app.utils.logger import logger
from app.utils.minio_client import get_minio_storage

BUSINESS_TZ = ZoneInfo("Asia/Shanghai")

# 三个独立 ARQ Worker 的队列配置（与各自 WorkerSettings 保持一致）
WORKER_DEFINITIONS = [
    {"key": "rag", "queue": "rag-flow", "name": "RAG 解析 Worker", "capacity": 4},
    {"key": "agent", "queue": "agent-flow", "name": "对话 Agent Worker", "capacity": 4},
    {"key": "review", "queue": "expense-review", "name": "AI 预审 Worker", "capacity": 2},
]

# 趋势视图：1 小时按 5 分钟、24 小时按小时、7 天按自然日分桶
TREND_RANGES = {
    "1h": {"duration": timedelta(hours=1), "step": timedelta(minutes=5), "label": "%H:%M"},
    "24h": {"duration": timedelta(hours=24), "step": timedelta(hours=1), "label": "%H:%M"},
    "7d": {"duration": timedelta(days=7), "step": timedelta(days=1), "label": "%m-%d"},
}


class DashboardService:
    def __init__(self, repository: DashboardRepository, redis: ArqRedis):
        self.repository = repository
        self.redis = redis

    # ---------- 汇总 ----------

    async def get_summary(self, *, admin_user_id: int | None = None) -> dict:
        tasks = await self.repository.get_task_stats()
        # 待审批口径与"待我审批"页一致：排除管理员本人提交的单据
        approvals = await self.repository.get_approval_summary(
            exclude_applicant_id=admin_user_id
        )
        quick = await self.repository.get_quick_stats(
            exclude_applicant_id=admin_user_id
        )
        records, records_total = await self.repository.get_recent_runs()
        return {
            "tasks": tasks,
            "approvals": approvals,
            "quick": quick,
            "records": records,
            "records_total": records_total,
            "generated_at": utc_now(),
        }

    # ---------- 趋势 ----------

    async def get_trend(self, range_key: str) -> dict:
        config = TREND_RANGES.get(range_key)
        if config is None:
            raise ValueError("不支持的时间范围")

        now = datetime.now(BUSINESS_TZ)
        duration: timedelta = config["duration"]
        step: timedelta = config["step"]
        # 先把「当前时间」对齐到分桶边界，否则 24h 视图会生成 17:54 这类非整点桶，
        # 与 SQL date_trunc 的 17:00 对不上导致全部为 0。
        end = self._floor_to_step(now, step)
        start = end - duration + step

        points: list[dict] = []

        if range_key == "1h":
            # 1 小时窗口数据量小，按原始记录在内存聚合，避免 SQL 处理 5 分钟取整
            raw = await self.repository.get_raw_runs(start)
            buckets: dict[datetime, dict[str, int]] = {}
            for started_at, status in raw:
                local = started_at.astimezone(BUSINESS_TZ)
                bucket = local.replace(
                    minute=local.minute - local.minute % 5, second=0, microsecond=0
                )
                slot = buckets.setdefault(bucket, {"total": 0, "success": 0, "failed": 0})
                slot["total"] += 1
                if status == "success":
                    slot["success"] += 1
                elif status in ("failed", "cancelled"):
                    slot["failed"] += 1
            cursor = start
            while cursor <= end:
                slot = buckets.get(cursor, {"total": 0, "success": 0, "failed": 0})
                points.append(self._point(cursor, slot, config["label"]))
                cursor += step
        else:
            aggregated = (
                await self.repository.get_hourly_trend(start)
                if range_key == "24h"
                else await self.repository.get_daily_trend(start)
            )
            key_format = "%Y-%m-%d %H:%M" if range_key == "24h" else "%Y-%m-%d"
            cursor = start
            while cursor <= end:
                slot = aggregated.get(cursor.strftime(key_format))
                points.append(
                    self._point(
                        cursor,
                        slot or {"total": 0, "success": 0, "failed": 0},
                        config["label"],
                    )
                )
                cursor += step

        return {"range": range_key, "points": points}

    @staticmethod
    def _floor_to_step(moment: datetime, step: timedelta) -> datetime:
        """把时间向下取整到 step 边界（对齐 SQL date_trunc 的分桶起点）。"""
        midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed = moment - midnight
        steps = int(elapsed.total_seconds() // step.total_seconds())
        return midnight + step * steps

    @staticmethod
    def _point(bucket: datetime, slot: dict[str, int], label_format: str) -> dict:
        return {
            "label": bucket.strftime(label_format),
            "bucket": bucket,
            "total": int(slot["total"]),
            "success": int(slot["success"]),
            "failed": int(slot["failed"]),
        }

    # ---------- 健康 ----------

    async def get_health(self) -> dict:
        cpu_percent, memory = await asyncio.gather(
            asyncio.to_thread(psutil.cpu_percent, 0.2),
            asyncio.to_thread(psutil.virtual_memory),
        )

        db_component = await self._probe_db()
        redis_component = await self._probe_redis()
        minio_component = await self._probe_minio()

        workers, last_active = await asyncio.gather(
            self._collect_workers(),
            self.repository.get_service_last_active(),
        )
        for worker in workers:
            worker["last_active_at"] = last_active.get(worker["queue"])

        avg_response_ms = await self._avg_response_ms()

        return {
            "cpu_percent": round(float(cpu_percent), 1),
            "memory_used_gb": round((memory.total - memory.available) / 1024**3, 1),
            "memory_total_gb": round(memory.total / 1024**3, 1),
            "memory_percent": round(float(memory.percent), 1),
            "avg_response_ms": avg_response_ms,
            "components": [db_component, redis_component, minio_component],
            "workers": workers,
            "checked_at": utc_now(),
        }

    async def _avg_response_ms(self) -> int | None:
        return await self.repository.get_avg_duration_ms()

    async def _probe_db(self) -> dict:
        started = time.perf_counter()
        try:
            await self.repository.session.execute(text("SELECT 1"))
            return {
                "key": "postgres",
                "name": "PostgreSQL",
                "status": "ok",
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:  # noqa: BLE001 - 探活失败需降级而不是抛错
            logger.warning(f"工作台探活：PostgreSQL 连接失败 {exc}")
            return {
                "key": "postgres",
                "name": "PostgreSQL",
                "status": "down",
                "latency_ms": None,
                "detail": str(exc)[:120],
            }

    async def _probe_redis(self) -> dict:
        started = time.perf_counter()
        try:
            await self.redis.ping()
            return {
                "key": "redis",
                "name": "Redis",
                "status": "ok",
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"工作台探活：Redis 连接失败 {exc}")
            return {
                "key": "redis",
                "name": "Redis",
                "status": "down",
                "latency_ms": None,
                "detail": str(exc)[:120],
            }

    async def _probe_minio(self) -> dict:
        started = time.perf_counter()
        storage = get_minio_storage()
        try:
            exists = await asyncio.to_thread(storage.client.bucket_exists, storage.bucket)
            latency = int((time.perf_counter() - started) * 1000)
            return {
                "key": "minio",
                "name": "MinIO",
                "status": "ok" if exists else "degraded",
                "latency_ms": latency,
                "detail": None if exists else "存储桶不存在",
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"工作台探活：MinIO 连接失败 {exc}")
            return {
                "key": "minio",
                "name": "MinIO",
                "status": "down",
                "latency_ms": None,
                "detail": str(exc)[:120],
            }

    async def _collect_workers(self) -> list[dict]:
        """读取 ARQ 自动维护的 `{queue}:health-check` 心跳键 + 队列积压长度。

        ARQ Worker 默认每 3600s 刷新一次心跳，key TTL 为 3601s，
        因此「离线」判定最坏存在约 1 小时延迟（此处不做额外探针）。
        """
        workers: list[dict] = []
        for definition in WORKER_DEFINITIONS:
            queue = definition["queue"]
            try:
                async with self.redis.pipeline(transaction=False) as pipe:
                    pipe.exists(f"{queue}:health-check")
                    pipe.zcard(queue)
                    exists, queued = await pipe.execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"工作台探活：读取队列 {queue} 失败 {exc}")
                exists, queued = 0, 0

            online = bool(exists)
            queued = int(queued or 0)
            if not online:
                status = "offline"
                detail = "未检测到心跳"
            elif queued >= definition["capacity"]:
                status = "busy"
                detail = f"队列积压 {queued}"
            else:
                status = "online"
                detail = None

            workers.append(
                {
                    "key": definition["key"],
                    "name": definition["name"],
                    "queue": queue,
                    "online": online,
                    "status": status,
                    "queued": queued,
                    "capacity": definition["capacity"],
                    "detail": detail,
                }
            )
        return workers
