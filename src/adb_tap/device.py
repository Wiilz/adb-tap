"""ADB 设备连接：路径解析、设备检查、持久 shell 会话。"""

import os
import shutil
import subprocess
from pathlib import Path


def resolve_adb_path(explicit: str | None) -> str:
    """按优先级解析 ADB 可执行路径：显式参数 > 环境变量 ADB_PATH > PATH 中的 adb。

    找不到时抛 FileNotFoundError。
    """
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_path = os.environ.get("ADB_PATH")
    if env_path:
        candidates.append(env_path)
    which = shutil.which("adb")
    if which:
        candidates.append(which)

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError(
        "找不到 adb，请用 --adb-path 指定、设置环境变量 ADB_PATH，或将 adb 加入 PATH"
    )


def list_devices(adb_path: str) -> list[str]:
    """返回已连接设备序列号列表（排除 offline/unauthorized）。"""
    result = subprocess.run(
        [adb_path, "devices"],
        capture_output=True,
        text=True,
        check=True,
    )
    serials: list[str] = []
    for line in result.stdout.splitlines()[1:]:  # 跳过 "List of devices attached"
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


class AdbShell:
    """持久 adb shell 会话，通过 stdin 连续发送 input tap 命令。"""

    def __init__(self, adb_path: str) -> None:
        serials = list_devices(adb_path)
        if not serials:
            raise RuntimeError("没有已连接的设备，请用 adb devices 检查连接")
        self._adb_path = adb_path
        self.serial = serials[0]
        # 启动持久 shell，绑定到第一个设备
        self._process = subprocess.Popen(
            [adb_path, "-s", self.serial, "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def tap(self, x: int, y: int) -> None:
        """向 shell stdin 写入 input tap 命令。写入失败抛 BrokenPipeError。"""
        if self._process.stdin is None:
            raise BrokenPipeError("shell stdin 不可用")
        self._process.stdin.write(f"input tap {x} {y}\n".encode())
        self._process.stdin.flush()

    def close(self) -> None:
        """关闭 stdin 并等待 shell 进程退出。"""
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except BrokenPipeError:
                pass
        self._process.wait(timeout=5)


def monitor_touches(adb_path: str, serial: str) -> None:
    """实时打印手指触摸坐标，供 preset get 取点用。

    解析 `getevent -l` 的 ABS_MT_POSITION_X / ABS_MT_POSITION_Y 事件。
    部分设备返回的是输入设备原始坐标（非屏幕像素）；如数值与屏幕不符，
    改用安卓「设置 → 开发者选项 → 指针位置」查看准确坐标。按 Ctrl+C 退出。
    """
    proc = subprocess.Popen(
        [adb_path, "-s", serial, "shell", "getevent", "-l"],
        stdout=subprocess.PIPE,
        text=True,
    )
    x = y = None
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if "ABS_MT_POSITION_X" in line:
                x = int(line.split()[-1], 16)
            elif "ABS_MT_POSITION_Y" in line:
                y = int(line.split()[-1], 16)
            elif line.startswith("EV_SYN") and x is not None and y is not None:
                print(f"\r触摸坐标: ({x}, {y})", end="", flush=True)
                x = y = None
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


if __name__ == "__main__":
    # 自检：解析路径 → 检查设备 → 启动 shell → 发一次测试 tap
    adb = resolve_adb_path(None)
    print(f"ADB 路径: {adb}")
    devices = list_devices(adb)
    print(f"已连接设备: {devices}")
    if not devices:
        raise SystemExit("无设备连接")
    shell = AdbShell(adb)
    shell.tap(500, 500)
    print("测试 tap 已发送到 (500, 500)")
    shell.close()
