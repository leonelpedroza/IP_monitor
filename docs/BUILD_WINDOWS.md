# Building the Windows 11 portable executable

## Prerequisites

- Windows 10/11 x64 with Python 3.12 (or 3.13) from python.org or `winget install Python.Python.3.12` — keep the default **tcl/tk** component.
- PowerShell 5.1 or 7. If scripts are blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- No Visual Studio, no Administrator rights, no code-signing certificate required.

## One command

```powershell
cd ip_monitor
.\build.ps1
```

`build.ps1` (also reachable via `build.bat` for double-click use):

1. creates/updates `.venv` and installs `requirements.txt` + `requirements-dev.txt`;
2. runs `ruff` and the test suite (skip with `-SkipTests`);
3. generates the version resource from `version.py` (`packaging/make_version_info.py`);
4. runs PyInstaller with `packaging/IPMonitor.spec`;
5. copies README, LICENSE, CHANGELOG, USAGE/TROUBLESHOOTING docs and third-party licences into `dist\IPMonitor\`;
6. produces `dist\IPMonitor-<version>-Windows-x64.zip`.

Options: `-OneFile` (also build a single exe → `dist\onefile\`), `-Clean`
(remove `build/`, `dist/`, `.venv` first), `-Python py -3.13` (choose interpreter).

## Output

```
dist\IPMonitor\
  IPMonitor.exe          <- run this
  _internal\             <- Python runtime, Tk, matplotlib, ping3
  README.txt  LICENSE  docs\
dist\IPMonitor-2.0.0-Windows-x64.zip
```

## onedir vs onefile

| | onedir (default) | onefile |
|-|------------------|---------|
| Start-up | instant | 1–3 s (self-extracts to `%TEMP%`) |
| Antivirus false positives | rare | frequent (self-extracting stub) |
| Files to distribute | folder / ZIP | one exe |
| Restart Program | works | works (re-extracts) |
| Recommended | **yes** | only when a single file is mandatory |

## What the spec does

- Entry `packaging/entry.py` (imports `ip_monitor.app:main`).
- Hidden imports for `tkinter`, `matplotlib.backends.backend_tkagg`, `ping3`.
- Excludes Qt, scipy, pandas, IPython and other heavy matplotlib optional deps.
- Embeds `assets/icon.ico`, the version resource and `packaging/IPMonitor.manifest`
  (`asInvoker` → never asks for elevation; Per-Monitor V2 DPI; long paths).
- `console=False`, `uac_admin=False`.

## Code signing (optional, recommended for distribution)

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a dist\IPMonitor\IPMonitor.exe
```

Without signing, users see the SmartScreen prompt once per machine; the
reputation improves as the file is downloaded and run.

## Troubleshooting the build

| Symptom | Fix |
|---------|-----|
| `tkinter` not found in the exe | reinstall Python with the tcl/tk option |
| `ModuleNotFoundError: matplotlib.backends.backend_tkagg` at runtime | run `.\build.ps1 -Clean`; the hidden import is in the spec |
| Defender deletes `IPMonitor.exe` right after the build | add `dist\` to exclusions during development; prefer onedir; sign the binary |
| Wrong version in About / ZIP name | only `src/ip_monitor/version.py` is read — edit that, rebuild |
| Build works, exe silently exits | run `IPMonitor.exe --debug` from a console and read `%LOCALAPPDATA%\IPMonitor\logs\ip_monitor.log` |
