"""Probe backed by the ``ping3`` library (pure-Python ICMP via raw sockets).

Behaviour notes (verified against ping3 4.x/5.x):

* ``ping3.EXCEPTIONS`` is a module-level switch.  We enable it so timeouts
  and unreachable replies arrive as typed exceptions instead of ``None``/``False``.
* Raw sockets need elevated privileges on Linux (unless ``ping_group_range``
  allows SOCK_DGRAM); on Windows a standard user can usually open a raw ICMP
  socket, but endpoint security products may block it.  ``PermissionError``
  is therefore mapped to ``ProbePermissionError`` so the backend selector can
  fall back to another mechanism.
"""

from __future__ import annotations

import socket

from ip_monitor.models import ProbeResult, ProbeStatus
from ip_monitor.probes.base import ProbePermissionError, ProbeUnavailableError

try:
    import ping3
    from ping3 import errors as ping3_errors

    PING3_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency present in packaged builds
    ping3 = None  # type: ignore[assignment]
    ping3_errors = None  # type: ignore[assignment]
    PING3_AVAILABLE = False


class Ping3Probe:
    name = "ping3"

    def __init__(self) -> None:
        if not PING3_AVAILABLE:
            raise ProbeUnavailableError("ping3 is not installed")
        ping3.EXCEPTIONS = True

    def probe(self, ip: str, timeout_s: float) -> ProbeResult:
        try:
            delay_s = ping3.ping(ip, timeout=timeout_s, unit="s")
        except ping3_errors.Timeout:
            return ProbeResult.failure(ProbeStatus.TIMEOUT, "Request timed out", ip)
        except ping3_errors.HostUnknown as exc:
            return ProbeResult.failure(ProbeStatus.DNS_FAILURE, str(exc), ip)
        except (ping3_errors.DestinationUnreachable, ping3_errors.TimeExceeded) as exc:
            return ProbeResult.failure(ProbeStatus.UNREACHABLE, type(exc).__name__, ip)
        except ping3_errors.PingError as exc:
            return ProbeResult.failure(ProbeStatus.NETWORK_ERROR, str(exc), ip)
        except PermissionError as exc:
            raise ProbePermissionError(f"ping3 raw socket denied: {exc}") from exc
        except socket.gaierror as exc:
            return ProbeResult.failure(ProbeStatus.DNS_FAILURE, str(exc), ip)
        except OSError as exc:
            return ProbeResult.failure(ProbeStatus.NETWORK_ERROR, str(exc), ip)

        if delay_s is None:  # EXCEPTIONS=False fallback semantics
            return ProbeResult.failure(ProbeStatus.TIMEOUT, "Request timed out", ip)
        if delay_s is False:
            return ProbeResult.failure(ProbeStatus.DNS_FAILURE, "Unknown host", ip)
        return ProbeResult.success(float(delay_s) * 1000.0, ip)
