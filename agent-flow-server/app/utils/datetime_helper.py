from zoneinfo import ZoneInfo
from datetime import datetime, timezone


def get_beijing_now_str() -> str:
    """获取北京时间，格式：2026-10-26 05:54"""
    bj_tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M")

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


if __name__ == '__main__':
    print(get_beijing_now_str())