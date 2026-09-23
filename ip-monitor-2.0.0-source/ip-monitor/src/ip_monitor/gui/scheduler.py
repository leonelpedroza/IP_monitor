"""Safe wrapper around Tk ``after()``.

Root cause of the original destroyed-Canvas exception: ``after()`` callbacks
were queued with closures that captured widgets, and nothing cancelled them
when those widgets were destroyed.  ``AfterScheduler`` fixes that class of
bug once, for the whole application:

* every scheduled id is tracked so it can be cancelled;
* each callback is wrapped in a guard that checks the owning widget still
  exists (``winfo_exists``) and the scheduler has not been closed;
* keyed *debounced* calls replace any pending call with the same key;
* ``close()`` cancels everything - called from the window's shutdown path.
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


class AfterScheduler:
    def __init__(self, widget: tk.Misc) -> None:
        self._widget = widget
        self._pending: dict[str, str] = {}  # after id -> key ("" if un-keyed)
        self._keyed: dict[str, str] = {}  # key -> after id
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def _alive(self) -> bool:
        if self._closed:
            return False
        try:
            return bool(self._widget.winfo_exists())
        except tk.TclError:
            return False

    def call_later(self, delay_ms: int, func: Callable[..., Any], *args: Any, key: str = "") -> str | None:
        """Schedule ``func(*args)``; returns the after id or None if not scheduled."""
        if not self._alive():
            return None
        if key:
            self.cancel(key)
        holder: dict[str, str] = {}

        def _guarded() -> None:
            after_id = holder.get("id", "")
            self._pending.pop(after_id, None)
            if key and self._keyed.get(key) == after_id:
                self._keyed.pop(key, None)
            if not self._alive():
                return
            func(*args)

        try:
            after_id = self._widget.after(delay_ms, _guarded)
        except tk.TclError:
            return None
        holder["id"] = after_id
        self._pending[after_id] = key
        if key:
            self._keyed[key] = after_id
        return after_id

    def call_debounced(self, key: str, delay_ms: int, func: Callable[..., Any], *args: Any) -> None:
        """Replace any pending call with the same ``key``."""
        self.call_later(delay_ms, func, *args, key=key)

    def cancel(self, key: str) -> None:
        after_id = self._keyed.pop(key, None)
        if after_id is not None:
            self._pending.pop(after_id, None)
            self._cancel_id(after_id)

    def cancel_id(self, after_id: str | None) -> None:
        if after_id is None:
            return
        key = self._pending.pop(after_id, None)
        if key:
            self._keyed.pop(key, None)
        self._cancel_id(after_id)

    def _cancel_id(self, after_id: str) -> None:
        with contextlib.suppress(tk.TclError):
            self._widget.after_cancel(after_id)

    def cancel_all(self) -> None:
        for after_id in list(self._pending):
            self._cancel_id(after_id)
        self._pending.clear()
        self._keyed.clear()

    def pending_count(self) -> int:
        return len(self._pending)

    def close(self) -> None:
        self._closed = True
        self.cancel_all()
