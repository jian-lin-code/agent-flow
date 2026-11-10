
import re
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ResolvedTimeRange:
    date_from: date | None
    date_to: date | None
    recognized: bool = True


def resolve_time_expression(
    expression: str | None,
    *,
    today: date | None = None,
) -> ResolvedTimeRange:
    """
    将用户的自然语言时间表达转换为日期范围。

    today 参数主要用于测试，生产环境默认使用上海时区日期。
    """
    if today is None:
        today = datetime.now(BUSINESS_TIMEZONE).date()

    if not expression or not expression.strip():
        return ResolvedTimeRange(None, None)

    value = expression.strip()

    # 今天
    if value in ("今天", "今日"):
        return ResolvedTimeRange(today, today)

    # 昨天
    if value in ("昨天", "昨日"):
        yesterday = today - timedelta(days=1)
        return ResolvedTimeRange(yesterday, yesterday)

    # 本周：周一至今天
    if value in ("本周", "这周", "这一周"):
        start = today - timedelta(days=today.weekday())
        return ResolvedTimeRange(start, today)

    # 上周：上周一至上周日
    if value in ("上周", "上一周"):
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        last_sunday = this_monday - timedelta(days=1)
        return ResolvedTimeRange(last_monday, last_sunday)

    # 本月：当月 1 日至今天
    if value in ("本月", "这个月", "当月"):
        start = today.replace(day=1)
        return ResolvedTimeRange(start, today)

    # 上个月：上月 1 日至月末
    if value in ("上个月", "上月"):
        current_month_start = today.replace(day=1)
        last_month_end = current_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return ResolvedTimeRange(last_month_start, last_month_end)

    # 今年：1 月 1 日至今天
    if value in ("今年", "本年"):
        return ResolvedTimeRange(
            date(today.year, 1, 1),
            today,
        )

    # 去年：全年
    if value in ("去年", "上一年"):
        return ResolvedTimeRange(
            date(today.year - 1, 1, 1),
            date(today.year - 1, 12, 31),
        )

    # 最近 N 天，包含今天
    match = re.fullmatch(r"最近\s*(\d+)\s*天", value)
    if match:
        days = int(match.group(1))
        if days < 1:
            return ResolvedTimeRange(None, None, recognized=False)

        start = today - timedelta(days=days - 1)
        return ResolvedTimeRange(start, today)

    # 「最近」「近期」「这几天」等口语表达：默认映射最近 7 天
    if value in ("最近", "近期", "近来", "这几天", "这阵子", "这一阵", "最近几天", "最近一段时间"):
        return ResolvedTimeRange(today - timedelta(days=6), today)

    # 最近一周 / 最近一个月 / 最近半年
    match = re.fullmatch(r"最近\s*(一\s*个?\s*)?(周|星期|礼拜)", value)
    if match:
        return ResolvedTimeRange(today - timedelta(days=6), today)

    match = re.fullmatch(r"最近\s*(一\s*个?\s*)?月", value)
    if match:
        start = today.replace(day=1)
        return ResolvedTimeRange(start, today)

    # 最近 N 个月
    match = re.fullmatch(r"最近\s*(\d+)\s*个?\s*月", value)
    if match:
        months = int(match.group(1))
        if months < 1:
            return ResolvedTimeRange(None, None, recognized=False)
        year = today.year
        month = today.month - months
        while month <= 0:
            month += 12
            year -= 1
        start_day = min(today.day, calendar.monthrange(year, month)[1])
        return ResolvedTimeRange(date(year, month, start_day), today)

    match = re.fullmatch(r"最近\s*半年", value)
    if match:
        return ResolvedTimeRange(today - timedelta(days=182), today)

    # YYYY年M月 / YYYY-MM / YYYY-M
    match = re.fullmatch(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月?",
        value,
    )
    if not match:
        match = re.fullmatch(r"(\d{4})-(\d{1,2})", value)

    if match:
        year = int(match.group(1))
        month = int(match.group(2))

        if not 1 <= month <= 12:
            return ResolvedTimeRange(None, None, recognized=False)

        last_day = calendar.monthrange(year, month)[1]

        return ResolvedTimeRange(
            date(year, month, 1),
            date(year, month, last_day),
        )

    # M月：默认当前年份
    match = re.fullmatch(r"(\d{1,2})\s*月", value)
    if match:
        month = int(match.group(1))

        if not 1 <= month <= 12:
            return ResolvedTimeRange(None, None, recognized=False)

        last_day = calendar.monthrange(today.year, month)[1]

        return ResolvedTimeRange(
            date(today.year, month, 1),
            date(today.year, month, last_day),
        )

    return ResolvedTimeRange(None, None, recognized=False)
