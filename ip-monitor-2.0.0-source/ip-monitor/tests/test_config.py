import json

from ip_monitor.config import DEFAULT_INTERVAL_S, Settings, atomic_write_text, load_settings, save_settings


def test_defaults_round_trip(tmp_path):
    path = tmp_path / "cfg" / "settings.json"
    save_settings(path, Settings())
    assert load_settings(path) == Settings()


def test_values_are_clamped_and_unknown_keys_ignored():
    s = Settings.from_dict({"ping_interval": 999, "probe_timeout": -3, "probe_backend": "bogus", "junk": 1})
    assert s.ping_interval == 60 and s.probe_timeout == 0.2 and s.probe_backend == "auto"
    s = Settings.from_dict({"ping_interval": "abc"})
    assert s.ping_interval == DEFAULT_INTERVAL_S


def test_non_dict_json_gives_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_settings(p) == Settings()


def test_corrupt_file_is_quarantined_and_defaults_used(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_settings(p) == Settings()
    assert not p.exists()
    assert list(tmp_path.glob("settings.json.corrupt-*"))


def test_missing_file_is_fine(tmp_path):
    assert load_settings(tmp_path / "nope.json") == Settings()


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "a.json"
    atomic_write_text(p, "1")
    atomic_write_text(p, "2")
    assert p.read_text(encoding="utf-8") == "2"
    assert [f.name for f in tmp_path.iterdir()] == ["a.json"]


def test_saved_file_is_valid_json(tmp_path):
    p = tmp_path / "s.json"
    save_settings(p, Settings(ping_interval=5, show_pie_charts=True))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["ping_interval"] == 5 and data["show_pie_charts"] is True
