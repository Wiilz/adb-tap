import pytest

from adb_tap import cli
from adb_tap import presets


def test_resolve_target_uses_preset_name(tmp_path):
    config = tmp_path / "config.json"
    presets.add_preset(config, "buy", 540, 1200)
    x, y = cli.resolve_target(config, ["buy"])
    assert (x, y) == (540, 1200)


def test_resolve_target_uses_explicit_coords(tmp_path):
    config = tmp_path / "config.json"
    x, y = cli.resolve_target(config, ["600", "1300"])
    assert (x, y) == (600, 1300)


def test_resolve_target_missing_preset_lists_available(tmp_path):
    config = tmp_path / "config.json"
    presets.add_preset(config, "buy", 540, 1200)
    with pytest.raises(cli.PresetNotFound, match=r"missing.*buy"):
        cli.resolve_target(config, ["missing"])


def test_resolve_target_rejects_bad_arg_count(tmp_path):
    config = tmp_path / "config.json"
    with pytest.raises(ValueError):
        cli.resolve_target(config, ["100", "200", "300"])


@pytest.mark.parametrize("raw", ["y", "Y", "yes", "  YES  ", "Yes"])
def test_confirm_continue_accepts_variants(monkeypatch, raw):
    monkeypatch.setattr("builtins.input", lambda _: raw)
    assert cli.confirm_continue("继续吗？") is True


def test_confirm_continue_rejects_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert cli.confirm_continue("继续吗？") is False


def test_confirm_continue_defaults_to_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert cli.confirm_continue("继续吗？") is False


def test_cmd_rush_returns_2_on_missing_preset(tmp_path):
    """缺失预设时 cmd_rush 给友好提示并返回 2，不连设备。"""
    from argparse import Namespace

    config = tmp_path / "config.json"
    args = Namespace(
        target=["missing"], at=None, workers=12, duration=None,
        no_ntp=True, ntp_server="ntp.aliyun.com", adb_path=None,
    )
    assert cli.cmd_rush(config, args) == 2


def test_cmd_rush_rejects_zero_workers(tmp_path):
    """--workers < 1 时友好提示并返回 2，不连设备。"""
    from argparse import Namespace

    config = tmp_path / "config.json"
    args = Namespace(
        target=["540", "1200"], at=None, workers=0, duration=None,
        no_ntp=True, ntp_server="ntp.aliyun.com", adb_path=None,
    )
    assert cli.cmd_rush(config, args) == 2


def test_rush_parser_has_workers_no_interval():
    """--workers 默认 12，且 --interval 已移除。"""
    parser = cli.build_parser()
    args = parser.parse_args(["rush", "buy", "--no-ntp"])
    assert args.workers == 12
    assert not hasattr(args, "interval")
