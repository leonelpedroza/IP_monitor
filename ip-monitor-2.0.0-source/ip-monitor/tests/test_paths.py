from ip_monitor import paths as p


def test_override_creates_layout(tmp_path):
    ap = p.resolve_paths(tmp_path / "data")
    assert ap.config_dir.is_dir() and ap.logs_dir.is_dir() and ap.targets_dir.is_dir() and ap.exports_dir.is_dir()
    assert ap.settings_file.parent == ap.config_dir
    assert not ap.portable


def test_portable_mode_uses_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "application_dir", lambda: tmp_path)
    (tmp_path / p.PORTABLE_MARKER).write_text("", encoding="utf-8")
    ap = p.resolve_paths()
    assert ap.portable and ap.root == tmp_path / "data"


def test_non_portable_uses_user_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "application_dir", lambda: tmp_path)
    monkeypatch.setattr(p, "default_data_root", lambda: tmp_path / "userdata")
    ap = p.resolve_paths()
    assert not ap.portable and ap.root == tmp_path / "userdata"


def test_unwritable_portable_dir_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "application_dir", lambda: tmp_path)
    (tmp_path / p.PORTABLE_MARKER).write_text("", encoding="utf-8")
    monkeypatch.setattr(p, "_is_writable_dir", lambda _path: False)
    monkeypatch.setattr(p, "default_data_root", lambda: tmp_path / "userdata")
    ap = p.resolve_paths()
    assert not ap.portable and ap.root == tmp_path / "userdata"
