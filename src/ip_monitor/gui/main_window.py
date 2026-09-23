"""Main application window.

Responsibilities: build the widgets, own the ordered list of ``Target`` models,
drain the monitoring event queue on the Tk main thread, and translate user
actions into ``MonitorService`` calls.  All Tkinter access happens here or in
the sibling view modules, always on the main thread.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from ip_monitor import export, targets_file
from ip_monitor.config import MAX_INTERVAL_S, MIN_INTERVAL_S, Settings, save_settings
from ip_monitor.csvlog import ProbeCsvLogger
from ip_monitor.gui import theme
from ip_monitor.gui.about import show_about
from ip_monitor.gui.history_graph import HistoryGraphWindow
from ip_monitor.gui.pie_chart import PieChartPanel
from ip_monitor.gui.scheduler import AfterScheduler
from ip_monitor.gui.target_row import RowCallbacks, TargetRow
from ip_monitor.models import Target
from ip_monitor.monitor import MonitorService, ProbeEvent
from ip_monitor.notifications import SoundNotifier
from ip_monitor.paths import AppPaths
from ip_monitor.validation import InvalidTargetError, parse_target
from ip_monitor.version import APP_NAME, __version__

log = logging.getLogger(__name__)

POLL_MS = 100
RESIZE_DEBOUNCE_MS = 300
SETTINGS_DEBOUNCE_MS = 800
ERROR_DIALOG_MIN_GAP_S = 30.0
SESSION_FILE_NAME = "last-session.json"  # auto-written at exit, restored at start


class MainWindow:
    def __init__(
        self,
        root: tk.Tk,
        *,
        settings: Settings,
        paths: AppPaths,
        service: MonitorService,
        csv_logger: ProbeCsvLogger,
        notifier: SoundNotifier | None = None,
        ui_scale: float = 1.0,
        icon: tk.PhotoImage | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.paths = paths
        self.service = service
        self.csv_logger = csv_logger
        self.notifier = notifier or SoundNotifier()
        self.ui_scale = ui_scale

        self.targets: list[Target] = []
        self._by_id: dict[str, Target] = {}
        self._rows: dict[str, TargetRow] = {}
        self.has_unsaved_changes = False
        self.all_paused = False
        self.closing = False
        self.events_processed = 0
        self._last_error_dialog = 0.0
        self._graph: HistoryGraphWindow | None = None
        self._icon = icon

        root.title(f"{APP_NAME} {__version__}")
        root.minsize(int(760 * ui_scale), int(400 * ui_scale))
        if settings.window_geometry:
            try:
                root.geometry(settings.window_geometry)
            except tk.TclError:
                root.geometry("1240x640")
        else:
            root.geometry(f"{int(1240 * ui_scale)}x{int(640 * ui_scale)}")
        if icon is not None:
            with contextlib.suppress(tk.TclError):
                root.iconphoto(True, icon)

        self.sched = AfterScheduler(root)
        self._build_menu()
        self._build_widgets()

        root.protocol("WM_DELETE_WINDOW", self.on_closing)
        root.bind("<Configure>", self._on_configure)
        root.report_callback_exception = self._report_callback_exception  # type: ignore[assignment]

        if settings.show_pie_charts:
            self._show_pie_charts()
        self.sched.call_later(POLL_MS, self._poll, key="poll")

    # ------------------------------------------------------------------ build
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Target List...", command=self.save_targets_as, accelerator="Ctrl+S")
        file_menu.add_command(label="Load Target List...", command=self.load_targets, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Export Statistics...", command=self.export_statistics)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)

        tools = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools)
        tools.add_command(label="Reset All Statistics", command=self.reset_all_stats)
        tools.add_command(label="Stop All / Start All", command=self.toggle_all)
        tools.add_command(label="Restart All (reset + resume)", command=self.restart_all)
        tools.add_separator()
        tools.add_command(label="Clear All Targets...", command=self.clear_all_targets)
        tools.add_command(label="View History Graph", command=self.show_graph)
        tools.add_separator()
        tools.add_command(label="Open Data Folder", command=self._open_data_folder)
        tools.add_command(label="Restart Program", command=self.restart_program)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=lambda: show_about(self.root, self.paths, self.service.probe.name))

        self.root.bind("<Control-s>", lambda _e: self.save_targets_as())
        self.root.bind("<Control-o>", lambda _e: self.load_targets())

    def _build_widgets(self) -> None:
        s = self.ui_scale
        entry_font = tkfont.nametofont("TkDefaultFont").copy()
        entry_font.configure(size=max(entry_font.cget("size"), 11))

        top = ttk.Frame(self.root)
        top.pack(side="top", fill="x", padx=10, pady=(8, 4))
        ttk.Label(top, text="IP address / hostname:").pack(side="left", padx=(0, 6))
        self.entry = ttk.Entry(top, width=34, font=entry_font)
        self.entry.pack(side="left")
        self.entry.bind("<Return>", lambda _e: self.add_target_from_entry())
        ttk.Button(top, text="Add", command=self.add_target_from_entry).pack(side="left", padx=(8, 0))
        ttk.Label(top, text="Interval (s):").pack(side="left", padx=(20, 4))
        self.interval_var = tk.IntVar(value=self.settings.ping_interval)
        spin = ttk.Spinbox(
            top,
            from_=MIN_INTERVAL_S,
            to=MAX_INTERVAL_S,
            width=4,
            textvariable=self.interval_var,
            command=self._on_interval_changed,
        )
        spin.pack(side="left")
        spin.bind("<FocusOut>", lambda _e: self._on_interval_changed())
        spin.bind("<Return>", lambda _e: self._on_interval_changed())
        ttk.Label(top, text=f"backend: {self.service.probe.name}").pack(side="right")

        buttons = ttk.Frame(self.root)
        buttons.pack(side="top", fill="x", padx=10, pady=4)
        self.logging_var = tk.BooleanVar(value=self.settings.logging_enabled)
        ttk.Checkbutton(
            buttons, text="Enable CSV logging", variable=self.logging_var, command=self._on_logging_toggled
        ).pack(side="left", padx=(0, 8))
        self.csv_logger.enabled = self.settings.logging_enabled
        bw = 16
        ttk.Button(buttons, text="Reset All Stats", width=bw, command=self.reset_all_stats).pack(side="left", padx=3)
        self.toggle_all_button = ttk.Button(buttons, text="Stop All", width=bw, command=self.toggle_all)
        self.toggle_all_button.pack(side="left", padx=3)
        ttk.Button(buttons, text="Restart All", width=bw, command=self.restart_all).pack(side="left", padx=3)
        ttk.Button(buttons, text="View Graph", width=bw, command=self.show_graph).pack(side="left", padx=3)
        ttk.Button(buttons, text="Export Stats...", width=bw, command=self.export_statistics).pack(side="left", padx=3)
        self.pie_button = ttk.Button(buttons, text="Show Pie Charts", width=bw, command=self.toggle_pie_charts)
        self.pie_button.pack(side="left", padx=3)

        # header
        header = tk.Frame(self.root)
        header.pack(fill="x", padx=10, pady=(6, 0))
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold", size=max(bold.cget("size"), 10))
        for i, col in enumerate(theme.COLUMNS):
            header.grid_columnconfigure(i, minsize=int(col.min_px * s))
            tk.Label(header, text=col.title, anchor=col.anchor, font=bold).grid(row=0, column=i, sticky="we", padx=4)
        header.grid_columnconfigure(len(theme.COLUMNS) - 1, weight=1)
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=10, pady=2)

        # scrollable rows
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=10, pady=4)
        self.rows_canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.rows_canvas.yview)
        self.rows_frame = tk.Frame(self.rows_canvas)
        self._rows_window = self.rows_canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", self._on_rows_frame_configure)
        self.rows_canvas.bind("<Configure>", lambda e: self.rows_canvas.itemconfigure(self._rows_window, width=e.width))
        self.rows_canvas.configure(yscrollcommand=scrollbar.set)
        self.rows_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", self._on_mousewheel)
        self.root.bind_all("<Button-5>", self._on_mousewheel)

        # pie charts (packed on demand)
        self.pie_frame = tk.Frame(self.root)
        self.pie_panel = PieChartPanel(self.pie_frame, s)

        # status bar
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken")
        status.pack(side="bottom", fill="x")
        self._update_status_bar()

    # --------------------------------------------------------------- scrolling
    def _on_rows_frame_configure(self, _event: tk.Event) -> None:
        with contextlib.suppress(tk.TclError):
            self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all"))

    def _on_mousewheel(self, event: tk.Event) -> None:
        widget = event.widget
        try:
            inside = str(widget).startswith(str(self.rows_canvas))
        except tk.TclError:
            return
        if not inside:
            return
        if getattr(event, "num", None) == 4:
            self.rows_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.rows_canvas.yview_scroll(1, "units")
        else:
            self.rows_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    # ------------------------------------------------------------- event loop
    def _poll(self) -> None:
        """Main-thread poller: drain the worker queue and update views."""
        if self.closing:
            return
        q = self.service.events
        drained = 0
        while drained < 500:  # bound the work per tick to keep the GUI responsive
            try:
                ev = q.get_nowait()
            except Exception:
                break
            self._apply_event(ev)
            drained += 1
        if self.csv_logger.failed and self.logging_var.get():
            self.logging_var.set(False)
            self._notify_once(f"CSV logging disabled: {self.csv_logger.error}")
        self.sched.call_later(POLL_MS, self._poll, key="poll")

    def _apply_event(self, ev: ProbeEvent) -> None:
        target = self._by_id.get(ev.target_id)
        if target is None:
            return  # target deleted while a probe was in flight
        target.stats.record(ev.result)
        self.events_processed += 1
        prev = target.stats.previous_state()
        now_ok = ev.result.ok
        if prev is not None and prev != now_ok and target.sound_enabled:
            self.notifier.state_changed(now_ok)
        row = self._rows.get(target.id)
        if row is not None:
            row.refresh(target)
        self.pie_panel.update_target(target)

    # --------------------------------------------------------- target actions
    def add_target_from_entry(self) -> None:
        text = self.entry.get()
        if self.add_target(text):
            self.entry.delete(0, tk.END)

    def add_target(self, text: str, *, sound: bool = False, paused: bool = False, quiet: bool = False) -> Target | None:
        try:
            parsed = parse_target(text)
        except InvalidTargetError as exc:
            if not quiet:
                messagebox.showerror("Invalid address", str(exc), parent=self.root)
            return None
        if any(t.address == parsed.address for t in self.targets):
            if not quiet:
                messagebox.showinfo("Duplicate", f"{parsed.address} is already being monitored.", parent=self.root)
            return None
        if len(self.targets) >= theme.MAX_TARGETS:
            if not quiet:
                messagebox.showwarning(
                    "Limit reached", f"At most {theme.MAX_TARGETS} targets can be monitored.", parent=self.root
                )
            return None
        target = Target(parsed.address, parsed.kind, sound_enabled=sound, paused=paused or self.all_paused)
        self.targets.append(target)
        self._by_id[target.id] = target
        row = TargetRow(self.rows_frame, target, self._row_callbacks(), self.ui_scale)
        row.frame.pack(fill="x", pady=2)
        self._rows[target.id] = row
        self.service.add_target(target.id, target.address, target.kind, paused=target.paused)
        self.has_unsaved_changes = True
        self._update_positions()
        self._sync_pies()
        self._update_status_bar()
        return target

    def remove_target(self, target: Target) -> None:
        if target.id not in self._by_id:
            return
        self.service.remove_target(target.id)
        self.targets.remove(target)
        self._by_id.pop(target.id, None)
        row = self._rows.pop(target.id, None)
        if row is not None:
            row.destroy()
        self.has_unsaved_changes = True
        self._update_positions()
        self._sync_pies()
        self._update_status_bar()

    def move_target(self, target: Target, delta: int) -> None:
        idx = self.targets.index(target)
        new = idx + delta
        if not 0 <= new < len(self.targets):
            return
        self.targets[idx], self.targets[new] = self.targets[new], self.targets[idx]
        for t in self.targets:
            row = self._rows.get(t.id)
            if row is not None:
                row.frame.pack_forget()
        for t in self.targets:
            row = self._rows.get(t.id)
            if row is not None:
                row.frame.pack(fill="x", pady=2)
        self.has_unsaved_changes = True
        self._update_positions()
        self._sync_pies()

    def toggle_pause(self, target: Target) -> None:
        if target.paused:
            target.paused = False
            self.service.resume(target.id)
        else:
            target.paused = True
            self.service.pause(target.id)
        self._refresh_row(target)
        self._update_status_bar()

    def toggle_sound(self, target: Target) -> None:
        target.sound_enabled = not target.sound_enabled
        self.has_unsaved_changes = True
        self._refresh_row(target)

    def reset_stats(self, target: Target) -> None:
        target.stats.reset()
        self._refresh_row(target)
        self.pie_panel.update_target(target)

    def reset_all_stats(self) -> None:
        for t in self.targets:
            self.reset_stats(t)

    def toggle_all(self) -> None:
        if self.all_paused:
            self.all_paused = False
            self.service.resume_all()
            for t in self.targets:
                t.paused = False
        else:
            self.all_paused = True
            self.service.pause_all()
            for t in self.targets:
                t.paused = True
        self.toggle_all_button.configure(text="Start All" if self.all_paused else "Stop All")
        for t in self.targets:
            self._refresh_row(t)
        self._update_status_bar()

    def restart_all(self) -> None:
        for t in self.targets:
            t.stats.reset()
            t.paused = False
        self.all_paused = False
        self.service.resume_all()
        self.toggle_all_button.configure(text="Stop All")
        for t in self.targets:
            self._refresh_row(t)
            self.pie_panel.update_target(t)
        self._update_status_bar()

    def clear_all_targets(self) -> None:
        if not self.targets:
            return
        answer = messagebox.askyesnocancel(
            "Clear all targets",
            "Export statistics before clearing?\n\n"
            "Yes = export then clear\nNo = clear without exporting\nCancel = keep everything",
            parent=self.root,
        )
        if answer is None:
            return
        if answer and not self.export_statistics():
            return
        for t in list(self.targets):
            self.remove_target(t)
        self.all_paused = False
        self.toggle_all_button.configure(text="Stop All")
        self.has_unsaved_changes = False

    def select_target(self, target: Target) -> None:
        self.entry.delete(0, tk.END)
        self.entry.insert(0, target.address)

    def _row_callbacks(self) -> RowCallbacks:
        return RowCallbacks(
            move_up=lambda t: self.move_target(t, -1),
            move_down=lambda t: self.move_target(t, +1),
            toggle_pause=self.toggle_pause,
            reset=self.reset_stats,
            delete=self.remove_target,
            toggle_sound=self.toggle_sound,
            select=self.select_target,
            context_menu=self._show_context_menu,
        )

    def _show_context_menu(self, event: tk.Event, target: Target) -> None:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Remove", command=lambda: self.remove_target(target))
        menu.add_command(label="Copy address", command=lambda: self._copy(target.address))
        if target.stats.resolved_ip and target.stats.resolved_ip != target.address:
            menu.add_command(
                label=f"Copy resolved IP ({target.stats.resolved_ip})",
                command=lambda: self._copy(target.stats.resolved_ip or ""),
            )
        menu.add_command(label="Reset statistics", command=lambda: self.reset_stats(target))
        menu.add_command(label="Resume" if target.paused else "Pause", command=lambda: self.toggle_pause(target))
        menu.add_checkbutton(
            label="Sound notifications",
            onvalue=True,
            offvalue=False,
            variable=tk.BooleanVar(value=target.sound_enabled),
            command=lambda: self.toggle_sound(target),
        )
        menu.add_separator()
        idx = self.targets.index(target)
        if idx > 0:
            menu.add_command(label="Move up", command=lambda: self.move_target(target, -1))
        if idx < len(self.targets) - 1:
            menu.add_command(label="Move down", command=lambda: self.move_target(target, +1))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _refresh_row(self, target: Target) -> None:
        row = self._rows.get(target.id)
        if row is not None:
            row.refresh(target)

    def _update_positions(self) -> None:
        count = len(self.targets)
        for i, t in enumerate(self.targets):
            row = self._rows.get(t.id)
            if row is not None:
                row.set_position(i, count)

    def _update_status_bar(self) -> None:
        paused = sum(1 for t in self.targets if t.paused)
        log_name = self.csv_logger.path.name if self.csv_logger.enabled else "off"
        self.status_var.set(f"{len(self.targets)} target(s), {paused} paused  |  log: {log_name}")

    # ---------------------------------------------------------------- settings
    def _on_interval_changed(self) -> None:
        try:
            value = int(self.interval_var.get())
        except (tk.TclError, ValueError):
            value = self.settings.ping_interval
        value = max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, value))
        if value != self.interval_var.get():
            self.interval_var.set(value)
        self.settings.ping_interval = value
        self.service.set_interval(value)
        self._schedule_settings_save()

    def _on_logging_toggled(self) -> None:
        enabled = bool(self.logging_var.get())
        self.csv_logger.enabled = enabled
        self.settings.logging_enabled = enabled
        self._update_status_bar()
        self._schedule_settings_save()

    def _schedule_settings_save(self) -> None:
        self.sched.call_debounced("save-settings", SETTINGS_DEBOUNCE_MS, self.save_settings_now)

    def save_settings_now(self) -> None:
        with contextlib.suppress(tk.TclError):
            self.settings.window_geometry = self.root.geometry()
        try:
            save_settings(self.paths.settings_file, self.settings)
        except OSError as exc:
            log.error("Could not save settings: %s", exc)

    # --------------------------------------------------------------- pie charts
    def toggle_pie_charts(self) -> None:
        if self.pie_panel.visible:
            self._hide_pie_charts()
        else:
            self._show_pie_charts()
        self._schedule_settings_save()

    def _show_pie_charts(self) -> None:
        self.pie_panel.show()
        self.pie_frame.pack(side="top", fill="x", padx=10, pady=8, before=self.rows_canvas.master)
        self.pie_button.configure(text="Hide Pie Charts")
        self.settings.show_pie_charts = True
        self._sync_pies()

    def _hide_pie_charts(self) -> None:
        self.pie_panel.hide()
        self.pie_frame.pack_forget()
        self.pie_button.configure(text="Show Pie Charts")
        self.settings.show_pie_charts = False

    def _sync_pies(self) -> None:
        if not self.pie_panel.visible:
            return
        try:
            width = self.root.winfo_width()
        except tk.TclError:
            return
        self.pie_panel.sync(self.targets, width)

    def _on_configure(self, event: tk.Event) -> None:
        # <Configure> on the root fires for every descendant too; only react to the window itself.
        if event.widget is not self.root:
            return
        self.sched.call_debounced("resize", RESIZE_DEBOUNCE_MS, self._on_resize_settled)

    def _on_resize_settled(self) -> None:
        self._sync_pies()
        self._schedule_settings_save()

    # ---------------------------------------------------------------- dialogs
    def show_graph(self) -> None:
        if self._graph is not None:
            try:
                if self._graph.window.winfo_exists():
                    self._graph.window.lift()
                    return
            except tk.TclError:
                pass
        if not self.targets:
            messagebox.showinfo("No data", "Add at least one target first.", parent=self.root)
            return
        try:
            self._graph = HistoryGraphWindow(self.root, lambda: list(self.targets))
        except Exception:
            self._graph = None

    def export_statistics(self) -> bool:
        if not self.targets:
            messagebox.showinfo("Nothing to export", "There are no monitored targets.", parent=self.root)
            return False
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export statistics",
            defaultextension=".csv",
            initialdir=str(self.paths.exports_dir),
            initialfile=export.default_export_name(),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return False
        try:
            export.export_statistics(Path(path), self.targets)
        except OSError as exc:
            log.error("Export failed: %s", exc)
            messagebox.showerror("Export failed", f"Could not write {path}:\n{exc}", parent=self.root)
            return False
        self.status_var.set(f"Statistics exported to {path}")
        return True

    def save_targets_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save target list",
            defaultextension=".json",
            initialdir=str(self.paths.targets_dir),
            initialfile="targets.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return False
        saved = [targets_file.SavedTarget(t.address, t.sound_enabled, t.paused) for t in self.targets]
        try:
            targets_file.save_targets(Path(path), saved)
        except OSError as exc:
            log.error("Save failed: %s", exc)
            messagebox.showerror("Save failed", f"Could not write {path}:\n{exc}", parent=self.root)
            return False
        self.settings.last_targets_file = path
        self.has_unsaved_changes = False
        self._schedule_settings_save()
        self.status_var.set(f"Target list saved to {path}")
        return True

    def load_targets(self) -> bool:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Load target list",
            initialdir=str(self.paths.targets_dir),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return False
        replace = True
        if self.targets:
            answer = messagebox.askyesnocancel(
                "Load target list",
                "Replace the current list?\n\nYes = replace\nNo = add to current list\nCancel = abort",
                parent=self.root,
            )
            if answer is None:
                return False
            replace = answer
        return self.load_targets_from(Path(path), replace=replace)

    def session_file(self) -> Path:
        """Automatically written at exit and restored at the next start."""
        return self.paths.targets_dir / SESSION_FILE_NAME

    def save_session_targets(self) -> None:
        """Best-effort snapshot of the current list (never interrupts shutdown)."""
        saved = [targets_file.SavedTarget(t.address, t.sound_enabled, t.paused) for t in self.targets]
        try:
            targets_file.save_targets(self.session_file(), saved)
        except OSError as exc:
            log.warning("Could not write session file %s: %s", self.session_file(), exc)

    def restore_session_targets(self) -> int:
        """Reload the previous session's targets, if any.  Returns the count added."""
        path = self.session_file()
        if not path.is_file():
            return 0
        try:
            saved, _skipped = targets_file.load_targets(path)
        except (OSError, targets_file.TargetsFileError) as exc:
            log.warning("Ignoring unreadable session file %s: %s", path, exc)
            return 0
        added = 0
        for item in saved:
            if self.add_target(item.address, sound=item.sound_notifications, paused=item.paused, quiet=True):
                added += 1
        self.has_unsaved_changes = False
        if added:
            self.status_var.set(f"Restored {added} target(s) from the previous session")
        return added

    def load_targets_from(self, path: Path, *, replace: bool = True, quiet: bool = False) -> bool:
        try:
            saved, skipped = targets_file.load_targets(path)
        except (OSError, targets_file.TargetsFileError) as exc:
            log.error("Load failed: %s", exc)
            if not quiet:
                messagebox.showerror("Load failed", f"Could not load {path}:\n{exc}", parent=self.root)
            return False
        if replace:
            for t in list(self.targets):
                self.remove_target(t)
        added = 0
        for item in saved:
            if self.add_target(item.address, sound=item.sound_notifications, paused=item.paused, quiet=True):
                added += 1
        self.has_unsaved_changes = False
        self.settings.last_targets_file = str(path)
        self._schedule_settings_save()
        msg = f"Loaded {added} target(s) from {path}"
        if skipped:
            msg += f" ({skipped} invalid/duplicate entries skipped)"
        self.status_var.set(msg)
        return True

    def _open_data_folder(self) -> None:
        try:
            if sys.platform == "win32":
                import os

                os.startfile(str(self.paths.root))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(self.paths.root)])
        except OSError as exc:
            messagebox.showinfo("Data folder", f"{self.paths.root}\n\n({exc})", parent=self.root)

    # --------------------------------------------------------------- lifecycle
    def _confirm_discard_changes(self, verb: str) -> bool:
        if not self.has_unsaved_changes or not self.targets:
            return True
        answer = messagebox.askyesnocancel(
            "Save changes", f"Save the current target list before {verb}?", parent=self.root
        )
        if answer is None:
            return False
        if answer:
            return self.save_targets_as()
        return True

    def restart_program(self) -> None:
        if not messagebox.askyesno("Restart", "Restart the application?", parent=self.root):
            return
        if not self._confirm_discard_changes("restarting"):
            return
        cmd = restart_command()
        try:
            subprocess.Popen(cmd, close_fds=True)
        except OSError as exc:
            log.error("Restart failed: %s", exc)
            messagebox.showerror("Restart failed", str(exc), parent=self.root)
            return
        self.shutdown()

    def on_closing(self) -> None:
        if self.closing:
            return
        if not self._confirm_discard_changes("exiting"):
            return
        self.shutdown()

    def shutdown(self) -> None:
        """Deterministic teardown: stop timers, stop workers, persist, destroy."""
        if self.closing:
            return
        self.closing = True
        self.sched.close()
        if self._graph is not None:
            self._graph.close()
            self._graph = None
        self.pie_panel.clear()
        self.save_session_targets()
        self.save_settings_now()
        done = self.service.shutdown(timeout_s=3.0)
        if not done:
            log.warning("Some monitoring workers were still running at exit (daemon threads)")
        with contextlib.suppress(tk.TclError):
            self.root.destroy()

    # ------------------------------------------------------------------ errors
    def _notify_once(self, text: str) -> None:
        self.status_var.set(text)
        log.warning(text)

    def _report_callback_exception(self, exc_type, exc_value, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Replacement for Tk's default handler: log with traceback, show one concise dialog."""
        log.error("Unhandled exception in Tk callback", exc_info=(exc_type, exc_value, exc_tb))
        now = time.monotonic()
        if self.closing or now - self._last_error_dialog < ERROR_DIALOG_MIN_GAP_S:
            return
        self._last_error_dialog = now
        with contextlib.suppress(tk.TclError):
            messagebox.showerror(
                "Unexpected error",
                f"{exc_type.__name__}: {exc_value}\n\nDetails were written to:\n{self.paths.app_log_file}",
                parent=self.root,
            )


def restart_command() -> list[str]:
    """Command that relaunches this program.  Never uses ``sys.argv[0]`` blindly."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "ip_monitor"]
