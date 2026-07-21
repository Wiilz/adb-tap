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
