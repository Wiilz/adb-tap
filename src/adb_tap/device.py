"""ADB 设备连接：路径解析、设备检查、持久 shell 会话。"""

import os
import shutil
import subprocess
import time


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
    for line in result.stdout.splitlines():
        line = line.strip()
        # 跳过空行、表头与 daemon 启动消息
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


class AdbShell:
    """持久 adb shell 会话，通过 stdin 连续发送 input tap 命令。

    tap 采用「发后确认」：每条命令后跟一个 echo ACK 标记，并同步读取
    shell 的 stdout 直到收到该标记。这样能确保程序侧的点击计数与手机
    真实执行节奏一致，且 Ctrl-C 退出后不会因管道积压而继续点击。
    """

    # 回执确认标记（设备 shell 执行完 tap 后 echo 出来）
    ACK = "__ADB_TAP_ACK__"

    def __init__(self, adb_path: str, serial: str | None = None) -> None:
        # serial 已知（并行场景复用）时跳过 list_devices，避免多次 adb devices
        if serial is None:
            serials = list_devices(adb_path)
            if not serials:
                raise RuntimeError("没有已连接的设备，请用 adb devices 检查连接")
            serial = serials[0]
        self._adb_path = adb_path
        self.serial = serial
        # 启动持久 shell，绑定到该设备；stdout 用管道读取回执
        self._process = subprocess.Popen(
            [adb_path, "-s", self.serial, "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def tap(self, x: int, y: int) -> None:
        """发送 input tap 并同步等待 shell 回执，确保命令真正执行完毕。

        shell 已断（stdout EOF）时抛 BrokenPipeError 供上层重连。
        """
        if self._process.stdin is None or self._process.stdout is None:
            raise BrokenPipeError("shell 管道不可用")
        try:
            self._process.stdin.write(
                f"input tap {x} {y}\necho {self.ACK}\n".encode()
            )
            self._process.stdin.flush()
        except BrokenPipeError:
            raise
        except OSError as exc:
            raise BrokenPipeError("shell stdin 写入失败") from exc

        # 同步读取 stdout，直到收到本命令的 ACK 标记
        while True:
            line = self._process.stdout.readline()
            if line == b"":
                # EOF：shell 进程已退出
                raise BrokenPipeError("shell 已断开（读取回执时 EOF）")
            if self.ACK.encode() in line:
                return

    def close(self) -> None:
        """关闭 stdin 并等待 shell 进程退出，超时后强制 kill。"""
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()


def _parse_touch_line(line: str, state: dict) -> tuple[int | None, int | None] | None:
    """解析一行 getevent -l 输出，更新 state["x"]/state["y"]。

    命中 EV_SYN 且已拿到坐标时，返回当前 (x, y) 坐标元组并把 state 清零
    （等待下一帧）；否则返回 None。X 或 Y 任一已知即输出（放宽同帧必须
    同时出现的要求，适配多点协议 B 中坐标分散在多个 SYN 帧的设备）。
    非法 hex 行被跳过，不更新坐标、不抛异常。
    """
    line = line.strip()
    try:
        if "ABS_MT_POSITION_X" in line:
            state["x"] = int(line.split()[-1], 16)
        elif "ABS_MT_POSITION_Y" in line:
            state["y"] = int(line.split()[-1], 16)
        elif "EV_SYN" in line:
            # 真实 getevent -l 行带 "/dev/input/eventN: " 前缀，
            # 故用包含匹配而非 startswith
            if state["x"] is not None or state["y"] is not None:
                coords = (state["x"], state["y"])
                state["x"] = state["y"] = None
                return coords
    except ValueError:
        # 某些设备 getevent token 非合法 hex，跳过该行
        pass
    return None


class _LineSplitter:
    """把字节流增量切分为文本行。

    getevent 经 adb 输出到 Windows 管道时是流式的，且行尾为 \\r\\n；
    直接对 text=True 的 stdout 做逐行迭代在这种场景下不可靠（数据已到
    但行迭代器不产出）。因此改用二进制读取 + 本类手动按 \\n 切行，
    未遇到 \\n 的尾部缓冲起来等待下次拼接。
    """

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, chunk: bytes) -> list[str]:
        """喂入一段字节，返回本次切出的完整行（已去掉 \\r、按 utf-8 解码）。"""
        self._buf += chunk
        parts = self._buf.split(b"\n")
        self._buf = parts.pop()  # 最后一段可能不完整，留待下次
        return [p.rstrip(b"\r").decode("utf-8", errors="replace") for p in parts]

    def flush(self) -> list[str]:
        """返回缓冲区中未完成的部分（进程结束时调用）。"""
        if not self._buf:
            return []
        line = self._buf.rstrip(b"\r").decode("utf-8", errors="replace")
        self._buf = b""
        return [line]


def _stream_lines(stream, is_alive, max_idle: int | None = None):
    """生成器：从二进制流持续读出完整文本行。

    关键：`BufferedReader.read1` 在数据暂时未到时返回空字节，这不代表
    EOF（getevent 监听等待触摸时就处于这种状态）。只有当 is_alive() 为
    False（进程已退出）且读到空时才是真正的 EOF，此时停止。

    - is_alive()：返回子进程是否仍在运行（如 proc.poll() is None）
    - max_idle：连续多少次「空读且进程仍活」后强制停止；None 表示不限
      （真实监听用 None，一直等到 Ctrl+C 或进程退出；测试用有限值防死循环）
    """
    splitter = _LineSplitter()
    idle = 0
    while True:
        chunk = stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
        if chunk:
            idle = 0
            for line in splitter.feed(chunk):
                yield line
            continue
        # 空读：区分真 EOF 与暂无数据
        if not is_alive():
            break  # 进程已退出且读尽，真 EOF
        idle += 1
        if max_idle is not None and idle >= max_idle:
            break
        time.sleep(0.05)  # 暂无数据但进程仍活，小睡避免忙轮询
    for line in splitter.flush():
        yield line


def monitor_touches(adb_path: str, serial: str) -> None:
    """实时打印手指触摸坐标，供 preset get 取点用。

    解析 `getevent -l` 的 ABS_MT_POSITION_X / ABS_MT_POSITION_Y 事件，
    每帧（EV_SYN）逐行打印当前坐标。部分设备返回的是输入设备原始坐标
    （非屏幕像素）；如数值与屏幕不符，改用安卓「设置 → 开发者选项 →
    指针位置」查看准确坐标。按 Ctrl+C 退出。
    """
    proc = subprocess.Popen(
        [adb_path, "-s", serial, "shell", "getevent", "-l"],
        stdout=subprocess.PIPE,  # 二进制模式，手动切行（见 _LineSplitter）
    )
    state = {"x": None, "y": None}
    try:
        assert proc.stdout is not None
        # max_idle=None：一直监听到 Ctrl+C 或 getevent 进程退出
        for line in _stream_lines(proc.stdout, is_alive=lambda: proc.poll() is None):
            coords = _parse_touch_line(line, state)
            if coords is not None:
                # 逐行打印（带换行 + flush），避免输出被终端缓冲吞掉
                print(f"触摸坐标: ({coords[0]}, {coords[1]})", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    # 自检：解析路径 → 检查设备 → 启动 shell → 发一次测试 tap
    adb = resolve_adb_path(None)
    print(f"ADB 路径: {adb}")
    devices = list_devices(adb)
    print(f"已连接设备: {devices}")
    if not devices:
        raise SystemExit("无设备连接")
    shell = AdbShell(adb)
    try:
        shell.tap(500, 500)
        print("测试 tap 已发送到 (500, 500)")
    finally:
        shell.close()
