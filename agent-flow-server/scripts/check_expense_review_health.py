#!/usr/bin/env python
"""报销 AI 初审卡单检查（供 cron / systemd timer / Prometheus 探针调用）。

检查目标：
1. pending_approval 单据的 AI 初审长时间停留在 pending（多半是 review worker 没起）；
2. 初审停留在 running 超过阈值的僵尸任务；
3. 初审 failed 的单据（需要用户在详情页点「重新初审」）。

用法：
    uv run python scripts/check_expense_review_health.py
    uv run python scripts/check_expense_review_health.py --pending-minutes 5 --json

退出码：
    0 正常；1 发现异常（可用于告警）；2 执行失败
"""

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

# 允许直接 `python scripts/check_expense_review_health.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core import database  # noqa: E402
from app.models.expense_claim import ExpenseClaim, ExpenseClaimStatus  # noqa: E402
from app.models.expense_pre_review import ExpensePreReview, PreReviewStatus  # noqa: E402
from app.utils.datetime_helper import utc_now  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查报销 AI 初审是否卡单")
    parser.add_argument(
        "--pending-minutes",
        type=int,
        default=10,
        help="初审 pending 超过多少分钟视为异常（默认 10）",
    )
    parser.add_argument(
        "--running-minutes",
        type=int,
        default=15,
        help="初审 running 超过多少分钟视为僵尸任务（默认 15）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出，便于接监控")
    return parser.parse_args()


async def collect_issues(
    *, pending_minutes: int, running_minutes: int
) -> dict[str, Any]:
    """汇总初审异常单据。"""
    now = utc_now()
    pending_deadline = now - timedelta(minutes=pending_minutes)
    running_deadline = now - timedelta(minutes=running_minutes)

    stuck_pending: list[dict[str, Any]] = []
    stuck_running: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    never_reviewed: list[dict[str, Any]] = []

    async with database.async_session() as session:
        claim_result = await session.execute(
            select(ExpenseClaim.id, ExpenseClaim.claim_no, ExpenseClaim.submitted_at)
            .where(
                ExpenseClaim.status == ExpenseClaimStatus.PENDING_APPROVAL.value
            )
        )
        claims = {
            row.id: {"claim_no": row.claim_no, "submitted_at": row.submitted_at}
            for row in claim_result.all()
        }

        if not claims:
            return {
                "checked_claims": 0,
                "stuck_pending": [],
                "stuck_running": [],
                "failed": [],
            }

        review_result = await session.execute(
            select(
                ExpensePreReview.claim_id,
                ExpensePreReview.status,
                ExpensePreReview.created_at,
                ExpensePreReview.started_at,
                ExpensePreReview.error_message,
            ).where(ExpensePreReview.claim_id.in_(list(claims.keys())))
        )

        latest: dict[int, Any] = {}

        for row in review_result.all():
            current = latest.get(row.claim_id)
            if current is None or (row.created_at and current.created_at and row.created_at > current.created_at):
                latest[row.claim_id] = row

        for claim_id, claim in claims.items():
            review = latest.get(claim_id)

            if review is None:
                submitted_at = claim["submitted_at"]
                if submitted_at is not None and submitted_at <= pending_deadline:
                    # 历史单据（功能上线前提交）本来就没有初审记录，
                    # 单独归类为「待补初审」，不参与告警判定。
                    never_reviewed.append(
                        {
                            "claim_no": claim["claim_no"],
                            "status": "missing",
                            "since": submitted_at.isoformat() if submitted_at else None,
                            "error_message": "没有任何 AI 初审记录",
                        }
                    )
                continue

            if review.status == PreReviewStatus.PENDING.value:
                if review.created_at is not None and review.created_at <= pending_deadline:
                    stuck_pending.append(
                        {
                            "claim_no": claim["claim_no"],
                            "status": review.status,
                            "since": review.created_at.isoformat(),
                            "error_message": review.error_message,
                        }
                    )
            elif review.status == PreReviewStatus.RUNNING.value:
                started_at = review.started_at or review.created_at
                if started_at is not None and started_at <= running_deadline:
                    stuck_running.append(
                        {
                            "claim_no": claim["claim_no"],
                            "status": review.status,
                            "since": started_at.isoformat(),
                            "error_message": review.error_message,
                        }
                    )
            elif review.status == PreReviewStatus.FAILED.value:
                failed.append(
                    {
                        "claim_no": claim["claim_no"],
                        "status": review.status,
                        "since": review.created_at.isoformat() if review.created_at else None,
                        "error_message": review.error_message,
                    }
                )

    return {
        "checked_claims": len(claims),
        "stuck_pending": stuck_pending,
        "stuck_running": stuck_running,
        "failed": failed,
        "never_reviewed": never_reviewed,
    }


def _print_human(result: dict[str, Any], *, pending_minutes: int, running_minutes: int) -> None:
    print(f"检查待审批单据：{result['checked_claims']} 张")
    print(f"pending 超时阈值：{pending_minutes} 分钟；running 超时阈值：{running_minutes} 分钟")

    def dump(title: str, rows: list[dict[str, Any]]) -> None:
        print(f"\n{title}（{len(rows)}）")
        for row in rows:
            print(
                f"  - {row['claim_no']} | {row['status']} | since={row['since']} | "
                f"{row['error_message'] or ''}"
            )

    dump("初审 pending 卡单（请检查 expense-review worker 是否运行）", result["stuck_pending"])
    dump("初审 running 僵尸任务", result["stuck_running"])
    dump("初审 failed（可在详情页重新初审）", result["failed"])
    dump("待补初审的历史单据（信息项，不告警）", result.get("never_reviewed") or [])

    if not (
        result["stuck_pending"] or result["stuck_running"] or result["failed"]
    ):
        print("\n✅ 初审队列正常")


async def main() -> int:
    args = _parse_args()
    database.init_db_engine()
    try:
        result = await collect_issues(
            pending_minutes=args.pending_minutes,
            running_minutes=args.running_minutes,
        )
    finally:
        await database.close_db_engine()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(
            result,
            pending_minutes=args.pending_minutes,
            running_minutes=args.running_minutes,
        )

    return 1 if (
        result["stuck_pending"] or result["stuck_running"] or result["failed"]
    ) else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001
        print(f"健康检查执行失败：{exc}", file=sys.stderr)
        sys.exit(2)
