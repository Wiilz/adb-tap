# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**abd-tap** - Android 设备自动化点击工具，通过 ADB 在指定坐标附近持续随机偏移点击。

## Development Environment

- **Python**: 3.13+ (see `.python-version`)
- **Package Manager**: `uv` (uses `uv.lock`)
- **Dependencies**: `abd>=0.0.3`, `adbutils>=2.12.0`

## Commonly Used Commands

```bash
# Install dependencies
uv sync

# Run the main click script
uv run python click_script.py <x> <y>

# Example: Click near (500, 800)
uv run python click_script.py 500 800
```

## Code Architecture

### Key Files

- **`click_script.py`** - 主脚本：通过 subprocess 直接调用 ADB 执行点击操作
  - 在指定坐标 ±4 像素范围内随机偏移点击
  - 点击间隔：0.1 秒
  - 按 `Ctrl+C` 停止
  - **重要**：第 9 行硬编码了 ADB 路径 `ADB_PATH = r"D:\as\jdk\platform-tools\adb.exe"`，使用前需修改

- **`main.py`** - 占位入口文件，当前仅打印 "Hello from abd-tap!"

- **`pyproject.toml`** - 项目配置和依赖定义

### Important Configuration

- **ADB 路径**：`click_script.py:9` - 必须根据实际环境修改
- **最大偏移量**：`click_script.py:12` - `MAX_OFFSET = 4`
- **点击间隔**：`click_script.py:68` - `time.sleep(0.1)`

## Note

虽然 `pyproject.toml` 声明了 `abd` 和 `adbutils` 依赖，但 `click_script.py` 实际使用 `subprocess` 直接调用 ADB，并未使用这些库。

## Git 提交规范

提交信息遵循 Conventional Commits（中文），详见 [`docs/commit-convention.md`](docs/commit-convention.md)。每次提交按此规范编写。
