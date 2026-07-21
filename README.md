# adb-tap

Android 抢票极速点击工具。通过 ADB 持久 shell 会话实现 ~50 次/秒点击，支持 NTP 校时定时触发、提前盲打和预设坐标管理。

## 安装

```bash
uv sync
```

要求：Python 3.12+、已安装 ADB 并连接安卓设备（开启 USB 调试）。

## 使用

### 保存常用按钮坐标

```bash
uv run adb-tap preset add buy 540 1200    # 保存预设
uv run adb-tap preset list                # 查看预设
uv run adb-tap preset remove buy          # 删除预设
uv run adb-tap preset get                 # 取点模式：实时显示手指触摸坐标
```

> 取点提示：`preset get` 解析 `getevent` 的触摸事件。部分设备返回的是输入设备原始坐标（非屏幕像素），如数值与屏幕不符，改用安卓「设置 → 开发者选项 → 指针位置」查看。

### 抢票

```bash
# 定时模式：NTP 校时 + 倒计时，到点自动开点
uv run adb-tap rush buy --at 12:00:00

# 盲打模式：立即开始极速点击
uv run adb-tap rush buy --no-ntp

# 直接给坐标（不用预设）
uv run adb-tap rush 540 1200 --at 12:00:00
```

### 常用选项

| 选项 | 说明 | 默认 |
|------|------|------|
| `--interval <毫秒>` | 点击间隔（下限 10ms） | 20（约 50 次/秒） |
| `--duration <秒>` | 持续时间，到时自动停 | Ctrl+C 手动停 |
| `--no-ntp` | 跳过 NTP 校时，用本地时间 | 关（开启校时） |
| `--ntp-server <地址>` | NTP 服务器 | ntp.aliyun.com |
| `--adb-path <路径>` | adb 可执行文件路径 | 环境变量 ADB_PATH / PATH |

按 `Ctrl+C` 随时停止。

## 原理

用持久 `adb shell` 子进程，通过 stdin 连续发送 `input tap` 命令，避免每次启动新进程的开销，将单次点击从 ~150ms 降到 ~1-2ms。NTP 校时保证定时触发的准确性，点击在基准坐标 ±4 像素内随机偏移。

## 开发

```bash
uv sync                 # 安装依赖
uv run pytest -v        # 运行测试
```

项目结构见 `CLAUDE.md`，提交规范见 [`docs/commit-convention.md`](docs/commit-convention.md)。
