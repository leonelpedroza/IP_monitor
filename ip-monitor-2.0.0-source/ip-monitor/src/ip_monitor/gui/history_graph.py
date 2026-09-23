"""Historical RTT graph (Matplotlib, loaded lazily on first use).

Data comes from the in-memory ``TargetStats.history`` ring buffers, not from
the CSV log, so the graph works whether or not CSV logging is enabled.
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from ip_monitor.gui.scheduler import AfterScheduler
from ip_monitor.models import Target

log = logging.getLogger(__name__)

TIME_RANGES: dict[str, timedelta | None] = {
    "Last 15 minutes": timedelta(minutes=15),
    "Last hour": timedelta(hours=1),
    "Last 6 hours": timedelta(hours=6),
    "All samples": None,
}
ALL_TARGETS = "All targets"
AUTO_REFRESH_MS = 5000


def _load_matplotlib():  # type: ignore[no-untyped-def]
    import matplotlib

    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    return Figure, FigureCanvasTkAgg


def filter_history(
    history: Sequence[tuple[float, float | None]], window: timedelta | None, now: datetime | None = None
) -> list[tuple[datetime, float | None]]:
    """Convert raw samples to datetimes and apply the time window."""
    now = now or datetime.now()
    out: list[tuple[datetime, float | None]] = []
    cutoff = None if window is None else now - window
    for ts, rtt in history:
        dt = datetime.fromtimestamp(ts)
        if cutoff is None or dt >= cutoff:
            out.append((dt, rtt))
    return out


class HistoryGraphWindow:
    def __init__(self, parent: tk.Misc, targets_provider: Callable[[], list[Target]]) -> None:
        try:
            Figure, FigureCanvasTkAgg = _load_matplotlib()
        except Exception as exc:  # ImportError or a broken backend
            log.exception("Matplotlib unavailable")
            messagebox.showerror("Graph unavailable", f"Matplotlib could not be loaded:\n{exc}", parent=parent)
            raise
        self._targets_provider = targets_provider

        self.window = tk.Toplevel(parent)
        self.window.title("Ping History Graph")
        self.window.geometry("860x600")
        self.window.transient(parent)  # type: ignore[call-overload]  # stays above the main window but is NOT modal
        self._sched = AfterScheduler(self.window)

        controls = ttk.Frame(self.window)
        controls.pack(fill="x", padx=8, pady=6)
        ttk.Label(controls, text="Target:").pack(side="left")
        self.target_var = tk.StringVar(value=ALL_TARGETS)
        self.target_box = ttk.Combobox(controls, textvariable=self.target_var, state="readonly", width=34)
        self.target_box.pack(side="left", padx=6)
        ttk.Label(controls, text="Range:").pack(side="left", padx=(12, 0))
        self.range_var = tk.StringVar(value="Last hour")
        ttk.Combobox(controls, textvariable=self.range_var, values=list(TIME_RANGES), state="readonly", width=16).pack(
            side="left", padx=6
        )
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Auto-refresh", variable=self.auto_var).pack(side="left", padx=12)
        ttk.Button(controls, text="Refresh", command=self.refresh).pack(side="right")

        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.window)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.target_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _e: self.close())
        self._refresh_choices()
        self.refresh()
        self._schedule_auto()

    def _refresh_choices(self) -> None:
        names = [ALL_TARGETS] + [t.address for t in self._targets_provider()]
        self.target_box.configure(values=names)
        if self.target_var.get() not in names:
            self.target_var.set(ALL_TARGETS)

    def _schedule_auto(self) -> None:
        self._sched.call_later(AUTO_REFRESH_MS, self._auto_tick, key="auto")

    def _auto_tick(self) -> None:
        if self.auto_var.get():
            self._refresh_choices()
            self.refresh()
        self._schedule_auto()

    def refresh(self) -> None:
        if self._sched.closed:
            return
        ax = self.axes
        ax.clear()
        window = TIME_RANGES.get(self.range_var.get())
        selected = self.target_var.get()
        targets = self._targets_provider()
        if selected != ALL_TARGETS:
            targets = [t for t in targets if t.address == selected]
        plotted = False
        for t in targets:
            samples = filter_history(list(t.stats.history), window)
            if not samples:
                continue
            xs = [dt for dt, _ in samples]
            ys = [rtt if rtt is not None else float("nan") for _, rtt in samples]
            ax.plot(xs, ys, marker="o", markersize=2.5, linewidth=1, label=t.address)
            failures = [dt for dt, rtt in samples if rtt is None]
            if failures:
                ax.scatter(
                    failures,
                    [0] * len(failures),
                    color="red",
                    marker="s",
                    s=18,
                    zorder=5,
                    label=f"{t.address} lost" if selected != ALL_TARGETS else None,
                )
            plotted = True
        if not plotted:
            ax.text(0.5, 0.5, "No samples in the selected range", ha="center", va="center", transform=ax.transAxes)
        else:
            ax.legend(loc="upper left", fontsize=8)
            ax.grid(True, linestyle="--", alpha=0.6)
        ax.set_xlabel("Time")
        ax.set_ylabel("Round-trip time (ms)")
        ax.set_title(f"Ping response times - {selected}")
        self.figure.autofmt_xdate()
        with contextlib.suppress(tk.TclError):
            self.canvas.draw_idle()

    def close(self) -> None:
        self._sched.close()
        with contextlib.suppress(tk.TclError):
            self.canvas.get_tk_widget().destroy()
        self.figure.clear()
        with contextlib.suppress(tk.TclError):
            self.window.destroy()
