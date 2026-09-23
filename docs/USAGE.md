# Usage

## Workflow

```
Launch IP Monitor → type an IPv4 address or hostname → Add (or Enter)
→ watch status / RTT → add more targets → export or save when done → close
```

Everything you add is remembered: on exit the current target list is
snapshotted to `targets\last-session.json` and restored at the next start,
together with the window size, interval, logging and pie-chart settings.
Named target lists (File → Save/Load) are independent of this snapshot; if you
changed a list since it was saved, you are asked whether to save it on exit.

## Main window

```
IP address / hostname: [ 10.0.0.1        ] [Add]   Interval (s): [2]           backend: icmp_api
[x] Enable CSV logging [Reset All Stats] [Stop All] [Restart All] [View Graph] [Export Stats...] [Show Pie Charts]
   Target        Last 10          Status    Current  Min   Max   Avg   Loss   Controls
▲▼ 10.0.0.1     ●●●●●●●●●●       OK        1 ms     <1 ms 3 ms  1 ms  0 %    [Stop][Reset][Delete] 🔔
```

### Adding targets

Accepted input: an IPv4 address (`192.168.1.1`) or a DNS hostname / FQDN
(`core-sw1`, `www.example.com`). IPv6 addresses and URLs
(`http://…`) are rejected with an explanation. Duplicates are refused.
Maximum 64 targets. Hostnames are resolved in the background; the resolved IP
is shown in the tooltip and in the context menu.

### Columns

| Column | Meaning |
|--------|---------|
| ▲▼ | Move the row up/down (also in the context menu) |
| Target | Address as typed. Tooltip: resolved IP and last error detail |
| Last 10 | Newest probe on the left. Green = reply, red = no reply, grey = no data |
| Status | Result of the latest probe: **OK, Timeout, Unreachable, DNS failure, Invalid address, Network error, Permission denied, ICMP unavailable, Stopped, Paused, Waiting** |
| Current / Min / Max / Avg | RTT of the last reply and min/max/mean over **replies only** since the last reset. `<1 ms` = below the backend's resolution |
| Loss | `lost / sent × 100` since the last reset |
| Controls | Stop/Start (pause), Reset (statistics), Delete, 🔔 sound toggle |

Row colours: green – all of the last 10 probes replied; red – none replied;
yellow – mixed; grey text – paused; no colour – fewer than 10 samples yet.

### Statistics definitions

- **Sent** – probes attempted (all statuses except *Stopped*).
- **Received** – probes with an Echo Reply.
- **Lost** – Sent − Received (timeouts, unreachable, DNS/network errors all count as lost).
- **Loss %** – Lost / Sent × 100.
- **Min / Max / Avg RTT** – over Received only. Failed probes never enter the RTT figures.
- **Last successful probe** – timestamp of the most recent reply (shown in exports and tooltips).

### Controls

| Control | Effect |
|---------|--------|
| Interval (s) | Time between probes for all targets, 1–60 s (default 2). Applied immediately. |
| Enable CSV logging | Write every probe to `logs\ping_log_<timestamp>.csv` (one file per session). |
| Reset All Stats / Reset | Clear counters and history (keeps targets). |
| Stop All / Start All | Pause or resume every target. |
| Restart All | Reset statistics and resume all targets. |
| View Graph | Non-modal RTT history graph (last 6 h at 2 s). Select a row first to focus that target; the graph refreshes itself. |
| Export Stats… | Save dialog → CSV with one row per target (sent, received, lost, loss %, min/max/avg/current RTT, last status, last reply time, resolved IP). Statistics are **not** reset. |
| Show / Hide Pie Charts | Ring chart per target: success % over the last 60 probes. |
| 🔔 | Play a sound when this target changes between up and down. |

### Menus

- **File**: Save Target List… (Ctrl+S), Load Target List… (Ctrl+O), Export Statistics…, Exit.
- **Tools**: Reset All Statistics, Stop All / Start All, Restart All, Clear All Targets… (offers an export first), View History Graph, Open Data Folder, Restart Program.
- **Help**: About (version, backend, data folder).

### Context menu (right-click a row)

Remove, Copy address, Copy resolved IP, Reset statistics, Pause/Resume,
Sound notifications, Move up, Move down.

## Target list files

JSON, format version 2:

```json
{"version": 2, "targets": [{"address": "10.0.0.1", "sound_notifications": true, "paused": false}]}
```

Files saved by IP Monitor 1.x (`["10.0.0.1"]` or `[{"ip": …, "notifications": …}]`)
load unchanged.

## Command-line options

```
IPMonitor.exe [--data-dir DIR] [--targets FILE] [--backend auto|icmp_api|ping3|ping_exe] [--debug] [--version]
```

## Closing

Closing the window stops every worker thread, flushes the CSV log and saves
settings. If a probe is in flight the shutdown waits for it (at most one
timeout, 1 s by default).
