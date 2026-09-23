"""GUI smoke tests for the after() scheduler - the generic fix for the
destroyed-widget callback class of bug seen in error.txt."""

import tkinter as tk

import pytest

from ip_monitor.gui.scheduler import AfterScheduler
from tests.conftest import pump

pytestmark = pytest.mark.gui


def test_callback_runs_when_widget_alive(tk_root):
    hits = []
    sched = AfterScheduler(tk_root)
    sched.call_later(10, hits.append, "x")
    pump(tk_root, 0.1)
    assert hits == ["x"] and sched.pending_count() == 0


def test_callback_is_dropped_when_owner_destroyed(tk_root):
    """Regression: an after() queued for a widget that is destroyed before the
    callback fires must silently not run - and must not raise TclError."""
    frame = tk.Frame(tk_root)
    canvas = tk.Canvas(frame)
    arc = canvas.create_arc(0, 0, 10, 10, start=0, extent=6)
    sched = AfterScheduler(frame)
    sched.call_later(20, lambda: canvas.itemconfigure(arc, fill="red"))
    frame.destroy()
    pump(tk_root, 0.1)
    assert tk_root.callback_errors == []


def test_close_cancels_everything(tk_root):
    hits = []
    sched = AfterScheduler(tk_root)
    for i in range(5):
        sched.call_later(10, hits.append, i)
    assert sched.pending_count() == 5
    sched.close()
    pump(tk_root, 0.1)
    assert hits == [] and sched.pending_count() == 0
    assert sched.call_later(1, hits.append, 9) is None  # closed scheduler refuses new work


def test_debounce_replaces_pending_call(tk_root):
    hits = []
    sched = AfterScheduler(tk_root)
    for i in range(10):
        sched.call_debounced("resize", 30, hits.append, i)
    pump(tk_root, 0.15)
    assert hits == [9]


def test_cancel_by_key(tk_root):
    hits = []
    sched = AfterScheduler(tk_root)
    sched.call_later(10, hits.append, 1, key="k")
    sched.cancel("k")
    pump(tk_root, 0.05)
    assert hits == [] and sched.pending_count() == 0
