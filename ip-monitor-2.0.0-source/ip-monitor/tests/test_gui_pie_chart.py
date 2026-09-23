"""Regression tests for the pie-chart lifecycle (error.txt: TclError
'invalid command name ... !canvas' from _do_draw_pie_chart)."""

import tkinter as tk

import pytest

from ip_monitor.gui.pie_chart import PieChart, PieChartPanel, chart_size_for
from ip_monitor.models import Target
from ip_monitor.validation import TargetKind
from tests.conftest import ok, pump, timeout

pytestmark = pytest.mark.gui


def _targets(n):
    return [Target(f"10.0.0.{i}", TargetKind.IPV4) for i in range(n)]


def test_update_on_destroyed_chart_is_safe(tk_root):
    t = _targets(1)[0]
    chart = PieChart(tk_root, t, 120, "white")
    assert chart.update(t.stats) is True
    chart.destroy()
    assert chart.exists() is False
    assert chart.update(t.stats) is False  # no TclError
    assert tk_root.callback_errors == []


def test_demoted_target_does_not_keep_stale_canvas(tk_root):
    """The 1.x bug: a target that dropped out of the first four kept a reference to
    its destroyed canvas and every subsequent probe tried to draw on it."""
    panel = PieChartPanel(tk_root)
    panel.show()
    targets = _targets(5)
    panel.sync(targets, 1000)
    assert [c.target_id for c in panel.charts()] == [t.id for t in targets[:4]]
    demoted = targets[0]
    targets.append(targets.pop(0))  # move first target to the end (index 4)
    panel.sync(targets, 1000)
    assert demoted.id not in [c.target_id for c in panel.charts()]
    for _ in range(3):  # probes keep arriving for the demoted target
        demoted.stats.record(ok())
        panel.update_target(demoted)
    pump(tk_root, 0.05)
    assert tk_root.callback_errors == []


def test_removed_target_with_pending_update(tk_root):
    panel = PieChartPanel(tk_root)
    panel.show()
    targets = _targets(3)
    panel.sync(targets, 1000)
    victim = targets.pop(1)
    panel.sync(targets, 1000)  # rebuild without the victim
    victim.stats.record(timeout())
    panel.update_target(victim)  # must be a no-op
    assert len(panel.charts()) == 2
    assert tk_root.callback_errors == []


def test_hide_show_and_resize_rebuild_cleanly(tk_root):
    panel = PieChartPanel(tk_root)
    targets = _targets(2)
    panel.update_target(targets[0])  # hidden: ignored
    panel.show()
    panel.sync(targets, 1000)
    first = panel.charts()
    assert panel.rebuild_count == 1
    panel.sync(targets, 1000)  # nothing changed -> in-place update, no rebuild
    assert panel.rebuild_count == 1 and panel.charts() == first
    panel.sync(targets, 300)  # narrower window -> different size -> rebuild
    assert panel.rebuild_count == 2
    assert all(not c.exists() for c in first)
    panel.hide()
    assert panel.charts() == []
    panel.update_target(targets[0])  # hidden again: still safe
    panel.show()
    panel.sync(targets, 300)
    assert len(panel.charts()) == 2
    assert tk_root.callback_errors == []


def test_percentage_and_colours_track_history(tk_root):
    panel = PieChartPanel(tk_root)
    panel.show()
    t = _targets(1)[0]
    panel.sync([t], 1000)
    chart = panel.charts()[0]
    for _ in range(3):
        t.stats.record(ok())
    t.stats.record(timeout())
    panel.update_target(t)
    assert chart.canvas.itemcget(chart._items["text"], "text") == "75%"
    assert chart.canvas.itemcget(chart._items["arc0"], "fill") != chart.canvas.itemcget(chart._items["arc1"], "fill")


def test_chart_size_bounds():
    assert chart_size_for(50, 4) == chart_size_for(1025, 4)  # unrendered window uses default width
    assert chart_size_for(1025, 0) == 0
    assert chart_size_for(300, 4) == int(104 * 1.3)
    assert chart_size_for(5000, 1) == int(195 * 1.3)
    assert chart_size_for(1025, 1, ui_scale=2.0) == int(195 * 1.3 * 2)


def test_many_syncs_do_not_leak_widgets(tk_root):
    panel = PieChartPanel(tk_root)
    panel.show()
    targets = _targets(4)
    for width in (1000, 500, 1000, 500):
        panel.sync(targets, width)
    assert len(tk_root.winfo_children()) == 4
    panel.clear()
    assert len(tk_root.winfo_children()) == 0
    assert isinstance(tk_root, tk.Tk)
