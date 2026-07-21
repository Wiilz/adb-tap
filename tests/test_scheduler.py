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
