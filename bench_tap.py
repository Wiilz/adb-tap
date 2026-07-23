"""input tap 吞吐基准：测量三种打法的真实点击频率。

对比：
- B0 当前方法（ACK 串行，单 shell）：每次 tap 后 echo ACK 并逐条等回执
- B1 单 shell 流水线（去 ACK）：批量写入，末尾 echo DONE，等 DONE 返回
- B2 多 shell 并行·盲打：K 个 shell 各发 per_worker 次（流水线），全部 DONE 即结束
- B3 多 shell 并行·ACK：K 个 shell 各做 per_worker 次 ACK-per-tap（复用 AdbShell.tap 语义）

用法：uv run python bench_tap.py <x> <y> [--taps 20] [--per-worker 20] [--workers 1,2,4,8]
"""

import argparse
import subprocess
import threading
import time

from adb_tap import device


def open_shell(adb: str, serial: str) -> subprocess.Popen:
    return subprocess.Popen(
        [adb, "-s", serial, "shell"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


def close_shell(proc: subprocess.Popen) -> None:
    try:
        if proc.stdin:
            proc.stdin.close()
    except BrokenPipeError:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def wait_for(proc: subprocess.Popen, marker: str) -> None:
    """从 stdout 读到含 marker 的行即返回；空行=EOF 抛错。"""
    assert proc.stdout is not None
    tag = marker.encode()
    while True:
        line = proc.stdout.readline()
        if line == b"":
            raise RuntimeError("shell EOF（意外断开）")
        if tag in line:
            return


def bench_ack(adb, serial, x, y, taps):
    """B0：当前方法——每次 tap + echo ACK，逐条等回执（串行）。"""
    proc = open_shell(adb, serial)
    t0 = time.perf_counter()
    for _ in range(taps):
        assert proc.stdin is not None
        proc.stdin.write(f"input tap {x} {y}\necho ACK\n".encode())
        proc.stdin.flush()
        wait_for(proc, "ACK")
    elapsed = time.perf_counter() - t0
    close_shell(proc)
    return taps, elapsed


def bench_fire_forget(adb, serial, x, y, taps):
    """B1：单 shell 流水线——一次性批量写入，末尾 echo DONE，等 DONE 返回。"""
    proc = open_shell(adb, serial)
    payload = (f"input tap {x} {y}\n" * taps).encode() + b"echo DONE\n"
    assert proc.stdin is not None
    t0 = time.perf_counter()
    proc.stdin.write(payload)
    proc.stdin.flush()
    wait_for(proc, "DONE")
    elapsed = time.perf_counter() - t0
    close_shell(proc)
    return taps, elapsed


def bench_parallel(adb, serial, x, y, per_worker, workers):
    """B2：多 shell 并行·盲打——K 个 shell 各发 per_worker 次（流水线），全部 DONE 即结束。"""
    procs = [open_shell(adb, serial) for _ in range(workers)]
    payload = (f"input tap {x} {y}\n" * per_worker).encode() + b"echo DONE\n"

    def fire(proc):
        assert proc.stdin is not None
        proc.stdin.write(payload)
        proc.stdin.flush()

    threads = [threading.Thread(target=fire, args=(p,)) for p in procs]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for p in procs:  # 逐个等 DONE（已完成的其 DONE 已在管道缓冲）
        wait_for(p, "DONE")
    elapsed = time.perf_counter() - t0
    for t in threads:
        t.join()
    for p in procs:
        close_shell(p)
    return per_worker * workers, elapsed


def bench_ack_parallel(adb, serial, x, y, per_worker, workers):
    """B3：多 shell 并行·ACK——每个 shell 做 per_worker 次 ACK-per-tap（复用 AdbShell.tap 语义）。"""
    procs = [open_shell(adb, serial) for _ in range(workers)]

    def tap_loop(proc, n):
        assert proc.stdin is not None
        for _ in range(n):
            proc.stdin.write(f"input tap {x} {y}\necho ACK\n".encode())
            proc.stdin.flush()
            wait_for(proc, "ACK")

    threads = [threading.Thread(target=tap_loop, args=(p, per_worker)) for p in procs]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0
    for p in procs:
        close_shell(p)
    return per_worker * workers, elapsed


def main() -> int:
    ap = argparse.ArgumentParser(description="input tap 吞吐基准")
    ap.add_argument("x", type=int, help="点击 x 坐标（务必空白区）")
    ap.add_argument("y", type=int, help="点击 y 坐标（务必空白区）")
    ap.add_argument("--taps", type=int, default=20, help="B0/B1 的点击数（默认 20）")
    ap.add_argument("--per-worker", type=int, default=20, help="B2/B3 每个 shell 的点击数（默认 20）")
    ap.add_argument("--workers", default="1,2,4,8", help="B2/B3 worker 数列表（默认 1,2,4,8）")
    args = ap.parse_args()

    adb = device.resolve_adb_path(None)
    serials = device.list_devices(adb)
    if not serials:
        raise SystemExit("无设备连接")
    serial = serials[0]
    workers = [int(k) for k in args.workers.split(",")]

    print(f"设备 {serial} | 目标 ({args.x},{args.y}) | taps={args.taps} per-worker={args.per_worker}\n")

    def rate(n, dt):
        return n / dt if dt > 0 else float("inf")

    print("【B0】当前方法（ACK 串行，单 shell）")
    n, dt = bench_ack(adb, serial, args.x, args.y, args.taps)
    print(f"  {n} 次 / {dt:.2f}s = {rate(n, dt):.1f} 次/秒\n")

    print("【B1】单 shell 流水线（去 ACK，批量写入）")
    n, dt = bench_fire_forget(adb, serial, args.x, args.y, args.taps)
    print(f"  {n} 次 / {dt:.2f}s = {rate(n, dt):.1f} 次/秒\n")

    print("【B2】多 shell 并行·盲打（每 shell 流水线）")
    base = None
    for k in workers:
        n, dt = bench_parallel(adb, serial, args.x, args.y, args.per_worker, k)
        r = rate(n, dt)
        if base is None:
            base = r
        mult = r / base if base else 0.0
        print(f"  K={k:<2}  {n:>3} 次 / {dt:.2f}s = {r:5.1f} 次/秒  (相对 K=1 ×{mult:.2f})")
    print()

    print("【B3】多 shell 并行·ACK（每 shell ACK-per-tap，复用 AdbShell.tap）")
    base = None
    for k in workers:
        n, dt = bench_ack_parallel(adb, serial, args.x, args.y, args.per_worker, k)
        r = rate(n, dt)
        if base is None:
            base = r
        mult = r / base if base else 0.0
        print(f"  K={k:<2}  {n:>3} 次 / {dt:.2f}s = {r:5.1f} 次/秒  (相对 K=1 ×{mult:.2f})")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
