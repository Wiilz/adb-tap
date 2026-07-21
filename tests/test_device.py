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
