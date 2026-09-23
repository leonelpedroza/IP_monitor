"""About dialog."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from ip_monitor.paths import AppPaths
from ip_monitor.version import APP_AUTHOR, APP_DESCRIPTION, APP_NAME, __version__


def show_about(parent: tk.Misc, paths: AppPaths, backend_name: str) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title(f"About {APP_NAME}")
    win.resizable(False, False)
    win.transient(parent)  # type: ignore[call-overload]
    frame = ttk.Frame(win, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=APP_NAME, font=("TkDefaultFont", 16, "bold")).pack()
    ttk.Label(frame, text=f"Version {__version__}").pack(pady=(2, 8))
    ttk.Label(frame, text=APP_DESCRIPTION, wraplength=380, justify="center").pack()
    ttk.Label(frame, text=f"\u00a9 {APP_AUTHOR}").pack(pady=(8, 2))
    info = (
        f"Python {sys.version.split()[0]}  |  Tk {tk.TkVersion}\n"
        f"Probe backend: {backend_name}\n"
        f"Data folder{' (portable)' if paths.portable else ''}:\n{paths.root}"
    )
    ttk.Label(frame, text=info, justify="center").pack(pady=(8, 12))
    ttk.Button(frame, text="Close", command=win.destroy).pack()
    win.bind("<Escape>", lambda _e: win.destroy())
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_height()) // 2
    win.geometry(f"+{max(0, x)}+{max(0, y)}")
    return win
