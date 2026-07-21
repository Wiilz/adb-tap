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
