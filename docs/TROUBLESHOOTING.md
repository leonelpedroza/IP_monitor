# Troubleshooting

## "IP Monitor says Down/Timeout but the device is up"

An ICMP failure is **evidence, not proof**. Before escalating, check:

| Cause | How to recognise it | What to do |
|-------|---------------------|-----------|
| Host firewall drops Echo Request (Windows Defender Firewall default for public profile, most servers) | TCP services (RDP, SSH, HTTPS) work; `Timeout` forever | Allow "File and Printer Sharing (Echo Request – ICMPv4-In)" on the target, or accept that ICMP is not a health signal for that host |
| Network ACL / firewall policy blocks ICMP on the path | All hosts behind one segment time out, others fine | Check ACLs on the L3 boundary; `tracert` to see where replies stop |
| ICMP rate limiting / control-plane policing on routers and switches | Occasional `Timeout` in a regular pattern; loss grows with more targets or a shorter interval | Raise the interval (5–10 s); do not read sporadic loss to a router's own IP as link loss |
| VPN / split tunnel | Corporate IPs unreachable when the tunnel is down, or resolvable only through it | Confirm the tunnel; note that some VPN clients block ICMP |
| Asymmetric routing / NAT | Replies take a different path and get dropped | Check routing; ICMP has no ports, so PAT can misattribute replies |
| DNS problems | Status `DNS failure`; tooltip shows the resolver error | Use the IP instead; check `nslookup`; IP Monitor re-resolves after failures |
| Wrong target | `Invalid address` | IPv6 and URLs are not supported; enter an IPv4 address or plain hostname |
| Local network down | `Network error` on **every** target at once | Wi-Fi / cable / adapter |

Conversely, "OK" only proves that ICMP echo works end-to-end — a host can
answer pings while its application is dead.

## RTT numbers look coarse (0 ms, 1 ms, 2 ms)

The Windows `IcmpSendEcho` API and `ping.exe` report round-trip time in
whole milliseconds; `<1 ms` means below that resolution. Switch to
`--backend ping3` for sub-millisecond values (needs raw sockets; works for
normal users on most Windows builds, may need Administrator on hardened
images).

## Status "Permission denied" or "ICMP unavailable"

The selected backend cannot open an ICMP socket/handle. Normally the
automatic selection picks a working one (`icmp_api` on Windows never needs
elevation). If you forced a backend with `--backend`, remove the flag. On
Linux, `ping3` needs `CAP_NET_RAW` or `net.ipv4.ping_group_range`; use
`--backend ping_exe`.

Help → About shows which backend is in use.

## Sound does not play

Sounds are per target: click the 🔔 on the row (green = enabled). Sound
plays only on **transitions** (up→down, down→up), not on every failure.
Check the Windows volume mixer for `IPMonitor.exe`.

## Settings or target list did not persist

- Data lives in `%LOCALAPPDATA%\IPMonitor` (Tools → Open Data Folder). If a
  `portable.txt` marker exists next to the exe but the folder is read-only,
  the app falls back to `%LOCALAPPDATA%` and logs it.
- A corrupt `settings.json` is renamed `settings.json.corrupt-<timestamp>`
  and defaults are used; look in `logs\ip_monitor.log`.
- Named lists (File → Save) and the automatic `last-session.json` are
  different files; loading a named list replaces the current one.

## The window is tiny / blurry on a 4K screen

The exe is Per-Monitor-V2 DPI aware and scales its columns. If you run from
source with an old `python.exe` shortcut that has a compatibility override,
remove the override (Properties → Compatibility → Change high DPI settings).

## "Unexpected error" dialog

The dialog is rate-limited (one per 30 s) and the full traceback is in
`logs\ip_monitor.log`. Please attach that file, your Windows version and the
backend name (Help → About) when reporting an issue.

## Restart Program does nothing

The exe spawns a new copy of itself and exits; if a security product blocks
the spawn, start it manually. From source it runs `python -m ip_monitor`.

## High CPU

64 targets at a 1 s interval means 64 probes/s plus 64 row refreshes; use a
2–5 s interval for large lists. Hide pie charts if the machine is slow.

## Collecting diagnostics

```
%LOCALAPPDATA%\IPMonitor\logs\ip_monitor.log    application log (rotating)
%LOCALAPPDATA%\IPMonitor\logs\ping_log_*.csv    per-probe results
IPMonitor.exe --debug                            verbose logging for one run
```
