"""定时触发：NTP 校时与目标时间解析。"""

import time
from datetime import datetime, timedelta

import ntplib


def sync_offset(server: str, timeout: float = 3.0) -> float:
    """向 NTP 服务器请求，返回偏移量（网络时间 - 本地时间，单位秒）。

    失败时抛出异常，由调用方决定如何处理。
    """
    client = ntplib.NTPClient()
    response = client.request(server, timeout=timeout)
    return float(response.offset)


def calibrated_now(offset: float) -> float:
    """返回校准后的当前 Unix 时间戳。"""
    return time.time() + offset


def parse_target_time(hhmmss: str, now: datetime | None = None) -> float:
    """将 HH:MM:SS 解析为最近的目标 Unix 时间戳。

    若今天的该时刻已过（严格早于 now）则顺延到明天；恰等于 now 时按今天处理。
    `now` 仅用于测试注入。
    """
    now = now if now is not None else datetime.now()
    hour, minute, second = (int(part) for part in hhmmss.split(":"))
    target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if target < now:
        target += timedelta(days=1)
    return target.timestamp()
