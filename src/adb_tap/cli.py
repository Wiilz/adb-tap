"""命令行入口：解析参数并组装 device / clicker / scheduler / presets。"""

from pathlib import Path

from adb_tap import presets

# 预设坐标默认配置文件路径（项目根目录）
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.json"


class PresetNotFound(Exception):
    """rush 指定的预设名不存在。"""


def resolve_target(config_path: Path, target_args: list[str]) -> tuple[int, int]:
    """将 rush 的目标参数解析为 (x, y)。

    - 1 个参数 → 当作预设名查找（不存在抛 PresetNotFound，消息含可用预设）
    - 2 个参数 → 当作 "x y" 坐标（非整数抛 ValueError，由调用方负责用户化提示）
    - 其它个数 → 抛 ValueError
    """
    if len(target_args) == 1:
        name = target_args[0]
        coords = presets.get_preset(config_path, name)
        if coords is None:
            raise PresetNotFound(
                f"预设 '{name}' 不存在，可用预设："
                f"{list(presets.list_presets(config_path))}"
            )
        return coords
    if len(target_args) != 2:
        raise ValueError(
            f"target 参数个数无效：期望 1（预设名）或 2（x y），实际 {len(target_args)}"
        )
    x = int(target_args[0])
    y = int(target_args[1])
    return x, y


def confirm_continue(prompt: str) -> bool:
    """提示用户确认，默认拒绝（按回车 = 否）。"""
    answer = input(f"{prompt} (y/N) ").strip().lower()
    return answer in ("y", "yes")
