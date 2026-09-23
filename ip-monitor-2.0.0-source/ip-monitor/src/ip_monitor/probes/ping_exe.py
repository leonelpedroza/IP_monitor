"""Probe that shells out to the operating system ``ping`` executable.

Last-resort backend: always available on Windows, needs no privileges, but
costs a process per probe and parses localised text.  Arguments are passed as
a list (never through a shell) and the destination is an already-validated
IPv4 literal, so command injection is not possible.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys

from ip_monitor.models import ProbeResult, ProbeStatus
from ip_monitor.probes.base import ProbeUnavailableError

log = logging.getLogger(__name__)

# "time=12ms", "time<1ms", "tiempo=12ms", "Zeit=12ms", "time=0.123 ms" ...
_RTT_RE = re.compile(r"[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)


def build_command(ping_path: str, ip: str, timeout_s: float) -> list[str]:
    timeout_ms = max(1, int(round(timeout_s * 1000)))
    if sys.platform == "win32":
        return [ping_path, "-n", "1", "-w", str(timeout_ms), "-4", ip]
    # Linux/macOS: -W takes whole seconds on Linux, so round up.
    import math

    return [ping_path, "-c", "1", "-W", str(max(1, math.ceil(timeout_s))), ip]


def parse_ping_output(returncode: int, output: str, ip: str) -> ProbeResult:
    """Classify the output of a single-packet ``ping`` invocation."""
    text = output or ""
    lower = text.lower()
    if "ttl=" in lower:
        m = _RTT_RE.search(text)
        rtt = float(m.group(1).replace(",", ".")) if m else 0.0
        if m and "<" in text[m.start() : m.start() + 1]:
            rtt = 0.0
        return ProbeResult.success(rtt, ip)
    if "unreachable" in lower or "inaccesible" in lower or "nicht erreichbar" in lower:
        return ProbeResult.failure(ProbeStatus.UNREACHABLE, "Destination unreachable", ip)
    if "ttl expired" in lower or "time to live exceeded" in lower:
        return ProbeResult.failure(ProbeStatus.UNREACHABLE, "TTL expired in transit", ip)
    if "could not find host" in lower or "unknown host" in lower or "name or service" in lower:
        return ProbeResult.failure(ProbeStatus.DNS_FAILURE, "Unknown host", ip)
    if "general failure" in lower or "transmit failed" in lower:
        return ProbeResult.failure(ProbeStatus.NETWORK_ERROR, "Transmit failed", ip)
    if returncode == 0:
        # Reply received but no TTL (very unusual) - treat as success without RTT detail.
        return ProbeResult.success(0.0, ip)
    return ProbeResult.failure(ProbeStatus.TIMEOUT, "Request timed out", ip)


class PingExeProbe:
    name = "ping_exe"

    def __init__(self, ping_path: str | None = None) -> None:
        found = ping_path or shutil.which("ping")
        if not found:
            raise ProbeUnavailableError("ping executable not found on PATH")
        self._ping: str = found
        self._creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def probe(self, ip: str, timeout_s: float) -> ProbeResult:
        cmd = build_command(self._ping, ip, timeout_s)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s + 5.0,
                creationflags=self._creationflags,
            )
        except subprocess.TimeoutExpired:
            return ProbeResult.failure(ProbeStatus.TIMEOUT, "ping process timed out", ip)
        except OSError as exc:
            return ProbeResult.failure(ProbeStatus.NETWORK_ERROR, f"cannot run ping: {exc}", ip)
        return parse_ping_output(proc.returncode, (proc.stdout or "") + (proc.stderr or ""), ip)
