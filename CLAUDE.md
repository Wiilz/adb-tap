# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**adb-tap** - Android 手机极速点击工具。通过 ADB 持久 shell 会话在指定坐标附近持续随机偏移点击（发后确认，频率与真机真实执行一致），支持 NTP 校时定时触发、提前盲打和预设坐标管理。

## Development Environment

- **Python**: 3.12+（`.python-version` 锁定 3.12.12）
- **Package Manager**: `uv`（`uv.lock`）
- **Dependencies**: `ntplib`（NTP 校时）；dev 组 `pytest`
- **Entry Point**: `adb-tap`（注册于 `[project.scripts]`，指向 `adb_tap.cli:main`）

## Commonly Used Commands

```bash
uv sync                                    # 安装依赖
uv run pytest -v                           # 运行测试
uv run adb-tap preset add <名> <x> <y>     # 保存预设
uv run adb-tap rush <预设> --at 12:00:00   # 定时点击
uv run adb-tap rush <预设> --no-ntp        # 立即盲打
```

完整用法见 `README.md`。

## Code Architecture

源码在 `src/adb_tap/`，按单一职责拆分：

- **`cli.py`** - 命令行入口：argparse 子命令（preset/rush）、NTP 校时流程、多 shell 并行点击接线（device_factory）、Windows UTF-8 编码处理
- **`device.py`** - ADB 交互：`resolve_adb_path`（路径解析）、`list_devices`、`AdbShell`（持久 shell + tap/close，tap 发后确认等待回执）、`monitor_touches`（取点，`_parse_touch_line` 解析 getevent）
- **`clicker.py`** - 点击引擎：`run_clicks`（多 shell 并行、随机偏移、共享计数器 + `threading.Event` 停止、worker 内 `BrokenPipe` 重连），`device_factory` 产出 `TapDevice`
- **`scheduler.py`** - 定时：`sync_offset`（NTP 偏移）、`parse_target_time`（HH:MM:SS 解析）、`wait_until`（倒计时）
- **`presets.py`** - 预设坐标：`add/remove/list/get`，读写 `config.json`（原子写入）

测试在 `tests/`（test_presets/test_scheduler/test_device/test_clicker/test_cli）。`device.py` 的设备交互部分无单测，靠 `python -m adb_tap.device` 自检。

### Important Configuration

- **ADB 路径**：优先级 `--adb-path` > 环境变量 `ADB_PATH` > PATH 中的 adb
- **并行路数**：`--workers`（默认 12，实测甜点；未 root 真机约 15 次/秒）
- **随机偏移**：±4 像素（`clicker.run_clicks` 的 offset 参数）
- **NTP 服务器**：`--ntp-server`（默认 ntp.aliyun.com）
- **预设配置**：`config.json`（项目根，被 .gitignore 忽略）

## Git 提交规范

提交信息遵循 Conventional Commits（中文），详见 [`docs/commit-convention.md`](docs/commit-convention.md)。每次提交按此规范编写。
