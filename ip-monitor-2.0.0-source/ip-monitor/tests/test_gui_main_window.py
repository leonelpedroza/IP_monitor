"""Tkinter integration smoke tests for the main window with a fake probe.

Every test asserts that no Tk callback raised - the exact symptom in error.txt."""

import time
import tkinter as tk

import pytest

from ip_monitor.config import Settings
from ip_monitor.csvlog import ProbeCsvLogger
from ip_monitor.gui.main_window import MainWindow
from ip_monitor.monitor import MonitorService
from ip_monitor.notifications import SoundNotifier
from ip_monitor.paths import resolve_paths
from tests.conftest import FakeProbe, ok, pump, timeout

pytestmark = pytest.mark.gui


@pytest.fixture
def window(tk_root, tmp_path):
    paths = resolve_paths(tmp_path / "data")
    probe = FakeProbe([ok(5.0), ok(6.0), timeout(), ok(7.0)])
    csv_logger = ProbeCsvLogger(paths.logs_dir / "log.csv")
    service = MonitorService(probe, csv_logger, interval_s=0.05)
    beeps = []
    notifier = SoundNotifier(up=lambda: beeps.append("up"), down=lambda: beeps.append("down"))
    win = MainWindow(
        tk_root,
        settings=Settings(ping_interval=1),
        paths=paths,
        service=service,
        csv_logger=csv_logger,
        notifier=notifier,
    )
    win.root.report_callback_exception = lambda *a: tk_root.callback_errors.append(a)  # keep collecting
    win.beeps = beeps
    win.probe = probe
    yield win
    if not win.closing:
        win.shutdown()


def test_add_targets_and_receive_updates(window):
    assert window.add_target("10.0.0.1") is not None
    assert window.add_target("example.com") is not None  # resolved by worker, not GUI
    assert window.add_target("10.0.0.1", quiet=True) is None  # duplicate
    assert window.add_target("not a host", quiet=True) is None
    pump(window.root, 0.6)
    assert window.events_processed >= 2
    row = window._rows[window.targets[0].id]
    assert row.status_label.cget("text") in ("OK", "Timeout")
    assert window.root.callback_errors == []


def test_delete_target_while_updates_pending(window):
    t = window.add_target("10.0.0.1")
    window.add_target("10.0.0.2")
    pump(window.root, 0.3)
    window.remove_target(t)
    assert t.id not in window._rows and t not in window.targets
    # events for the deleted target may still be in the queue: they must be ignored
    pump(window.root, 0.4)
    assert len(window.targets) == 1
    assert window.root.callback_errors == []


def test_reorder_with_pie_charts_visible(window):
    """Regression for error.txt: reorder/delete with pie charts shown."""
    targets = [window.add_target(f"10.0.0.{i}") for i in range(1, 7)]
    window.toggle_pie_charts()
    pump(window.root, 0.2)
    assert len(window.pie_panel.charts()) == 4
    window.move_target(targets[0], +1)
    window.move_target(targets[5], -1)
    window.move_target(targets[5], -1)  # now inside the top four, pushes another out
    pump(window.root, 0.4)
    window.remove_target(targets[1])
    pump(window.root, 0.4)
    ids = [c.target_id for c in window.pie_panel.charts()]
    assert ids == [t.id for t in window.targets[:4]]
    assert window.root.callback_errors == []


def test_resize_with_pie_charts_visible(window):
    window.add_target("10.0.0.1")
    window.toggle_pie_charts()
    window.root.deiconify()
    window.root.geometry("500x400")
    pump(window.root, 0.5)
    first = window.pie_panel.charts()[0]
    for _ in range(3):  # a burst of resize events while a chart is visible
        window.root.geometry("1300x700")
        pump(window.root, 0.05)
        window.root.geometry("500x400")
        pump(window.root, 0.05)
    window.root.geometry("1300x700")
    pump(window.root, 0.6)
    assert window.pie_panel.rebuild_count >= 2
    assert not first.exists()  # old chart destroyed and forgotten
    window.targets[0].stats.record(ok())
    window.pie_panel.update_target(window.targets[0])  # draws on the new chart only
    assert window.pie_panel.charts()[0].size != first.size
    assert window.root.callback_errors == []


def test_pie_hide_show_toggle(window):
    window.add_target("10.0.0.1")
    for _ in range(4):
        window.toggle_pie_charts()
        pump(window.root, 0.15)
    assert window.pie_panel.visible is False
    window.toggle_pie_charts()
    pump(window.root, 0.2)
    assert len(window.pie_panel.charts()) == 1
    assert window.root.callback_errors == []


def test_pause_resume_and_all(window):
    t = window.add_target("10.0.0.1")
    window.add_target("10.0.0.2")
    window.toggle_pause(t)
    assert t.paused and window.service.is_paused(t.id)
    assert window._rows[t.id].toggle_button.cget("text") == "Start"
    window.toggle_pause(t)
    assert not t.paused
    window.toggle_all()
    assert window.all_paused and all(x.paused for x in window.targets)
    assert window.toggle_all_button.cget("text") == "Start All"
    window.toggle_all()
    assert not any(x.paused for x in window.targets)
    window.restart_all()
    assert all(x.stats.sent == 0 for x in window.targets)
    assert window.root.callback_errors == []


def test_sound_notifier_only_on_state_change(window):
    t = window.add_target("10.0.0.1")
    window.toggle_sound(t)
    assert t.sound_enabled
    pump(window.root, 0.5)  # ok, ok, timeout, ok, ok ...
    assert window.beeps[:2] == ["down", "up"]
    assert window.root.callback_errors == []


def test_interval_change_reaches_service(window):
    window.interval_var.set(7)
    window._on_interval_changed()
    assert window.service.interval_s == 7 and window.settings.ping_interval == 7
    window.interval_var.set(999)
    window._on_interval_changed()
    assert window.interval_var.get() == 60


def test_logging_toggle(window):
    window.logging_var.set(False)
    window._on_logging_toggled()
    assert not window.csv_logger.enabled
    window.logging_var.set(True)
    window._on_logging_toggled()
    assert window.csv_logger.enabled


def test_save_and_load_targets(window, tmp_path):
    t = window.add_target("10.0.0.1")
    window.add_target("example.org")
    window.toggle_sound(t)
    path = tmp_path / "list.json"
    from ip_monitor import targets_file

    targets_file.save_targets(
        path, [targets_file.SavedTarget(x.address, x.sound_enabled, x.paused) for x in window.targets]
    )
    assert window.load_targets_from(path, replace=True)
    assert [x.address for x in window.targets] == ["10.0.0.1", "example.org"]
    assert window.targets[0].sound_enabled is True and window.has_unsaved_changes is False
    assert window.load_targets_from(path, replace=False)  # add mode: duplicates skipped
    assert len(window.targets) == 2
    assert window.root.callback_errors == []


def test_load_corrupt_targets_file_shows_error_not_crash(window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr("ip_monitor.gui.main_window.messagebox.showerror", lambda *a, **k: shown.append(a))
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert window.load_targets_from(bad) is False and shown


def test_shutdown_stops_workers_and_timers(window):
    for i in range(1, 4):
        window.add_target(f"10.0.0.{i}")
    window.toggle_pie_charts()
    pump(window.root, 0.3)
    t0 = time.monotonic()
    window.shutdown()
    assert time.monotonic() - t0 < 3.0
    assert window.closing and window.sched.closed and window.sched.pending_count() == 0
    assert window.service.live_thread_count() == 0
    assert window.paths.settings_file.exists()
    with pytest.raises(tk.TclError):
        window.root.winfo_exists()  # root destroyed
    assert window.root.callback_errors == []


def test_history_graph_opens_and_closes(window):
    window.add_target("10.0.0.1")
    pump(window.root, 0.3)
    window.show_graph()
    assert window._graph is not None
    pump(window.root, 0.3)
    window._graph.close()
    pump(window.root, 0.1)
    assert window.root.callback_errors == []


def test_tk_callback_exceptions_are_logged_not_fatal(window, monkeypatch, caplog):
    import logging

    monkeypatch.setattr("ip_monitor.gui.main_window.messagebox.showerror", lambda *a, **k: None)
    with caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError("simulated")
        except RuntimeError as exc:
            window._report_callback_exception(type(exc), exc, exc.__traceback__)
    assert "Unhandled exception in Tk callback" in caplog.text


def _fresh_window(tmp_path):
    root = tk.Tk()
    root.withdraw()
    root.callback_errors = []
    root.report_callback_exception = lambda *a: root.callback_errors.append(a)
    paths = resolve_paths(tmp_path / "data")
    csv_logger = ProbeCsvLogger(paths.logs_dir / "log.csv")
    service = MonitorService(FakeProbe([ok(1.0)]), csv_logger, interval_s=0.05)
    return MainWindow(root, settings=Settings(ping_interval=1), paths=paths, service=service, csv_logger=csv_logger)


def test_session_targets_survive_restart(tk_root, tmp_path):
    """The target list is snapshotted at shutdown and restored on the next start."""
    w = _fresh_window(tmp_path)
    assert w.add_target("10.9.9.1") is not None
    assert w.add_target("host-b", sound=True) is not None
    w.toggle_pause(w.targets[1])
    w.shutdown()  # writes last-session.json
    assert w.session_file().is_file()

    w2 = _fresh_window(tmp_path)
    assert w2.restore_session_targets() == 2
    assert [t.address for t in w2.targets] == ["10.9.9.1", "host-b"]
    assert w2.targets[1].sound_enabled is True
    assert w2.targets[1].paused is True
    assert w2.has_unsaved_changes is False
    pump(w2.root, 0.2)
    assert w2.root.callback_errors == []
    w2.shutdown()


def test_restore_session_ignores_missing_or_corrupt_file(tk_root, tmp_path):
    w = _fresh_window(tmp_path)
    assert w.restore_session_targets() == 0
    w.session_file().parent.mkdir(parents=True, exist_ok=True)
    w.session_file().write_text("{not json", encoding="utf-8")
    assert w.restore_session_targets() == 0
    assert w.targets == []
    w.shutdown()
