"""Pie/ring status charts drawn on plain Tk Canvases (no Matplotlib).

Lifecycle design
----------------
* ``PieChart`` owns exactly one Canvas and remembers its item ids.  ``alive``
  becomes False the moment ``destroy()`` is called; every drawing method checks
  both ``alive`` and ``winfo_exists()`` before touching the Canvas.
* ``PieChartPanel.sync(targets)`` decides whether the existing charts can be
  updated in place (same target ids, same size) or must be rebuilt.  Rebuilds
  destroy the old ``PieChart`` objects *and drop every reference to them*, so
  nothing can draw on a dead Canvas later.
* Nothing here schedules ``after()`` callbacks.  Updates are applied
  synchronously by the main-thread poller; a resize is debounced by the main
  window through ``AfterScheduler`` which itself guards against dead widgets.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Sequence

from ip_monitor.gui import theme
from ip_monitor.models import EXTENDED_HISTORY, Target, TargetStats

RING_WIDTH = 10
SLICE_DEGREES = 360 / EXTENDED_HISTORY


def slice_color(state: bool | None) -> str:
    return theme.CIRCLE_OK if state else theme.CIRCLE_FAIL if state is False else theme.CIRCLE_NONE


def chart_size_for(window_width: int, chart_count: int, ui_scale: float = 1.0) -> int:
    """Chart edge length in pixels (kept close to the 1.x heuristic)."""
    if window_width < 100:
        window_width = 1025
    if chart_count <= 0:
        return 0
    size = int(window_width * 0.25 / chart_count) - 20
    size = max(104, min(195, size))
    return int(size * 1.3 * ui_scale)


class PieChart:
    def __init__(self, parent: tk.Misc, target: Target, size: int, background: str) -> None:
        self.target_id = target.id
        self.size = size
        self.alive = True
        self.frame = tk.Frame(parent)
        self.canvas = tk.Canvas(self.frame, width=size, height=size, highlightthickness=0, background=background)
        self.canvas.pack()
        self.label = tk.Label(self.frame, text=target.address)
        self.label.pack()
        self._items: dict[str, int] = {}
        self._draw_initial(target.stats)

    def _draw_initial(self, stats: TargetStats) -> None:
        c = self.canvas
        centre = self.size // 2
        radius = centre - RING_WIDTH
        box = (centre - radius, centre - radius, centre + radius, centre + radius)
        self._items["ring"] = c.create_oval(*box, outline=theme.pie_ring_color(None), width=RING_WIDTH, fill="")
        for i in range(EXTENDED_HISTORY):
            self._items[f"arc{i}"] = c.create_arc(
                *box,
                start=90 - i * SLICE_DEGREES,
                extent=-SLICE_DEGREES,
                fill=theme.CIRCLE_NONE,
                outline="",
                style=tk.PIESLICE,
            )
        self._items["text"] = c.create_text(
            centre,
            centre,
            text="",
            fill=theme.PIE_TEXT,
            font=("TkDefaultFont", max(10, self.size // 5), "bold"),
        )
        self.update(stats)

    def exists(self) -> bool:
        if not self.alive:
            return False
        try:
            return bool(self.canvas.winfo_exists())
        except tk.TclError:
            return False

    def update(self, stats: TargetStats) -> bool:
        """Repaint from the model.  Returns False (and does nothing) if dead."""
        if not self.exists():
            return False
        c = self.canvas
        ext = list(stats.extended)
        for i in range(EXTENDED_HISTORY):
            state = ext[i] if i < len(ext) else None
            c.itemconfigure(self._items[f"arc{i}"], fill=slice_color(state))
        pct = stats.extended_success_pct
        c.itemconfigure(self._items["ring"], outline=theme.pie_ring_color(pct))
        c.itemconfigure(self._items["text"], text="" if pct is None else f"{int(pct)}%")
        return True

    def destroy(self) -> None:
        self.alive = False
        with contextlib.suppress(tk.TclError):
            self.frame.destroy()


class PieChartPanel:
    """Manages up to ``theme.PIE_CHART_MAX`` charts inside ``container``."""

    def __init__(self, container: tk.Misc, ui_scale: float = 1.0) -> None:
        self.container = container
        self._scale = ui_scale
        self._charts: dict[str, PieChart] = {}
        self._order: list[str] = []
        self._size = 0
        self.visible = False
        self.rebuild_count = 0

    def charts(self) -> list[PieChart]:
        return [self._charts[i] for i in self._order]

    def sync(self, targets: Sequence[Target], window_width: int) -> None:
        """Make the panel reflect ``targets`` (first N only).  Cheap when nothing
        structural changed; rebuilds otherwise."""
        if not self.visible:
            return
        shown = list(targets)[: theme.PIE_CHART_MAX]
        ids = [t.id for t in shown]
        size = chart_size_for(window_width, len(shown), self._scale)
        structural_change = (
            ids != self._order or size != self._size or any(not ch.exists() for ch in self._charts.values())
        )
        if structural_change:
            self._rebuild(shown, size)
        else:
            for t in shown:
                self._charts[t.id].update(t.stats)

    def _rebuild(self, shown: Sequence[Target], size: int) -> None:
        self.clear()
        bg = theme.system_background(self.container)
        for t in shown:
            chart = PieChart(self.container, t, size, bg)
            chart.frame.pack(side="left", padx=6)
            self._charts[t.id] = chart
            self._order.append(t.id)
        self._size = size
        self.rebuild_count += 1

    def update_target(self, target: Target) -> None:
        """Called by the poller after each probe.  Safe when the chart is gone."""
        if not self.visible:
            return
        chart = self._charts.get(target.id)
        if chart is not None and not chart.update(target.stats):
            # Canvas vanished underneath us (should not happen) - drop it so the
            # next sync() rebuilds cleanly instead of us retrying a dead widget.
            self._charts.pop(target.id, None)
            if target.id in self._order:
                self._order.remove(target.id)

    def clear(self) -> None:
        for chart in self._charts.values():
            chart.destroy()
        self._charts.clear()
        self._order.clear()
        self._size = 0

    def hide(self) -> None:
        self.visible = False
        self.clear()

    def show(self) -> None:
        self.visible = True
