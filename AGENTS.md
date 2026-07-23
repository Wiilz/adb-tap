# AGENTS.md

Android 抢票极速点击工具。通过 ADB 持久 shell 会话持续点击（发后确认，频率与真机真实执行一致），支持 NTP 校时定时触发、提前盲打和预设坐标管理。

## 开发环境

- Python 3.12+（`.python-version` 锁定 3.12.12）
- 包管理：`uv`（`uv.lock`）
- 依赖：`ntplib`（NTP 校时）；dev 组 `pytest`
- 入口：`adb-tap`（`[project.scripts]` → `adb_tap.cli:main`）

## 常用命令

```bash
uv sync                                    # 安装依赖
uv run pytest -v                           # 运行测试
uv run adb-tap preset add <名> <x> <y>     # 保存预设
uv run adb-tap rush <预设> --at 12:00:00   # 定时抢票
uv run adb-tap rush <预设> --no-ntp        # 立即盲打
```

完整用法见 `README.md`。

## 项目结构

源码在 `src/adb_tap/`，按单一职责拆分：

- `cli.py` - 命令行入口：argparse 子命令（preset/rush）、NTP 校时、shell 断开重连、Windows UTF-8
- `device.py` - ADB 交互：`resolve_adb_path`、`list_devices`、`AdbShell`（持久 shell，tap 发后确认等待回执）、`monitor_touches`（取点，`_parse_touch_line` 解析 getevent）
- `clicker.py` - 点击引擎：`run_clicks`（随机偏移、间隔下限 10ms、max_clicks/duration 停止）
- `scheduler.py` - 定时：`sync_offset`（NTP）、`parse_target_time`、`wait_until`（倒计时）
- `presets.py` - 预设坐标：`add/remove/list/get`，读写 `config.json`（原子写入）

测试在 `tests/`。`device.py` 设备交互部分无单测，靠 `python -m adb_tap.device` 自检。

## 关键配置

- ADB 路径优先级：`--adb-path` > 环境变量 `ADB_PATH` > PATH
- 点击间隔：`--interval`（默认 20ms，下限 10ms）
- 随机偏移：±4 像素
- NTP 服务器：`--ntp-server`（默认 ntp.aliyun.com）
- 预设配置：`config.json`（被 .gitignore 忽略）

## 提交规范

提交信息遵循 Conventional Commits（中文），见 [`docs/commit-convention.md`](docs/commit-convention.md)。
