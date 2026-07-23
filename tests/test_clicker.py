from adb_tap import clicker


class FakeDevice:
    """记录所有 tap 坐标；break_after=N 时第 N 次 tap 起抛 BrokenPipeError 模拟断连。"""

    def __init__(self, break_after: int | None = None) -> None:
        self.taps: list[tuple[int, int]] = []
        self._break_after = break_after

    def tap(self, x: int, y: int) -> None:
        if self._break_after is not None and len(self.taps) >= self._break_after:
            raise BrokenPipeError("模拟 shell 断开")
        self.taps.append((x, y))


def _factory_from(devices):
    """工厂：每次调用依次返回 devices 中的下一个设备。"""
    it = iter(devices)

    def factory():
        return next(it)

    return factory


def test_single_worker_counts_and_offsets():
    """单 worker：返回值与点击数一致，坐标落在 ±offset 内且偏移生效。"""
    device = FakeDevice()
    count = clicker.run_clicks(
        lambda: device, base_x=500, base_y=800, workers=1, max_clicks=200, offset=4
    )
    assert count == len(device.taps) == 200
    for x, y in device.taps:
        assert 496 <= x <= 504
        assert 796 <= y <= 804
    assert min(x for x, _ in device.taps) <= 498
    assert max(x for x, _ in device.taps) >= 502


def test_multiple_workers_aggregate_count():
    """多 worker：总计数 = 各设备 tap 之和；max_clicks 下最多超出 workers-1。"""
    devices = [FakeDevice() for _ in range(4)]
    count = clicker.run_clicks(
        _factory_from(devices), base_x=0, base_y=0, workers=4, max_clicks=100
    )
    assert 100 <= count <= 103  # 并行下最多超出 workers-1
    assert sum(len(d.taps) for d in devices) == count  # 每个 tap 都被计数


def test_factory_called_once_per_worker():
    """启动时应恰好为每个 worker 调用一次工厂。"""
    made = []

    def factory():
        d = FakeDevice()
        made.append(d)
        return d

    clicker.run_clicks(factory, base_x=0, base_y=0, workers=5, max_clicks=10)
    assert len(made) == 5


def test_stops_on_duration():
    """duration 到时停止（注入 clock：每次 tap 推进 0.02s）。"""
    state = {"t": 0.0}

    class ClockyDevice:
        def __init__(self) -> None:
            self.taps = 0

        def tap(self, x: int, y: int) -> None:
            state["t"] += 0.02
            self.taps += 1

    def fake_clock() -> float:
        return state["t"]

    device = ClockyDevice()
    count = clicker.run_clicks(
        lambda: device, base_x=0, base_y=0, workers=1, duration=0.1, clock=fake_clock
    )
    assert 4 <= count <= 7  # 0.1s / 0.02s ≈ 5 次


def test_max_clicks_triggers_before_duration():
    device = FakeDevice()
    count = clicker.run_clicks(
        lambda: device, base_x=0, base_y=0, workers=1, max_clicks=2, duration=100
    )
    assert count == len(device.taps) == 2


def test_on_progress_called_with_increasing_total():
    device = FakeDevice()
    progress: list[int] = []
    clicker.run_clicks(
        lambda: device, base_x=0, base_y=0, workers=1, max_clicks=3, on_progress=progress.append
    )
    assert progress == [1, 2, 3]


def test_reconnects_on_broken_pipe():
    """worker 遇 BrokenPipe 应重连并继续：第一个设备断前 1 次，重连后 2 次。"""
    devices = [FakeDevice(break_after=1), FakeDevice()]
    count = clicker.run_clicks(
        _factory_from(devices), base_x=0, base_y=0, workers=1, max_clicks=3
    )
    assert count == 3
    assert len(devices[0].taps) == 1
    assert len(devices[1].taps) == 2


def test_worker_gives_up_after_max_reconnect():
    """连续断连达 MAX_RECONNECT 后该 worker 放弃（无成功点击）。"""
    devices = [FakeDevice(break_after=0) for _ in range(clicker.MAX_RECONNECT + 1)]
    count = clicker.run_clicks(
        _factory_from(devices), base_x=0, base_y=0, workers=1, max_clicks=10
    )
    assert count == 0
