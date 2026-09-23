"""One row of the target table.  Pure view: it renders a ``Target`` model and
forwards user actions to callbacks.  It stores no monitoring state of its own."""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont

from ip_monitor.gui import theme
from ip_monitor.gui.tooltip import ToolTip
from ip_monitor.models import RECENT_HISTORY, ProbeStatus, RowState, Target


class RowCallbacks:
    """Bundle of actions the row can trigger (all executed on the GUI thread)."""

    def __init__(
        self,
        move_up: Callable[[Target], None],
        move_down: Callable[[Target], None],
        toggle_pause: Callable[[Target], None],
        reset: Callable[[Target], None],
        delete: Callable[[Target], None],
        toggle_sound: Callable[[Target], None],
        select: Callable[[Target], None],
        context_menu: Callable[[tk.Event, Target], None],
    ) -> None:
        self.move_up = move_up
        self.move_down = move_down
        self.toggle_pause = toggle_pause
        self.reset = reset
        self.delete = delete
        self.toggle_sound = toggle_sound
        self.select = select
        self.context_menu = context_menu


class TargetRow:
    def __init__(self, parent: tk.Misc, target: Target, callbacks: RowCallbacks, ui_scale: float) -> None:
        self.target_id = target.id
        self._cb = callbacks
        self._scale = ui_scale
        self._default_bg = theme.system_background(parent)
        self._target = target

        base = tkfont.nametofont("TkDefaultFont")
        self._font = base.copy()
        self._font.configure(size=max(base.cget("size"), 10))
        self._bold = self._font.copy()
        self._bold.configure(weight="bold")

        f = self.frame = tk.Frame(parent)
        for i, col in enumerate(theme.COLUMNS):
            f.grid_columnconfigure(i, minsize=int(col.min_px * ui_scale))
        f.grid_columnconfigure(len(theme.COLUMNS) - 1, weight=1)

        # 0 - reorder arrows
        arrows = tk.Frame(f)
        arrows.grid(row=0, column=0, sticky="w", padx=(2, 0))
        self.up_button = tk.Button(
            arrows, text="\u25b2", width=2, font=("TkDefaultFont", 7), command=lambda: self._cb.move_up(self._target)
        )
        self.up_button.pack()
        self.down_button = tk.Button(
            arrows, text="\u25bc", width=2, font=("TkDefaultFont", 7), command=lambda: self._cb.move_down(self._target)
        )
        self.down_button.pack()

        # 1 - address
        self.address_label = tk.Label(f, text=target.address, anchor="w", font=self._bold)
        self.address_label.grid(row=0, column=1, sticky="we", padx=4)
        self.address_tip = ToolTip(self.address_label, target.address)
        self.address_label.bind("<Button-1>", lambda _e: self._cb.select(self._target))

        # 2 - recent history circles
        self.circle_frame = tk.Frame(f)
        self.circle_frame.grid(row=0, column=2, padx=4)
        self.circles: list[tk.Canvas] = []
        self.circle_tips: list[ToolTip] = []
        d = int(16 * ui_scale)
        for i in range(RECENT_HISTORY):
            c = tk.Canvas(self.circle_frame, width=d, height=d, highlightthickness=0)
            c.create_oval(2, 2, d - 2, d - 2, fill=theme.CIRCLE_NONE, outline="", tags="dot")
            c.pack(side="left", padx=int(2 * ui_scale))
            self.circles.append(c)
            self.circle_tips.append(ToolTip(c, f"Probe {i + 1}: no data"))

        # 3..8 - text statistics
        self.status_label = tk.Label(f, text="-", anchor="center", font=self._font)
        self.status_label.grid(row=0, column=3, sticky="we")
        self.current_label = tk.Label(f, text="-", font=self._font)
        self.current_label.grid(row=0, column=4, sticky="we")
        self.min_label = tk.Label(f, text="-", font=self._font)
        self.min_label.grid(row=0, column=5, sticky="we")
        self.max_label = tk.Label(f, text="-", font=self._font)
        self.max_label.grid(row=0, column=6, sticky="we")
        self.avg_label = tk.Label(f, text="-", font=self._font)
        self.avg_label.grid(row=0, column=7, sticky="we")
        self.loss_label = tk.Label(f, text="-", font=self._font)
        self.loss_label.grid(row=0, column=8, sticky="we")

        # 9 - controls
        controls = tk.Frame(f)
        controls.grid(row=0, column=9, sticky="w", padx=4)
        self.toggle_button = tk.Button(
            controls, text="Stop", width=6, command=lambda: self._cb.toggle_pause(self._target)
        )
        self.toggle_button.pack(side="left", padx=2)
        tk.Button(controls, text="Reset", width=6, command=lambda: self._cb.reset(self._target)).pack(
            side="left", padx=2
        )
        tk.Button(controls, text="Delete", width=6, command=lambda: self._cb.delete(self._target)).pack(
            side="left", padx=2
        )
        self.bell_button = tk.Label(controls, text="\U0001f515", font=("TkDefaultFont", 12), cursor="hand2")
        self.bell_button.pack(side="left", padx=6)
        self.bell_button.bind("<Button-1>", lambda _e: self._cb.toggle_sound(self._target))
        self.bell_tip = ToolTip(self.bell_button, "Sound notifications disabled")

        # right-click anywhere on the row
        for w in (
            f,
            self.address_label,
            self.circle_frame,
            self.status_label,
            self.current_label,
            self.min_label,
            self.max_label,
            self.avg_label,
            self.loss_label,
            controls,
        ):
            w.bind("<Button-3>", lambda e: self._cb.context_menu(e, self._target))

        self._bg_widgets: list[tk.Widget] = [
            f,
            arrows,
            self.address_label,
            self.circle_frame,
            self.status_label,
            self.current_label,
            self.min_label,
            self.max_label,
            self.avg_label,
            self.loss_label,
            controls,
            self.bell_button,
            *self.circles,
        ]
        self.refresh(target)

    # ------------------------------------------------------------------
    def exists(self) -> bool:
        try:
            return bool(self.frame.winfo_exists())
        except tk.TclError:
            return False

    def destroy(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.frame.destroy()

    def set_position(self, index: int, count: int) -> None:
        self.up_button.configure(state="normal" if index > 0 else "disabled")
        self.down_button.configure(state="normal" if index < count - 1 else "disabled")

    def refresh(self, target: Target) -> None:
        """Re-render every dynamic element from the model (in place, no widget churn)."""
        if not self.exists():
            return
        self._target = target
        s = target.stats

        for i, c in enumerate(self.circles):
            state = s.recent[i] if i < len(s.recent) else None
            colour = theme.CIRCLE_OK if state else theme.CIRCLE_FAIL if state is False else theme.CIRCLE_NONE
            c.itemconfigure("dot", fill=colour)
        # tooltip for the most recent probe only (others are just positional)
        if s.recent and s.recent[0] is not None:
            if s.recent[0]:
                self.circle_tips[0].set_text(f"Latest: {theme.format_rtt(s.current_rtt_ms)}")
            else:
                label = s.last_status.label if s.last_status else "Failed"
                self.circle_tips[0].set_text(f"Latest: {label}")

        status = s.last_status
        if target.paused:
            status_text = "Paused"
        elif status is None:
            status_text = "Waiting"
        else:
            status_text = status.label
        self.status_label.configure(text=status_text)
        tip = target.address
        if s.resolved_ip and s.resolved_ip != target.address:
            tip += f"\nResolved: {s.resolved_ip}"
        if s.last_message and status is not None and status is not ProbeStatus.SUCCESS:
            tip += f"\n{s.last_message}"
        self.address_tip.set_text(tip)

        self.current_label.configure(text=theme.format_rtt(s.current_rtt_ms))
        self.min_label.configure(text=theme.format_rtt(s.min_rtt_ms))
        self.max_label.configure(text=theme.format_rtt(s.max_rtt_ms))
        self.avg_label.configure(text=theme.format_rtt(s.avg_rtt_ms))
        self.loss_label.configure(text=theme.format_pct(s.packet_loss_pct))

        self.toggle_button.configure(text="Start" if target.paused else "Stop")
        if target.sound_enabled:
            self.bell_button.configure(text="\U0001f514", fg="#00aa00")
            self.bell_tip.set_text("Sound notifications enabled")
        else:
            self.bell_button.configure(text="\U0001f515", fg="gray")
            self.bell_tip.set_text("Sound notifications disabled")

        self._apply_state(target.row_state())

    def _apply_state(self, state: RowState) -> None:
        bg, fg = theme.ROW_COLORS[state]
        bg = bg or self._default_bg
        self.address_label.configure(fg=fg)
        for w in self._bg_widgets:
            with contextlib.suppress(tk.TclError):
                w.configure(background=bg)  # type: ignore[call-arg]
