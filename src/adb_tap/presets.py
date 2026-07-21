"""预设坐标管理：读写 config.json，格式 {"名称": {"x": int, "y": int}}。"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _read(config_path: Path) -> dict[str, Any]:
    """读取配置文件，不存在或损坏时返回空 dict。"""
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(config_path: Path, data: dict[str, Any]) -> None:
    """写入配置文件（原子替换，避免中断留下损坏文件）。"""
    content = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, config_path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def list_presets(config_path: Path) -> dict[str, dict[str, int]]:
    """列出所有预设。"""
    return _read(config_path)


def add_preset(config_path: Path, name: str, x: int, y: int) -> None:
    """新增或覆盖预设。"""
    data = _read(config_path)
    data[name] = {"x": x, "y": y}
    _write(config_path, data)


def remove_preset(config_path: Path, name: str) -> bool:
    """删除预设，返回是否删除成功（不存在返回 False）。"""
    data = _read(config_path)
    if name not in data:
        return False
    del data[name]
    _write(config_path, data)
    return True


def get_preset(config_path: Path, name: str) -> tuple[int, int] | None:
    """获取预设坐标，不存在返回 None。"""
    data = _read(config_path)
    preset = data.get(name)
    if preset is None:
        return None
    return preset["x"], preset["y"]
