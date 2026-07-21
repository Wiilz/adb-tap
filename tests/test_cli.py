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


def test_resolve_target_missing_preset_raises(tmp_path):
    config = tmp_path / "config.json"
    try:
        cli.resolve_target(config, ["missing"])
    except cli.PresetNotFound as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("应抛出 PresetNotFound")


def test_confirm_continue_accepts_yes(capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert cli.confirm_continue("继续吗？") is True


def test_confirm_continue_rejects_no(capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert cli.confirm_continue("继续吗？") is False


def test_confirm_continue_defaults_to_no(capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert cli.confirm_continue("继续吗？") is False
