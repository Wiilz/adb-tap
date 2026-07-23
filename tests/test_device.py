import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from adb_tap import device


def test_resolve_prefers_explicit_arg(tmp_path):
    fake_adb = tmp_path / "adb.exe"
    fake_adb.write_text("fake")
    with patch.dict("os.environ", {"ADB_PATH": "/env/adb"}):
        with patch("adb_tap.device.shutil.which", return_value="/which/adb"):
            result = device.resolve_adb_path(str(fake_adb))
    assert result == str(fake_adb)


def test_resolve_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("ADB_PATH", "/env/adb.exe")
    monkeypatch.setattr(device.shutil, "which", lambda _: None)
    monkeypatch.setattr(device.os.path, "isfile", lambda p: p == "/env/adb.exe")
    result = device.resolve_adb_path(None)
    assert result == "/env/adb.exe"


def test_resolve_falls_back_to_which(monkeypatch):
    monkeypatch.delenv("ADB_PATH", raising=False)
    monkeypatch.setattr(device.shutil, "which", lambda _: "/usr/bin/adb")
    monkeypatch.setattr(device.os.path, "isfile", lambda p: True)
    result = device.resolve_adb_path(None)
    assert result == "/usr/bin/adb"


def test_resolve_raises_when_not_found(monkeypatch):
    monkeypatch.delenv("ADB_PATH", raising=False)
    monkeypatch.setattr(device.shutil, "which", lambda _: None)
    with pytest.raises(FileNotFoundError):
        device.resolve_adb_path(None)


def test_list_devices_parses_online_devices():
    fake_output = (
        "List of devices attached\n"
        "emulator-5554\tdevice\n"
        "emulator-5556\toffline\n"
        "abc123\tunauthorized\n"
    )
    with patch("adb_tap.device.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(stdout=fake_output)
        serials = device.list_devices("adb")
    assert serials == ["emulator-5554"]


def test_list_devices_ignores_daemon_messages():
    fake_output = (
        "* daemon not running; starting now\n"
        "* daemon started successfully\n"
        "List of devices attached\n"
    )
    with patch("adb_tap.device.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(stdout=fake_output)
        serials = device.list_devices("adb")
    assert serials == []


# --- monitor_touches 解析逻辑 ---

def test_parse_touch_line_captures_x_y():
    """X/Y 坐标应分别被捕获并保留（用带设备前缀的真实 getevent -l 格式）。"""
    state = {"x": None, "y": None}
    assert device._parse_touch_line(
        "/dev/input/event3: EV_ABS       ABS_MT_POSITION_X    00000258            ", state
    ) is None
    assert state["x"] == 0x258
    assert device._parse_touch_line(
        "/dev/input/event3: EV_ABS       ABS_MT_POSITION_Y    0000039a            ", state
    ) is None
    assert state["y"] == 0x39A


def test_parse_touch_line_syn_with_partial_coords_emits():
    """EV_SYN 时只要 X 或 Y 任一已知就应输出（放宽：不要求同帧都有）。"""
    state = {"x": 600, "y": None}
    assert device._parse_touch_line(
        "/dev/input/event3: EV_SYN       SYN_REPORT           00000000            ", state
    ) == (600, None)
    # 输出后坐标应清零，等下一帧
    assert state == {"x": None, "y": None}


def test_parse_touch_line_syn_with_only_y_emits():
    """只有 Y 时也应在 SYN 输出（适配 Y 坐标单独成帧的设备）。"""
    state = {"x": None, "y": 1300}
    assert device._parse_touch_line(
        "/dev/input/event3: EV_SYN       SYN_REPORT           00000000            ", state
    ) == (None, 1300)


def test_parse_touch_line_syn_without_coords_no_emit():
    """完全没有坐标时 SYN 不输出。"""
    state = {"x": None, "y": None}
    assert device._parse_touch_line(
        "/dev/input/event3: EV_SYN       SYN_REPORT           00000000            ", state
    ) is None


def test_parse_touch_line_ignores_unrelated():
    state = {"x": None, "y": None}
    assert device._parse_touch_line(
        "/dev/input/event3: EV_ABS       ABS_MT_TRACKING_ID   00000001            ", state
    ) is None
    assert state == {"x": None, "y": None}


def test_parse_touch_line_bad_hex_skipped():
    """非法 hex 不应抛异常，也不更新坐标。"""
    state = {"x": 100, "y": 200}
    assert device._parse_touch_line(
        "/dev/input/event3: EV_ABS       ABS_MT_POSITION_X    zzzzzz            ", state
    ) is None
    assert state["x"] == 100


def test_parse_touch_line_full_frame_emits_both_coords():
    """完整一帧（X、Y、SYN）应输出两个坐标。"""
    state = {"x": None, "y": None}
    device._parse_touch_line("/dev/input/event3: EV_ABS       ABS_MT_POSITION_X    00000258", state)
    device._parse_touch_line("/dev/input/event3: EV_ABS       ABS_MT_POSITION_Y    0000039a", state)
    assert device._parse_touch_line(
        "/dev/input/event3: EV_SYN       SYN_REPORT           00000000", state
    ) == (0x258, 0x39A)
    assert state == {"x": None, "y": None}


# --- AdbShell 回执确认 ---

def _make_shell_with_pipes(monkeypatch, stdout_bytes: bytes):
    """构造一个 AdbShell，其 _process 用假管道：stdin 可写、stdout 预置内容。"""
    fake_stdin = io.BytesIO()
    fake_stdout = io.BytesIO(stdout_bytes)
    fake_proc = SimpleNamespace(stdin=fake_stdin, stdout=fake_stdout)
    monkeypatch.setattr(device, "list_devices", lambda _p: ["serial-1"])
    monkeypatch.setattr(device.subprocess, "Popen", lambda *a, **k: fake_proc)
    shell = device.AdbShell("adb")
    return shell, fake_stdin


def test_tap_waits_for_ack(monkeypatch):
    """tap 写入命令后应同步读取 stdout 直到收到 ACK 标记。"""
    shell, fake_stdin = _make_shell_with_pipes(
        monkeypatch, b"noise\r\n__ADB_TAP_ACK__\r\n"
    )
    shell.tap(540, 1200)
    written = fake_stdin.getvalue().decode()
    assert "input tap 540 1200" in written
    # stdout 应被消费到 ACK 行
    assert shell._process.stdout.readline() == b""  # 已读完


def test_tap_raises_broken_pipe_on_eof(monkeypatch):
    """stdout 提前 EOF（无 ACK）说明 shell 已断，应抛 BrokenPipeError。"""
    shell, _ = _make_shell_with_pipes(monkeypatch, b"")  # 立即 EOF
    with pytest.raises(BrokenPipeError):
        shell.tap(1, 2)


def test_shell_uses_given_serial_without_listing(monkeypatch):
    """传入 serial 时应跳过 list_devices，直接用该 serial 开 shell。"""
    listed = []
    monkeypatch.setattr(device, "list_devices", lambda p: listed.append(p) or ["unused"])
    fake_proc = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO())
    monkeypatch.setattr(device.subprocess, "Popen", lambda *a, **k: fake_proc)
    shell = device.AdbShell("adb", serial="my-serial")
    assert shell.serial == "my-serial"
    assert listed == []  # 未调用 list_devices


# --- 字节流增量切行 ---

def test_line_splitter_yields_complete_lines():
    """应按 \\n 切出完整行，去掉 \\r，保留末尾未完成部分。"""
    sp = device._LineSplitter()
    lines = sp.feed(b"add device 1: /dev/input/event7\r\n  name: x\r\n")
    assert lines == ["add device 1: /dev/input/event7", "  name: x"]


def test_line_splitter_buffers_partial_line():
    """未遇到 \\n 的部分应缓冲，跨多次 feed 拼接成完整行。"""
    sp = device._LineSplitter()
    assert sp.feed(b"/dev/input/event3: EV_ABS       ABS_MT_POSIT") == []
    assert sp.feed(b"ION_X    000002cf\r\n") == [
        "/dev/input/event3: EV_ABS       ABS_MT_POSIT" + "ION_X    000002cf"
    ]


def test_line_splitter_handles_bare_lf_and_crlf():
    """同时兼容 \\n 与 \\r\\n 行结尾。"""
    sp = device._LineSplitter()
    assert sp.feed(b"a\nb\r\nc\n") == ["a", "b", "c"]


def test_line_splitter_flush_returns_remaining():
    """flush 返回缓冲区中未完成的部分（进程结束时）。"""
    sp = device._LineSplitter()
    sp.feed(b"partial-no-newline")
    assert sp.flush() == ["partial-no-newline"]
    assert sp.flush() == []  # 已清空


# --- 流式行读取（关键：read1 返回空 ≠ EOF）---

class _FakeStream:
    """模拟 BufferedReader：read1 按脚本返回数据块，空字节表示'暂时无数据'。"""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read1(self, _n):
        return self._chunks.pop(0) if self._chunks else b""


def test_stream_lines_continues_when_empty_but_alive():
    """read1 返回空字节但进程仍存活时，应继续等待而非停止。"""
    # 脚本：先空（监听等待）→ 再空 → 来一行数据 → 进程随后退出
    stream = _FakeStream([b"", b"", b"line one\nline two\n"])
    alive = iter([True, True, True, False])  # 前三次 alive，第四次 False

    lines = list(device._stream_lines(stream, is_alive=lambda: next(alive, False), max_idle=3))
    assert "line one" in lines
    assert "line two" in lines


def test_stream_lines_stops_on_real_eof():
    """进程已退出且 read1 返回空（真 EOF）时停止。"""
    stream = _FakeStream([b"only line\n"])  # 之后一直返回空
    lines = list(device._stream_lines(stream, is_alive=lambda: False, max_idle=3))
    assert lines == ["only line"]


def test_stream_lines_idle_limit_prevents_infinite_loop():
    """进程一直存活但始终无数据时，靠 max_idle 退出避免测试死循环。"""
    stream = _FakeStream([])  # 永远返回空
    lines = list(device._stream_lines(stream, is_alive=lambda: True, max_idle=5))
    assert lines == []


# --- monitor_touches 端到端（注入真实 getevent 字节流）---

# 取自真机实测数据：一次完整触摸帧 X=0x2e1, Y=0x53c
_REAL_GETEVENT_BYTES = (
    b"add device 5: /dev/input/event3\r\n"
    b'  name:     "synaptics_tcm_touch"\r\n'
    b"/dev/input/event3: EV_ABS       ABS_MT_TRACKING_ID   0000d89c            \r\n"
    b"/dev/input/event3: EV_KEY       BTN_TOUCH            DOWN                \r\n"
    b"/dev/input/event3: EV_ABS       ABS_MT_POSITION_X    000002e1            \r\n"
    b"/dev/input/event3: EV_ABS       ABS_MT_POSITION_Y    0000053c            \r\n"
    b"/dev/input/event3: EV_SYN       SYN_REPORT           00000000            \r\n"
)


class _ByteStream:
    """带 read1 的字节流，读完后 _eof 置位。"""

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)
        self.eof = False

    def read1(self, n: int) -> bytes:
        chunk = self._buf.read1(n)
        if not chunk:
            self.eof = True
        return chunk


def test_monitor_touches_prints_coords(monkeypatch, capsys):
    """注入真实 getevent 字节流，monitor_touches 应打印出解析后的坐标。"""
    stream = _ByteStream(_REAL_GETEVENT_BYTES)
    fake_proc = SimpleNamespace(
        stdout=stream,
        poll=lambda: (0 if stream.eof else None),  # 读完即视为退出
        terminate=lambda: None,
        wait=lambda timeout=None: 0,
        kill=lambda: None,
    )
    monkeypatch.setattr(device.subprocess, "Popen", lambda *a, **k: fake_proc)

    device.monitor_touches("adb", "serial-x")

    out = capsys.readouterr().out
    assert "触摸坐标" in out
    assert "(737, 1340)" in out  # 0x2e1=737, 0x53c=1340
