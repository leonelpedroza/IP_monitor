# IP Monitor

Lightweight, real-time ICMP reachability monitor for network engineers.
Enter a few IPv4 addresses or hostnames, click **Add**, and watch reachability
and latency during a maintenance window — without opening a dozen CMD windows.

**Version 2.0.0** · Windows 11 x64 (portable) · Python 3.12/3.13 from source · Tkinter GUI · License: GPL (see [LICENSE](LICENSE))

> Screenshot placeholders: `docs/img/main-window.png`, `docs/img/history-graph.png`

## What it is (and is not)

IP Monitor is the GUI equivalent of running `ping -t` against several hosts at
once. It is meant for router/switch migrations, firewall changes, WAN/LAN
troubleshooting, device replacement and other maintenance-window work.

It is **not** a replacement for SolarWinds, PRTG, Zabbix, Nagios, Catalyst
Center or any SNMP-based NMS. It sends ICMP Echo Requests and nothing else.

## Features

- Monitor up to 64 IPv4 addresses / DNS hostnames simultaneously
- Configurable probe interval (1–60 s) and per-probe timeout
- Per-target status (OK, Timeout, Unreachable, DNS failure, …), row colour (green = up, red = down, yellow = degraded), last-10 probe history, current / min / max / average RTT, packet-loss %
- Distinguishes **success, timeout, destination unreachable, DNS failure, invalid address, network error, permission error, ICMP unavailable, stopped** — not just "failed"
- Colour-coded rows, pie/status charts (last 60 probes), history graph (in-memory, up to 6 h at 2 s) — non-modal, auto-refreshing
- Per-target pause/resume, reset, delete, reorder (buttons, context menu); global Stop All / Start All / Restart All / Reset All
- Sound notification on status change (per target, toggle with the bell)
- Optional CSV probe log, statistics export (Save dialog), save/load target lists (1.x files still load)
- Settings, window size and last target list persist between sessions
- Three ICMP backends, auto-selected: Windows `IcmpSendEcho` API (no Administrator needed), `ping3`, or `ping.exe`
- High-DPI aware (100 %–200 % scaling), no Administrator privileges, no Internet access, no telemetry

## Portable installation (Windows 11)

1. Download `IPMonitor-2.0.0-Windows-x64.zip`.
2. Extract it anywhere (Desktop, `C:\Tools`, USB stick).
3. Double-click `IPMonitor\IPMonitor.exe`.

Python, pip and the source code are **not** required on the target PC.
SmartScreen may warn about an unsigned executable the first time — see
[docs/INSTALLATION.md](docs/INSTALLATION.md).

## Running from source

```powershell
git clone https://github.com/leonelpedroza/ip_monitor.git
cd ip_monitor
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
python -m ip_monitor          # or: python IPMonitor.pyw
```

Supported Python: **3.12 (baseline) and 3.13**. Python 3.14 runs from source
with current matplotlib/PyInstaller releases but is not the packaging
baseline (see [docs/INSTALLATION.md](docs/INSTALLATION.md)).

## Where data is stored

| Item | Location |
|------|----------|
| Settings | `%LOCALAPPDATA%\IPMonitor\config\settings.json` |
| Application log | `%LOCALAPPDATA%\IPMonitor\logs\ip_monitor.log` (rotating) |
| CSV probe logs | `%LOCALAPPDATA%\IPMonitor\logs\` |
| Saved target lists | `%LOCALAPPDATA%\IPMonitor\targets\` |
| Exports (default folder) | `%LOCALAPPDATA%\IPMonitor\exports\` |

**Portable mode:** create an empty `portable.txt` next to `IPMonitor.exe`; data
then lives in `<exe folder>\data\` if that folder is writable. Override
everything with `--data-dir <folder>`. Tools → *Open Data Folder* opens the
active location.

## Building the executable

```powershell
.\build.ps1            # onedir build + ZIP in dist\
.\build.ps1 -OneFile   # additionally produce a single-file exe
```

Details: [docs/BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md).

## Documentation

- [docs/INSTALLATION.md](docs/INSTALLATION.md) — portable install, source install, Python versions
- [docs/USAGE.md](docs/USAGE.md) — every control and status explained
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — threading model, module map, why the 1.x crash cannot return
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — dev environment, tests, lint
- [docs/BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md) — PyInstaller build and packaging
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — "ping fails but the device is up", backends, permissions
- [CHANGELOG.md](CHANGELOG.md)

## Known limitations

- IPv4 only. IPv6 addresses are recognised and rejected with a clear message; the probe abstraction is ready for an IPv6 backend.
- ICMP Echo only — no TCP/HTTP checks.
- Sound notifications use `winsound`; on other platforms the terminal bell is used.
- The `icmp_api` and `ping_exe` backends report RTT with 1 ms resolution (Windows API limitation); `ping3` reports sub-millisecond values.
- Unsigned executable → SmartScreen prompt on first run.
- One thread per target; 64 targets maximum by design.

## License

The original repository declared **GPL** in its README text while the badge
said MIT and the source carried no license header. This release standardises
on **GPL-3.0** as the author's stated intent; see [LICENSE](LICENSE).

---

# IP Monitor (Español)

Monitor ligero de alcanzabilidad ICMP en tiempo real para ingenieros de red.
Ingrese direcciones IPv4 o nombres de host, pulse **Add** y observe la
alcanzabilidad y latencia durante una ventana de mantenimiento, sin abrir
múltiples ventanas de CMD.

- Instalación portátil: descargue el ZIP, descomprima y ejecute `IPMonitor.exe` (no requiere Python).
- Desde el código fuente: Python 3.12 o 3.13, `pip install -e .`, `python -m ip_monitor`.
- Datos del usuario: `%LOCALAPPDATA%\IPMonitor\` (modo portátil con `portable.txt`).
- Solo IPv4 y solo ICMP Echo. No reemplaza un sistema de gestión SNMP.
- Licencia: GPL-3.0 (ver LICENSE).

La documentación completa (en inglés) está en la carpeta `docs/`.
