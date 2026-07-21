import json

from adb_tap import presets


def test_list_empty_when_no_config(tmp_path):
    config = tmp_path / "config.json"
    assert presets.list_presets(config) == {}


def test_add_new_preset(tmp_path):
    config = tmp_path / "config.json"
    presets.add_preset(config, "buy", 540, 1200)
    assert presets.list_presets(config) == {"buy": {"x": 540, "y": 1200}}


def test_add_preset_overwrites_existing(tmp_path):
    config = tmp_path / "config.json"
    presets.add_preset(config, "buy", 540, 1200)
    presets.add_preset(config, "buy", 600, 1300)
    assert presets.list_presets(config) == {"buy": {"x": 600, "y": 1300}}


def test_add_preset_persists_to_file(tmp_path):
    config = tmp_path / "config.json"
    presets.add_preset(config, "buy", 540, 1200)
    raw = json.loads(config.read_text(encoding="utf-8"))
    assert raw == {"buy": {"x": 540, "y": 1200}}


def test_remove_existing_preset(tmp_path):
    config = tmp_path / "config.json"
    presets.add_preset(config, "buy", 540, 1200)
    removed = presets.remove_preset(config, "buy")
    assert removed is True
    assert presets.list_presets(config) == {}


def test_remove_nonexistent_preset(tmp_path):
    config = tmp_path / "config.json"
    removed = presets.remove_preset(config, "missing")
    assert removed is False


def test_remove_does_not_touch_others(tmp_path):
    config = tmp_path / "config.json"
    presets.add_preset(config, "buy", 540, 1200)
    presets.add_preset(config, "sell", 100, 100)
    presets.remove_preset(config, "buy")
    assert presets.list_presets(config) == {"sell": {"x": 100, "y": 100}}


def test_get_existing_preset(tmp_path):
    config = tmp_path / "config.json"
    presets.add_preset(config, "buy", 540, 1200)
    assert presets.get_preset(config, "buy") == (540, 1200)


def test_get_nonexistent_returns_none(tmp_path):
    config = tmp_path / "config.json"
    assert presets.get_preset(config, "missing") is None


def test_corrupted_file_treated_as_empty(tmp_path):
    config = tmp_path / "config.json"
    config.write_text("not json {", encoding="utf-8")
    assert presets.list_presets(config) == {}
    presets.add_preset(config, "buy", 540, 1200)
    assert presets.get_preset(config, "buy") == (540, 1200)


def test_get_preset_invalid_structure_returns_none(tmp_path):
    """手编 config 结构无效时 get_preset 返回 None 而非抛错。"""
    config = tmp_path / "config.json"
    config.write_text(
        '{"bad": {"x": "abc"}, "list": [1, 2], "partial": {"x": 5}}',
        encoding="utf-8",
    )
    assert presets.get_preset(config, "bad") is None      # 坐标非整数
    assert presets.get_preset(config, "list") is None      # 值非 dict
    assert presets.get_preset(config, "partial") is None   # 缺 y
