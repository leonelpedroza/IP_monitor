"""Lightweight tooltip that can be updated in place (no event re-binding)."""

from __future__ import annotations

import contextlib
import tkinter as tk


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str = "", delay_ms: int = 400) -> None:
        self.widget = widget
        self.text = text
        self._delay = delay_ms
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_leave, add="+")

    def set_text(self, text: str) -> None:
        self.text = text
        if self._tip is not None:
            for child in self._tip.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(text=text)

    def _on_enter(self, _event: object = None) -> None:
        self._cancel()
        try:
            self._after_id = self.widget.after(self._delay, self._show)
        except tk.TclError:
            self._after_id = None

    def _on_leave(self, _event: object = None) -> None:
        self._cancel()
        self._hide()

    def _cancel(self) -> None:
        if self._after_id is not None:
            with contextlib.suppress(tk.TclError):
                self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._tip is not None or not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tip,
                text=self.text,
                justify="left",
                background="#ffffe0",
                relief="solid",
                borderwidth=1,
                padx=4,
                pady=2,
            ).pack()
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def _hide(self) -> None:
        if self._tip is not None:
            with contextlib.suppress(tk.TclError):
                self._tip.destroy()
            self._tip = None
