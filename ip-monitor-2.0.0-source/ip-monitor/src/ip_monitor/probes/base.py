"""Probe abstraction.

A *probe* sends one ICMP Echo Request to an already-resolved IPv4 address and
classifies the outcome.  Name resolution is deliberately outside the probe so
that DNS failures are reported distinctly and so probes can be unit-tested
without the network.
"""

from __future__ import annotations

import socket
from typing import Protocol, runtime_checkable

from ip_monitor.models import ProbeResult


class ProbeError(Exception):
    """Base class for probe-infrastructure problems (not for normal network failures)."""


class ProbePermissionError(ProbeError):
    """The probe mechanism needs privileges this process does not have."""


class ProbeUnavailableError(ProbeError):
    """The probe mechanism cannot be used on this system at all."""


@runtime_checkable
class Probe(Protocol):
    """A single-shot ICMP echo probe."""

    name: str

    def probe(self, ip: str, timeout_s: float) -> ProbeResult:
        """Send one echo request to ``ip`` and return a classified result.

        Implementations return ``ProbeResult`` for every *network* outcome
        (success, timeout, unreachable ...).  They raise ``ProbePermissionError``
        or ``ProbeUnavailableError`` only for infrastructure problems.
        """
        ...


def resolve_ipv4(hostname: str) -> str:
    """Resolve a hostname to an IPv4 address.  Raises ``socket.gaierror``."""
    infos = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise socket.gaierror(socket.EAI_NONAME, "no address returned")
    return str(infos[0][4][0])
