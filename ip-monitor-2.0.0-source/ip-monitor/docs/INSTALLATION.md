# Installation

## A. Portable Windows 11 build (recommended for end users)

Requirements: Windows 10/11 64-bit, a normal user account. No Python, pip,
Visual Studio or Internet connection is needed.

1. Download `IPMonitor-<version>-Windows-x64.zip`.
2. Right-click the ZIP → *Properties* → tick **Unblock** (optional, avoids
   extra warnings), then *Extract All…* to any folder you can write to
   (`C:\Tools\IPMonitor`, the Desktop, a USB stick).
3. Double-click `IPMonitor\IPMonitor.exe`.

### SmartScreen / Defender

The executable is not code-signed. On first launch Windows may display
*"Windows protected your PC"*. Click **More info → Run anyway**. Defender
may also scan the file for a few seconds. Do **not** disable SmartScreen or
Defender; if your organisation blocks unsigned binaries, ask IT to whitelist
the file hash, or run from source (section C).

If a corporate endpoint agent quarantines `IPMonitor.exe`, the usual cause is
the PyInstaller bootloader heuristics, not the program itself. The `onedir`
build (default) is far less likely to trigger this than the `onefile` build.

### Where the program writes

Nothing is written next to the executable unless you enable portable mode.

| Data | Path |
|------|------|
| Settings | `%LOCALAPPDATA%\IPMonitor\config\settings.json` |
| Application log | `%LOCALAPPDATA%\IPMonitor\logs\ip_monitor.log` |
| CSV probe logs | `%LOCALAPPDATA%\IPMonitor\logs\ping_log_<timestamp>.csv` |
| Target lists | `%LOCALAPPDATA%\IPMonitor\targets\` |
| Exports | `%LOCALAPPDATA%\IPMonitor\exports\` (default Save location) |

**Portable mode:** create an empty file `portable.txt` beside
`IPMonitor.exe`. If `<exe folder>\data\` can be created and written, it is
used instead of `%LOCALAPPDATA%`; otherwise the program silently falls back to
`%LOCALAPPDATA%` and logs the reason.

**Command line:** `IPMonitor.exe --data-dir D:\mon --targets core.json --backend ping_exe --debug`

### Uninstall

Delete the extracted folder and, optionally, `%LOCALAPPDATA%\IPMonitor`.
Nothing is written to the registry.

## B. Supported Python versions (source installs)

| Python | Status |
|--------|--------|
| 3.12   | **Baseline.** All dependencies and PyInstaller wheels are mature. Used for the official build. |
| 3.13   | Supported and tested by CI-style runs; fine for source and packaging. |
| 3.14   | Runs from source with matplotlib ≥ 3.10.7 and PyInstaller ≥ 6.16. Not used for the official build: fewer pre-built wheels, less field time. |
| 3.10 / 3.11 | Should run (`pyproject.toml` declares `>=3.10`) but is not tested or packaged; use 3.12. |
| ≤ 3.9 | Not supported. |

The original README's "Python 3.6/3.7+" claims are dropped: current
matplotlib and PyInstaller releases no longer support those interpreters.

## C. Running from source on Windows 11

```powershell
winget install Python.Python.3.12        # if not installed; tick "tcl/tk" (default)
git clone https://github.com/leonelpedroza/ip_monitor.git
cd ip_monitor
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -e .                          # runtime dependencies from pyproject.toml
python -m ip_monitor
```

`IPMonitor.pyw` (double-click) does the same without a console window.

If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## D. Other platforms

The application is Windows-first (`winsound`, `IcmpSendEcho`). It also starts
on Linux/macOS for development and testing with the `ping3` (needs
`CAP_NET_RAW`/root or `net.ipv4.ping_group_range`) or `ping_exe` backend;
sound falls back to the terminal bell. Tkinter must be installed
(`sudo apt install python3-tk` on Debian/Ubuntu).
