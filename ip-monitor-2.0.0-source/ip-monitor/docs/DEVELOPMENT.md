# Development

## Environment (Windows 11, PowerShell)

```powershell
git clone https://github.com/leonelpedroza/ip_monitor.git
cd ip_monitor
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"          # runtime + pytest, ruff, mypy, pyinstaller
```

Linux/macOS: `python3.12 -m venv .venv && source .venv/bin/activate`, plus
`sudo apt install python3-tk xvfb` for the GUI tests.

## Everyday commands

```powershell
python -m ip_monitor --debug                  # run with verbose log
python -m ip_monitor --backend ping_exe       # force a backend
python -m ip_monitor --data-dir .\devdata     # keep dev data out of %LOCALAPPDATA%
python -m pytest                              # full suite
python -m pytest -m "not gui"                 # headless subset
python -m pytest tests/test_gui_pie_chart.py -v
ruff check src tests ; ruff format src tests
mypy src
.\build.ps1                                   # package (see BUILD_WINDOWS.md)
```

On Linux CI: `xvfb-run -a python -m pytest`.

## Test layout

| File | Covers |
|------|--------|
| `test_validation.py` | IPv4/hostname parsing, IPv6/URL rejection |
| `test_models_stats.py` | counters, RTT over received only, loss %, deques, row state |
| `test_config.py` | defaults, clamping, atomic write, corrupt file quarantine |
| `test_paths.py` | LOCALAPPDATA, portable marker, override |
| `test_csvlog.py` | header, concurrency, enable/disable |
| `test_export.py`, `test_targets_file.py` | CSV export, JSON v2 + legacy load |
| `test_probes.py` | backend error mapping, `select_probe` order/self-test (ctypes backend mocked) |
| `test_monitor.py` | worker lifecycle, pause/resume, DNS caching, shutdown deadline |
| `test_app.py` | argparse, restart command, DPI scale |
| `test_gui_scheduler.py` | tracked `after`, debounce, close |
| `test_gui_pie_chart.py` | **regression for error.txt** |
| `test_gui_main_window.py` | end-to-end with `FakeProbe`, session restore |

`tests/conftest.py` provides `FakeProbe` (scripted results), `tk_root` (skips
when no display), `pump(root, seconds)`.

## Conventions

- Python ≥ 3.12, `from __future__ import annotations`, full type hints, Ruff
  (line length 110) — configuration in `pyproject.toml`.
- Version lives only in `src/ip_monitor/version.py`; bump it, add a
  CHANGELOG entry, tag `vX.Y.Z`.
- Semantic versioning: MAJOR = incompatible file formats/behaviour, MINOR =
  features, PATCH = fixes.
- No `print()`; use `logging.getLogger(__name__)`.
- Never call Tk from a thread. If you need the GUI to react, put an event on
  the queue or use `AfterScheduler` **from the main thread**.
- Catch specific exceptions; log them; never `except: pass`.

## Release checklist

1. `ruff check`, `ruff format --check`, `mypy src`, `pytest` all green.
2. Bump `version.py`, update `CHANGELOG.md`.
3. `.\build.ps1 -Clean` on a Windows 11 machine.
4. Smoke-test `dist\IPMonitor\IPMonitor.exe` on a clean VM (no Python).
5. Attach `dist\IPMonitor-<ver>-Windows-x64.zip` to the GitHub release.
