# Architecture

## The one rule

**Only the Tk main thread touches Tk.** Worker threads produce plain data
(`ProbeEvent`) and put it on a `queue.Queue`; the main thread drains that
queue every 100 ms, updates the model and refreshes widgets in place.

```
  TargetWorker (thread per target)                     Tk main thread
  ┌───────────────────────────────┐   queue.Queue   ┌────────────────────────────────┐
  │ resolve DNS (cached 300 s)    │ ─ProbeEvent──▶  │ MainWindow._drain_events()     │
  │ probe.probe(ip, timeout)       │                 │   Target.stats.record(result)  │
  │ sleep(interval) / pause event │                 │   TargetRow.refresh(target)    │
  │ ProbeCsvLogger.write (locked) │                 │   PieChartPanel.update_target()│
  └───────────────────────────────┘                 │   SoundNotifier on transitions │
                                                    └────────────────────────────────┘
```

Nothing in `monitor.py`, `probes/`, `models.py`, `csvlog.py` imports Tkinter.

## Module map

| Module | Responsibility |
|--------|----------------|
| `version.py` | Single source of the version string. |
| `app.py` | Entry point: argparse, DPI awareness, logging, paths, probe selection, Tk root, `MainWindow`, session restore, mainloop. |
| `paths.py` | `%LOCALAPPDATA%\IPMonitor` layout, portable mode, `--data-dir`. |
| `config.py` | `Settings` dataclass, clamping, atomic JSON write, corrupt-file quarantine. |
| `logging_setup.py` | Rotating application log; Tk exception hook installation. |
| `validation.py` | `parse_target()` → `TargetKind.IPV4 / HOSTNAME`; rejects IPv6, URLs, garbage. |
| `models.py` | `ProbeStatus`, `ProbeResult`, `TargetStats` (counters, RTT, deques), `Target`, `RowState`. No widgets. |
| `probes/base.py` | `Probe` protocol: `probe(ip, timeout_s) -> ProbeResult`, `name`; `resolve_ipv4()` helper. |
| `probes/icmp_api.py` | Windows `IcmpCreateFile`/`IcmpSendEcho` via ctypes (no Administrator). Maps `IP_STATUS` codes to `ProbeStatus`. |
| `probes/ping3_probe.py` | `ping3` (raw socket) with error translation. |
| `probes/ping_exe.py` | `ping.exe -n 1 -w <ms>` via `subprocess` list args, no shell, output parsed. |
| `probes/__init__.py` | `select_probe("auto")` — tries backends in order with a loopback self-test. |
| `monitor.py` | `TargetWorker` thread, `MonitorService` (add/remove/pause/resume/shutdown). |
| `csvlog.py` | One CSV file per session, one lock, header written lazily. |
| `export.py` | Statistics CSV export. |
| `targets_file.py` | Target-list JSON v2 + 1.x formats. |
| `notifications.py` | `SoundNotifier` (winsound / bell), edge-triggered on up↔down. |
| `gui/scheduler.py` | `AfterScheduler` — tracked/keyed `after()` with cancel-all and widget-existence guard. |
| `gui/target_row.py` | One row widget set; `refresh(target)` updates in place. |
| `gui/pie_chart.py` | `PieChart` (a Canvas) and `PieChartPanel` (owns chart lifecycle). |
| `gui/history_graph.py` | Non-modal matplotlib window fed from `TargetStats.history`. |
| `gui/main_window.py` | Composition root of the GUI; all user actions. |
| `gui/theme.py`, `gui/tooltip.py`, `gui/about.py` | Colours/columns/formatting, tooltip, About dialog. |

## Lifecycle of a target

1. `MainWindow.add_target()` validates input, creates `Target`, `TargetRow`, and calls `MonitorService.add_target()`.
2. `MonitorService` starts a `TargetWorker` (daemon thread) with a stop `Event` and a pause `Event`.
3. Each cycle the worker resolves (if needed), probes, writes the CSV row, and puts a `ProbeEvent(target_id, result)` on the queue.
4. The main thread's poller matches the event to a live `Target` by id — events for removed targets are dropped, which is what makes delete-while-probing safe.
5. `remove_target()` removes the row, asks the service to stop the worker (non-blocking), and lets `PieChartPanel.sync()` rebuild charts if the shown set changed.
6. `shutdown()` closes the scheduler (cancels every pending `after`), clears charts, saves session + settings, joins workers (≤ 3 s), then destroys the root.

## Why the 1.x crash cannot come back

The 1.3 failure (`invalid command name ".!frame5.!frame328.!canvas"`) needed
three things at once: chart canvases recreated on every `<Configure>` event,
model rows holding references to those canvases, and `after()` callbacks
scheduled from worker threads with no cancellation. Each is gone:

- Charts are owned by `PieChartPanel`; `sync()` rebuilds only when the set of
  shown targets or the chart size changes. `PieChart.update()` returns
  `False` and does nothing when `winfo_exists()` is false; `update_target()`
  ignores unknown targets.
- `Target` has no widget attributes.
- `AfterScheduler.call_later()` wraps every callback in a guard that checks the
  scheduler is open and the widget exists; `call_debounced(key, ms, fn)` replaces an
  earlier job with the same key; `close()` cancels everything. Root `<Configure>` is
  filtered to `event.widget is root` and debounced (300 ms).

Regression coverage: `tests/test_gui_pie_chart.py` (demoted/removed target,
destroyed chart, hide/show, resize) and `tests/test_gui_main_window.py`
(delete/reorder with charts visible, resize storms, shutdown). Every GUI test
asserts `root.callback_errors == []`.

## Threading and shutdown guarantees

- Workers never call Tk, never read `tk.Variable`s; interval/timeout are
  plain floats read from `MonitorService` under a lock.
- Pause is an `Event`; a paused worker sleeps on it, so pausing is immediate.
- Stop is an `Event` checked between phases; `stop()` never blocks the GUI.
- `shutdown()` joins with a deadline. Workers are daemon threads, so a probe
  stuck in a slow backend cannot keep the process alive.
- The CSV logger serialises writes with one lock; `enabled` toggles are
  atomic; the file is created on first write only.

## Persistence

| File | Written by | When |
|------|------------|------|
| `config/settings.json` | `config.save_settings` (atomic) | debounced 0.8 s after any change; at exit |
| `targets/last-session.json` | `MainWindow.save_session_targets` | at exit |
| `targets/*.json` | File → Save | on demand |
| `logs/ping_log_*.csv` | `ProbeCsvLogger` | every probe (when enabled) |
| `logs/ip_monitor.log` | logging | rotating, 1 MB × 3 |
| `exports/*.csv` | Export Stats… | on demand |

## Extension points

- New backend: implement `Probe` in `probes/`, register in `BACKENDS`.
- IPv6: `TargetKind.IPV6` already parses; add an `Icmp6SendEcho2` backend and
  lift the rejection in `validation.py`.
- New statistic: extend `TargetStats.record()` and `export.EXPORT_HEADER`.
