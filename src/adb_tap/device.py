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
