import sys

from ip_monitor import version
from ip_monitor.app import parse_args
from ip_monitor.gui.main_window import restart_command


def test_version_tuple():
    assert version.version_tuple() == tuple(int(x) for x in version.__version__.split(".")[:3])


def test_parse_args_defaults():
    args = parse_args([])
    assert args.data_dir is None and args.backend is None and args.debug is False


def test_parse_args_backend_choice():
    assert parse_args(["--backend", "ping_exe", "--debug"]).backend == "ping_exe"


def test_restart_command_never_uses_argv0(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["something-else"])
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert restart_command() == [sys.executable, "-m", "ip_monitor"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert restart_command() == [sys.executable]
