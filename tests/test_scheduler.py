import time
from datetime import datetime, timedelta
from unittest.mock import patch

import ntplib
import pytest

from adb_tap import scheduler


def _make_response(server_offset: float) -> ntplib.NTPStats:
    """构造 NTPStats，模拟瞬时往返下服务器相对本地快/慢 server_offset 秒。

    ntplib.NTPStats.offset 公式：
        ((recv - orig) + (tx - dest)) / 2

    其中：
      orig  —— 客户端发送请求时的本地时间
      recv  —— 服务端接收请求时的服务端时间
      tx    —— 服务端发送响应时的服务端时间
      dest  —— 客户端接收响应时的本地时间

    若服务器相对本地偏移 server_offset 秒（网络时间 - 本地时间），
    且往返瞬时，则 recv/tx（服务端时钟）相对 orig/dest（本地时钟）
    整体领先 server_offset。
    """
    stats = ntplib.NTPStats()
    # 基准取 0.0 避免大数减小时的浮点精度误差（原 1_000_000.0 下
    # 999999.7 - 1000000.0 会引入 ~4.6e-11 误差，使 .offset != server_offset）
    local_now = 0.0
    stats.orig_timestamp = local_now
    stats.recv_timestamp = local_now + server_offset
    stats.tx_timestamp = local_now + server_offset
    stats.dest_timestamp = local_now
    return stats


def test_sync_offset_returns_positive_offset():
    """服务器快 0.5 秒时，偏移应为正。"""
    with patch("adb_tap.scheduler.ntplib.NTPClient") as MockClient:
        MockClient.return_value.request.return_value = _make_response(0.5)
        offset = scheduler.sync_offset("ntp.aliyun.com", timeout=3.0)
    assert offset == 0.5


def test_sync_offset_returns_negative_offset():
    """服务器慢 0.3 秒时，偏移应为负。"""
    with patch("adb_tap.scheduler.ntplib.NTPClient") as MockClient:
        MockClient.return_value.request.return_value = _make_response(-0.3)
        offset = scheduler.sync_offset("ntp.aliyun.com", timeout=3.0)
    assert offset == -0.3


def test_parse_target_time_today():
    """目标时间在今天范围内。"""
    now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    target = scheduler.parse_target_time("12:00:00", now=now)
    expected = (now + timedelta(hours=2)).timestamp()
    assert target == expected


def test_parse_target_time_rolls_to_tomorrow():
    """目标时间已过，顺延到明天。"""
    now = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
    target = scheduler.parse_target_time("12:00:00", now=now)
    expected = (now + timedelta(days=1) - timedelta(hours=2)).timestamp()
    assert target == expected


@pytest.mark.parametrize("bad", ["12:00", "25:00:00", "12:60:00", "abc", "", "12:00:00:00"])
def test_parse_target_time_rejects_invalid(bad):
    with pytest.raises((ValueError, IndexError)):
        scheduler.parse_target_time(bad, now=datetime.now())


def test_parse_target_time_exactly_now_keeps_today():
    """恰好在目标时刻调用时按今天处理，不顺延到明天。"""
    now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    target = scheduler.parse_target_time("12:00:00", now=now)
    assert target == now.timestamp()


def test_wait_until_returns_immediately_when_past():
    ticks: list[str] = []
    target = scheduler.calibrated_now(0.0) - 1.0  # 已过 1 秒
    scheduler.wait_until(target, offset=0.0, on_tick=ticks.append)
    assert ticks == []


def test_wait_until_counts_down_in_final_seconds():
    """模拟最后几秒逐秒刷新。"""
    ticks: list[str] = []
    # 可控时钟：每次调用推进 1 秒；序列对应 remaining = 3,2,1,0(退出)
    times = iter([0.0, 1.0, 2.0, 3.0])

    def fake_clock():
        return next(times)

    def fake_sleep(_seconds: float) -> None:
        pass

    scheduler.wait_until(3.0, offset=0.0, on_tick=ticks.append,
                         sleep=fake_sleep, clock=fake_clock)
    assert ticks == ["00:03", "00:02", "00:01"]


def test_format_remaining_handles_hours_and_minutes():
    assert scheduler._format_remaining(125) == "02:05"
    assert scheduler._format_remaining(3725) == "1:02:05"


def test_calibrated_now_applies_offset():
    """calibrated_now 在正偏移下应返回更大的时间戳。"""
    base = time.time()
    assert scheduler.calibrated_now(5.0) >= base + 5.0
    assert scheduler.calibrated_now(-5.0) <= base


def test_wait_until_refreshes_every_second():
    """倒计时应逐秒刷新，让用户看到持续变化的剩余时间。"""
    ticks: list[str] = []
    elapsed = [0.0]

    def fake_sleep(seconds: float) -> None:
        elapsed[0] += seconds

    def fake_clock() -> float:
        return elapsed[0]

    scheduler.wait_until(65.0, offset=0.0, on_tick=ticks.append,
                         sleep=fake_sleep, clock=fake_clock)
    assert ticks[0] == "01:05"
    assert ticks[1] == "01:04"
    assert ticks[59] == "00:06"
    assert ticks[-1] == "00:01"
    assert len(ticks) == 65


def test_wait_until_signals_clear_when_crossing_hour_boundary():
    """跨小时边界（1:00:00 → 59:59）时标记 clear，供 CLI 清除行内残留。

    CLI 用 \\r 行内刷新，新串比旧串短会残留旧字符形成 '59:5600'，
    因此 wait_until 在串变短时应通过 clear=True 告知调用方先清行。
    """
    ticks: list[tuple[str, bool]] = []
    elapsed = [0.0]

    def fake_sleep(seconds: float) -> None:
        elapsed[0] += seconds

    def fake_clock() -> float:
        return elapsed[0]

    # 从 1 小时以上跨到 1 小时以内
    scheduler.wait_until(3660.0, offset=0.0, on_tick=lambda r, clear=False: ticks.append((r, clear)),
                         sleep=fake_sleep, clock=fake_clock)
    assert ticks[0] == ("1:01:00", False)
    assert ticks[61] == ("59:59", True)
    # 不足 1 小时后一直 clear，不会再变长
    assert all(clear for _, clear in ticks[61:])


def test_wait_until_applies_offset():
    """offset 与 clock 同侧相加：offset=-5、target=10 时首次剩余 15s。"""
    ticks: list[str] = []
    elapsed = [0.0]

    def fake_sleep(seconds: float) -> None:
        elapsed[0] += seconds

    def fake_clock() -> float:
        return elapsed[0]

    scheduler.wait_until(10.0, offset=-5.0, on_tick=ticks.append,
                         sleep=fake_sleep, clock=fake_clock)
    assert ticks[0] == "00:15"
