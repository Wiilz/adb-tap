"""点击引擎：在基准坐标附近随机偏移持续点击。"""

import random
import time


def run_clicks(
    device,
    base_x: int,
    base_y: int,
    *,
    interval_ms: int = 20,
    offset: int = 4,
    max_clicks: int | None = None,
    duration: float | None = None,
    on_progress=None,
    sleep=time.sleep,
    clock=time.time,
) -> int:
    """循环点击，返回总点击次数。

    - device：协议对象，需实现 tap(x, y)
    - interval_ms：点击间隔（毫秒），实际下限 10ms
    - offset：随机偏移像素（±offset）
    - max_clicks / duration：任一满足即停止；都为 None 则直到外部中断
    - on_progress(count)：每次点击后回调，用于 CLI 输出统计
    - sleep / clock：测试注入
    """
    interval = max(interval_ms, 10) / 1000.0
    start = clock()
    count = 0
    while True:
        if max_clicks is not None and count >= max_clicks:
            break
        if duration is not None and (clock() - start) >= duration:
            break
        tap_x = base_x + random.randint(-offset, offset)
        tap_y = base_y + random.randint(-offset, offset)
        device.tap(tap_x, tap_y)
        count += 1
        if on_progress is not None:
            on_progress(count)
        sleep(interval)
    return count
