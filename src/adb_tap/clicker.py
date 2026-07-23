"""点击引擎：多 shell 并行点击，在基准坐标附近随机偏移。"""

import random
import threading
import time
from typing import Callable, Protocol


class TapDevice(Protocol):
    """点击设备协议：需实现 tap(x, y)。"""

    def tap(self, x: int, y: int) -> None: ...


# 单 worker 连续断开的重连上限
MAX_RECONNECT = 3


class _Counter:
    """线程安全计数器：多 worker 并发累加点击数。"""

    def __init__(self) -> None:
        self._n = 0
        self._lock = threading.Lock()

    def inc(self) -> int:
        """自增并返回新值。"""
        with self._lock:
            self._n += 1
            return self._n

    @property
    def value(self) -> int:
        with self._lock:
            return self._n


def _close_quietly(device: TapDevice) -> None:
    """关闭设备（若有 close），忽略异常：用于 worker 重连前与退出前清理。"""
    close = getattr(device, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def run_clicks(
    device_factory: Callable[[], TapDevice],
    base_x: int,
    base_y: int,
    *,
    workers: int = 12,
    offset: int = 4,
    max_clicks: int | None = None,
    duration: float | None = None,
    on_progress: Callable[[int], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """开 workers 个设备并行点击，返回总点击次数。

    - device_factory：每次调用返回一个新 TapDevice（如 ``lambda: AdbShell(adb, serial)``）
    - workers：并行 shell 数（实测甜点约 12，未 root 真机约 15 次/秒）
    - offset：随机偏移像素（±offset）
    - max_clicks / duration：任一满足（按全局聚合计数/耗时）即停止；都为 None 则点击至
      Ctrl+C（KeyboardInterrupt 会在停掉所有 worker、关闭设备后重新抛出）
    - on_progress(total)：每次点击后回调（聚合真实执行数），应保持轻量
    - clock：用于 duration 计时；默认 monotonic，不受系统时间调整影响

    每个 worker 采用「发后确认」（ACK-per-tap）：一次只一条在途命令，故 Ctrl+C 后
    最多残留 workers 次在途点击，无管道积压。
    """
    counter = _Counter()
    stop = threading.Event()
    deadline = (clock() + duration) if duration is not None else None
    created: list[TapDevice] = []

    def factory() -> TapDevice:
        dev = device_factory()
        created.append(dev)
        return dev

    def worker(dev: TapDevice) -> None:
        reconnects = 0
        while not stop.is_set():
            if max_clicks is not None and counter.value >= max_clicks:
                break
            if deadline is not None and clock() >= deadline:
                break
            tap_x = base_x + random.randint(-offset, offset)
            tap_y = base_y + random.randint(-offset, offset)
            try:
                dev.tap(tap_x, tap_y)
            except BrokenPipeError:
                if reconnects >= MAX_RECONNECT:
                    break  # 该 worker 放弃，其余继续
                reconnects += 1
                _close_quietly(dev)
                dev = factory()
                continue
            total = counter.inc()
            if on_progress is not None:
                on_progress(total)

    try:
        devices = [factory() for _ in range(workers)]
        threads = [threading.Thread(target=worker, args=(d,)) for d in devices]
        for t in threads:
            t.start()
        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            stop.set()
            for t in threads:
                t.join()
            raise
    finally:
        for dev in created:
            _close_quietly(dev)
    return counter.value
