"""Probe backend selection.

``select_probe("auto")`` tries, in order, the backends that are appropriate
for the platform and returns the first one that passes a loopback self-test.
On Windows the preference is IcmpSendEcho (no privileges, typed status codes),
then ping3, then ping.exe.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Sequence

from ip_monitor.models import ProbeStatus
from ip_monitor.probes.base import (
    Probe,
    ProbeError,
    ProbePermissionError,
    ProbeUnavailableError,
    resolve_ipv4,
)
from ip_monitor.probes.icmp_api import IcmpApiProbe
from ip_monitor.probes.ping3_probe import Ping3Probe
from ip_monitor.probes.ping_exe import PingExeProbe

log = logging.getLogger(__name__)

BACKENDS: dict[str, Callable[[], Probe]] = {
    "icmp_api": IcmpApiProbe,
    "ping3": Ping3Probe,
    "ping_exe": PingExeProbe,
}


def default_backend_order() -> list[str]:
    if sys.platform == "win32":
        return ["icmp_api", "ping3", "ping_exe"]
    return ["ping3", "ping_exe"]


def self_test(probe: Probe, timeout_s: float = 1.0) -> bool:
    """Probe loopback once.  Any *network* result counts as a working backend;
    permission/unavailability errors mean the backend cannot be used."""
    try:
        result = probe.probe("127.0.0.1", timeout_s)
    except ProbeError as exc:
        log.info("Backend %s failed self-test: %s", probe.name, exc)
        return False
    except Exception:  # defensive: a broken backend must never abort startup
        log.exception("Backend %s crashed during self-test", probe.name)
        return False
    log.info("Backend %s self-test: %s", probe.name, result.status.value)
    return result.status not in (ProbeStatus.PERMISSION_ERROR, ProbeStatus.ICMP_UNAVAILABLE)


def select_probe(preferred: str = "auto", order: Sequence[str] | None = None) -> Probe:
    """Instantiate the preferred backend, or auto-select one.  Raises
    ``ProbeUnavailableError`` if nothing works."""
    names = list(order) if order else default_backend_order()
    if preferred != "auto":
        names = [preferred] + [n for n in names if n != preferred]
    errors: list[str] = []
    for name in names:
        factory = BACKENDS.get(name)
        if factory is None:
            errors.append(f"{name}: unknown backend")
            continue
        try:
            probe = factory()
        except ProbeError as exc:
            errors.append(f"{name}: {exc}")
            continue
        if self_test(probe):
            log.info("Using probe backend '%s'", probe.name)
            return probe
        errors.append(f"{name}: failed self-test")
    raise ProbeUnavailableError("No usable ICMP probe backend: " + "; ".join(errors))


__all__ = [
    "BACKENDS",
    "Probe",
    "ProbeError",
    "ProbePermissionError",
    "ProbeUnavailableError",
    "default_backend_order",
    "resolve_ipv4",
    "select_probe",
    "self_test",
]
