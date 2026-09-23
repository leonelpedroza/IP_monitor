# Changelog

All notable changes to IP Monitor are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and the
project uses [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-09-23

Complete re-engineering of the 1.3 single-file application.

### Fixed
- **`_tkinter.TclError: invalid command name ".!frameN.!canvas"`** (error.txt).
  Pie-chart canvases were destroyed and recreated on every window `<Configure>`
  event, but targets that dropped out of the first four rows (or were deleted)
  kept a reference to the destroyed canvas and every probe scheduled a redraw
  on it. Chart lifecycle is now owned by `PieChartPanel`, every `after()` job
  is tracked/cancelled by `AfterScheduler`, and redraws are no-ops for charts
  that no longer exist. Regression tests: `tests/test_gui_pie_chart.py`,
  `tests/test_gui_main_window.py`.
- Worker threads no longer touch Tkinter objects (`IntVar`/`BooleanVar`
  reads, `after()` calls from threads). Workers emit plain `ProbeEvent`s
  through a `queue.Queue`; the main thread drains it every 100 ms.
- DNS resolution moved off the GUI thread (an unresolvable hostname froze the
  window in 1.x).
- CSV log corruption from concurrent per-thread `open()/write()` calls; one
  writer, one lock.
- Average RTT included 0.0 for failed probes; min/max ignored sub-1 ms
  results. All statistics now use received probes only.
- Duplicate `update_pie_charts()` calls, tooltip bindings re-created on every
  probe, `root.bind("<Configure>")` firing for every child widget.
- Restart used `sys.argv[0]` and broke under PyInstaller; startup tried to run
  `pip install ping3`.
- Settings/target files written to the current working directory (often
  read-only for a packaged exe); corrupt settings crashed startup.

### Added
- Probe backends with a common `Probe` interface: Windows `IcmpSendEcho`
  (`icmp_api`, no Administrator), `ping3`, `ping.exe`. Auto-selection with a
  loopback self-test; `--backend` override.
- Distinct statuses: success, timeout, unreachable, DNS failure, invalid
  address, network error, permission error, ICMP unavailable, stopped.
- Statistics: sent / received / lost / loss %, current RTT, last successful
  probe, resolved IP, DNS re-resolution after failures.
- `Export Statistics…` with a Save dialog; `Tools → Clear All Targets…`;
  `Open Data Folder`; `Copy address` / `Copy resolved IP` context-menu items.
- User data in `%LOCALAPPDATA%\IPMonitor` with a portable mode
  (`portable.txt`), `--data-dir`, atomic settings writes, corrupt-file quarantine.
- Rotating application log (`logs/ip_monitor.log`), Tk exception hook.
- High-DPI awareness (Per-Monitor V2), scaled column widths.
- History graph reads in-memory samples (works with CSV logging off), is
  non-modal and auto-refreshes.
- Version in one place (`ip_monitor/version.py`), shown in About and in the
  ZIP name.
- `pytest` suite (148 tests), Ruff configuration, PyInstaller spec, `build.ps1`,
  `build.bat`, `clean.ps1`, manifest and version resource.
- Documentation set under `docs/`.

### Changed
- Project restructured into `src/ip_monitor/` package.
- Probe interval range widened from 2–10 s to 1–60 s.
- "Reset & Save Stats" split into *Export Stats…* (no reset) and
  *Clear All Targets…* (offers an export first).
- Graph window is no longer modal.
- "URL" terminology replaced by "hostname" everywhere.
- Python baseline 3.12/3.13 (3.6/3.7 claims removed).
- README no longer claims Linux/macOS support; the tool is Windows-first
  (`winsound`, `IcmpSendEcho`) although it runs on other platforms for development.

### Removed
- Runtime `pip install` of missing dependencies.
- Reading the CSV log to build the graph.

## [1.3] - original single-file release
- Tkinter GUI, ping3 probing, pie charts, matplotlib history graph, CSV log.
