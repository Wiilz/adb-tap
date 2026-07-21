from adb_tap import clicker


class FakeDevice:
    def __init__(self) -> None:
        self.taps: list[tuple[int, int]] = []

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))


def test_clicks_stay_within_offset():
    device = FakeDevice()
    count = clicker.run_clicks(device, base_x=500, base_y=800, max_clicks=200,
                               interval_ms=1, offset=4)
    for x, y in device.taps:
        assert 496 <= x <= 504
        assert 796 <= y <= 804
    assert count == len(device.taps) == 200  # 返回值与点击数一致
    # 偏移两端都被访问（200 次采样下几乎必然）
    assert min(x for x, _ in device.taps) <= 498
    assert max(x for x, _ in device.taps) >= 502


def test_clicks_include_some_non_center():
    """200 次中应有大量非中心点（随机偏移生效）。"""
    device = FakeDevice()
    clicker.run_clicks(device, base_x=500, base_y=800, max_clicks=200,
                       interval_ms=1, offset=4)
    off_center = [t for t in device.taps if t != (500, 800)]
    assert len(off_center) > 150


def test_stops_on_duration():
    device = FakeDevice()
    # 模拟时钟：每次 sleep 推进 0.02 秒
    t = [0.0]

    def fake_sleep(_s: float) -> None:
        t[0] += 0.02

    def fake_clock() -> float:
        return t[0]

    clicker.run_clicks(device, base_x=0, base_y=0, interval_ms=20,
                       duration=0.1, sleep=fake_sleep, clock=fake_clock)
    # duration=0.1s、间隔 0.02s → 约 5-6 次点击
    assert 4 <= len(device.taps) <= 7


def test_interval_clamped_to_minimum():
    device = FakeDevice()
    sleeps: list[float] = []
    clicker.run_clicks(device, base_x=0, base_y=0, max_clicks=3,
                       interval_ms=1, sleep=sleeps.append)
    # interval_ms=1 应被钳制到 10ms
    assert all(s == 0.01 for s in sleeps)


def test_on_progress_called_with_increasing_count():
    device = FakeDevice()
    progress: list[int] = []
    clicker.run_clicks(device, base_x=0, base_y=0, max_clicks=3,
                       interval_ms=1, on_progress=progress.append)
    assert progress == [1, 2, 3]


def test_returns_count_matching_taps():
    device = FakeDevice()
    count = clicker.run_clicks(device, base_x=0, base_y=0, max_clicks=5, interval_ms=1)
    assert count == 5 == len(device.taps)


def test_max_clicks_triggers_before_duration():
    """max_clicks 与 duration 同时设置时，max_clicks 先触发。"""
    device = FakeDevice()
    clicker.run_clicks(device, base_x=0, base_y=0, max_clicks=2,
                       duration=100, interval_ms=1)
    assert len(device.taps) == 2
