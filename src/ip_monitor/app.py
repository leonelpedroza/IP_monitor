"""Application entry point and composition root.

Order of operations:
1. parse command line, resolve data folders, configure logging
2. make the process DPI-aware (Windows) *before* Tk is created
3. load settings, select a probe backend, create the monitoring service
4. build the Tk window and run the main loop
5. on exit, workers are stopped by ``MainWindow.shutdown``
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from ip_monitor.config import load_settings
from ip_monitor.csvlog import ProbeCsvLogger
from ip_monitor.logging_setup import configure_logging
from ip_monitor.monitor import MonitorService
from ip_monitor.paths import resolve_paths
from ip_monitor.probes import ProbeUnavailableError, select_probe
from ip_monitor.version import APP_NAME, __version__

log = logging.getLogger(__name__)


def enable_dpi_awareness() -> None:
    """Opt in to per-monitor DPI awareness on Windows (no-op elsewhere)."""
    if sys.platform != "win32":  # pragma: no cover
        return
    try:  # pragma: no cover - Windows only
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:  # pragma: no cover
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    with contextlib.suppress(AttributeError, OSError):  # pragma: no cover
        ctypes.windll.user32.SetProcessDPIAware()


def compute_ui_scale(root: tk.Tk) -> float:
    """Return the DPI scale factor (1.0 at 96 DPI) and align Tk's point scaling."""
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        return 1.0
    if dpi <= 0:
        return 1.0
    with contextlib.suppress(tk.TclError):
        root.tk.call("tk", "scaling", dpi / 72.0)
    return max(1.0, round(dpi / 96.0, 2))


def load_icon(root: tk.Tk) -> tk.PhotoImage | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2] / "assets"))
    for candidate in (base / "icon.png", base / "assets" / "icon.png"):
        if candidate.exists():
            try:
                return tk.PhotoImage(master=root, file=str(candidate))
            except tk.TclError:
                continue
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ip_monitor", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--data-dir", help="override the user-data folder")
    parser.add_argument("--targets", help="load this target list file at startup")
    parser.add_argument("--backend", choices=["auto", "icmp_api", "ping3", "ping_exe"], help="probe backend")
    parser.add_argument("--debug", action="store_true", help="verbose application log")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = resolve_paths(args.data_dir)
    configure_logging(paths.app_log_file, logging.DEBUG if args.debug else logging.INFO)
    log.info("%s %s starting; data folder %s (portable=%s)", APP_NAME, __version__, paths.root, paths.portable)

    settings = load_settings(paths.settings_file)
    if args.backend:
        settings.probe_backend = args.backend

    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()

    try:
        probe = select_probe(settings.probe_backend)
    except ProbeUnavailableError as exc:
        log.critical("%s", exc)
        messagebox.showerror(APP_NAME, f"No ICMP probe mechanism is available on this computer.\n\n{exc}")
        root.destroy()
        return 2

    csv_logger = ProbeCsvLogger(ProbeCsvLogger.session_path(paths.logs_dir), enabled=settings.logging_enabled)
    service = MonitorService(probe, csv_logger, interval_s=settings.ping_interval, timeout_s=settings.probe_timeout)

    from ip_monitor.gui.main_window import MainWindow  # imported late: Tk must exist first

    ui_scale = compute_ui_scale(root)
    window = MainWindow(
        root,
        settings=settings,
        paths=paths,
        service=service,
        csv_logger=csv_logger,
        ui_scale=ui_scale,
        icon=load_icon(root),
    )
    if args.targets:
        window.load_targets_from(Path(args.targets), replace=True)
    else:
        window.restore_session_targets()
    root.deiconify()
    try:
        root.mainloop()
    finally:
        if not window.closing:  # e.g. KeyboardInterrupt from a console
            window.shutdown()
    log.info("%s exited", APP_NAME)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
