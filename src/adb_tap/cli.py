"""命令行入口：解析参数并组装 device / clicker / scheduler / presets。"""

import argparse
import sys
import time
from pathlib import Path

from adb_tap import clicker, device, presets, scheduler

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


def cmd_preset_add(config_path: Path, args) -> int:
    presets.add_preset(config_path, args.name, args.x, args.y)
    print(f"已保存预设 '{args.name}' → ({args.x}, {args.y})")
    return 0


def cmd_preset_list(config_path: Path, args) -> int:
    data = presets.list_presets(config_path)
    if not data:
        print("（暂无预设，用 'adb-tap preset add <名称> <x> <y>' 添加）")
        return 0
    for name, coord in data.items():
        print(f"  {name}\t({coord['x']}, {coord['y']})")
    return 0


def cmd_preset_remove(config_path: Path, args) -> int:
    if presets.remove_preset(config_path, args.name):
        print(f"已删除预设 '{args.name}'")
        return 0
    print(f"预设 '{args.name}' 不存在")
    return 1


def cmd_preset_get(config_path: Path, args) -> int:
    """取点模式：实时打印手指触摸坐标。"""
    adb_path = device.resolve_adb_path(None)
    serials = device.list_devices(adb_path)
    if not serials:
        print("没有已连接的设备")
        return 1
    print("手指触摸屏幕将显示坐标，按 Ctrl+C 退出：")
    device.monitor_touches(adb_path, serials[0])
    return 0


def _sync_time(args) -> float:
    """执行 NTP 校时，返回偏移量；失败时询问是否继续，返回 0 或退出。"""
    if args.no_ntp:
        print("已跳过 NTP 校时，使用本地时间")
        return 0.0
    try:
        offset = scheduler.sync_offset(args.ntp_server, timeout=3.0)
    except Exception as exc:  # 网络异常、超时等
        print(f"⚠️ NTP 校时失败：{exc}")
        try:
            if not confirm_continue("是否用本地时间继续？"):
                raise SystemExit("已取消")
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("已取消")
        return 0.0
    print(f"✅ 时间已校准（本地偏差 {offset:+.3f}s）")
    return offset


def cmd_rush(config_path: Path, args) -> int:
    # 1. 解析目标坐标
    try:
        x, y = resolve_target(config_path, args.target)
    except PresetNotFound as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if args.workers < 1:
        print(f"错误：--workers 必须 ≥ 1（当前 {args.workers}）", file=sys.stderr)
        return 2

    # 2. 解析 ADB 路径并确认设备
    try:
        adb_path = device.resolve_adb_path(args.adb_path)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(f"🔌 连接设备（ADB: {adb_path}）...")
    serials = device.list_devices(adb_path)
    if not serials:
        print("错误：没有已连接的设备，请用 adb devices 检查连接", file=sys.stderr)
        return 2
    serial = serials[0]
    print(f"✅ 设备就绪：{serial}")
    # 工厂：每次创建一个绑定该 serial 的持久 shell（跳过重复 list_devices）
    factory = lambda: device.AdbShell(adb_path, serial)

    start = time.monotonic()
    last_seen = 0
    interrupted = False

    def _do_clicks() -> int:
        last_print = 0.0

        def on_progress(c: int) -> None:
            nonlocal last_seen, last_print
            last_seen = c
            now = time.monotonic()
            # 节流：首次或距上次打印≥0.1s 才刷新，避免高频点击被 I/O 拖慢
            if c == 1 or now - last_print >= 0.1:
                last_print = now
                print(f"\r✅ 已点击 {c} 次 | {now - start:.1f}s", end="", flush=True)

        return clicker.run_clicks(
            factory, base_x=x, base_y=y,
            workers=args.workers, duration=args.duration,
            on_progress=on_progress,
        )

    try:
        # 3. NTP 校时
        offset = _sync_time(args)

        # 4. 定时等待
        if args.at:
            try:
                target = scheduler.parse_target_time(args.at)
            except (ValueError, IndexError) as exc:
                print(f"错误：--at 时间格式无效（{exc}）", file=sys.stderr)
                return 2
            print(f"⏰ 目标时间 {args.at}，开始倒计时...")

            def _tick(r: str, clear: bool = False) -> None:
                # 串变短时（跨小时边界）用空格清掉行内残留再重写
                print(f"\r距开票还有 {r}{' ' * 5 if clear else ''}", end="", flush=True)

            scheduler.wait_until(target, offset, on_tick=_tick)
            print()  # 倒计时换行

        # 5. 极速点击（多 shell 并行；设备由 run_clicks 内部创建与关闭）
        print(
            f"🚀 开始在 ({x}, {y}) 附近极速点击（{args.workers} 路并行，Ctrl+C 停止）..."
        )
        total_clicks = _do_clicks()
    except KeyboardInterrupt:
        interrupted = True
        total_clicks = last_seen

    elapsed = time.monotonic() - start
    suffix = "（已中断）" if interrupted else ""
    print(f"\n🔚 停止{suffix}。共点击 {total_clicks} 次，耗时 {elapsed:.1f}s")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adb-tap", description="Android 手机极速点击工具")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="预设坐标配置文件路径")

    sub = parser.add_subparsers(dest="command", required=True)

    # preset 子命令组
    preset = sub.add_parser("preset", help="预设坐标管理")
    preset_sub = preset.add_subparsers(dest="preset_command", required=True)

    p_add = preset_sub.add_parser("add", help="保存预设")
    p_add.add_argument("name", help="预设名")
    p_add.add_argument("x", type=int, help="x 坐标")
    p_add.add_argument("y", type=int, help="y 坐标")

    preset_sub.add_parser("list", help="列出所有预设")

    p_rm = preset_sub.add_parser("remove", help="删除预设")
    p_rm.add_argument("name", help="预设名")

    preset_sub.add_parser("get", help="取点模式：实时显示手指触摸坐标")

    # rush 子命令
    rush = sub.add_parser("rush", help="极速点击")
    rush.add_argument("target", nargs="+", help="预设名 或 'x y' 坐标")
    rush.add_argument("--at", help="定时触发（HH:MM:SS），不指定则立即盲打")
    rush.add_argument("--workers", type=int, default=12, help="并行 shell 数（默认 12，实测甜点；想压榨可调高）")
    rush.add_argument("--duration", type=float, default=None, help="持续秒数，不指定则 Ctrl+C 停止")
    rush.add_argument("--no-ntp", action="store_true", help="跳过 NTP 校时")
    rush.add_argument("--ntp-server", default="ntp.aliyun.com", help="NTP 服务器")
    rush.add_argument("--adb-path", default=None, help="adb 可执行文件路径")

    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 默认 cp936 会导致中文/emoji 乱码，强制 stdout/stderr 用 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = Path(args.config)

    if args.command == "preset":
        handlers = {
            "add": cmd_preset_add,
            "list": cmd_preset_list,
            "remove": cmd_preset_remove,
            "get": cmd_preset_get,
        }
        return handlers[args.preset_command](config_path, args)
    if args.command == "rush":
        return cmd_rush(config_path, args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
