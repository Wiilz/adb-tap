"""定时触发：NTP 校时与目标时间解析。"""

import time
from datetime import datetime, timedelta
from typing import Callable

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


def _format_remaining(seconds: float) -> str:
    """将剩余秒数格式化为 H:MM:SS 或 MM:SS。"""
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def wait_until(
    target: float,
    offset: float,
    on_tick: Callable[[str], None],
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> None:
    """阻塞直到校准时间到达 target。

    - on_tick(remaining_str, clear=False)：每次刷新调用，clear=True 时
      调用方应先清掉行内残留（跨小时边界字符串会变短）
    - sleep / clock：用于测试注入
    """
    while True:
        remaining = target - (clock() + offset)
        if remaining <= 0:
            return
        # 不足 1 小时的串短于 H:MM:SS，用行内刷新前需清掉旧尾部
        # clear 用关键字传入，兼容只接收单参数的简单回调（如 list.append）
        try:
            on_tick(_format_remaining(remaining), clear=remaining < 3600)
        except TypeError:
            on_tick(_format_remaining(remaining))
        sleep(1.0)  # 逐秒刷新，让用户看到持续变化的倒计时
