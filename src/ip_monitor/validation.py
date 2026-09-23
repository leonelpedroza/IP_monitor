"""Target address validation.

Uses the standard library (``ipaddress``) for IP literals and an RFC 1123
label check for hostnames.  **No DNS lookup happens here** - validation must
never block the GUI thread.  Name resolution is performed by the monitoring
worker and reported as a ``DNS_FAILURE`` probe result.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import Enum

MAX_HOSTNAME_LENGTH = 253
_LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")


class TargetKind(str, Enum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    HOSTNAME = "hostname"


class InvalidTargetError(ValueError):
    """Raised when the text cannot be used as a monitoring target."""


@dataclass(frozen=True)
class ParsedTarget:
    address: str  # normalised form
    kind: TargetKind


def parse_target(text: str, *, allow_ipv6: bool = False) -> ParsedTarget:
    """Validate and normalise a target string.

    Accepts an IPv4 address or a DNS hostname / FQDN.  IPv6 literals are
    recognised but rejected unless ``allow_ipv6`` is True (IPv6 probing is
    not implemented in this release - see docs/USAGE.md, Known limitations).
    """
    if text is None:
        raise InvalidTargetError("Address is empty.")
    candidate = text.strip()
    if not candidate:
        raise InvalidTargetError("Address is empty.")
    if any(ch.isspace() for ch in candidate):
        raise InvalidTargetError("Address must not contain spaces.")
    if "://" in candidate or "/" in candidate:
        raise InvalidTargetError("Enter an IP address or hostname, not a URL. HTTP/HTTPS monitoring is not supported.")

    # IP literal?
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.version == 4:
            return ParsedTarget(str(ip), TargetKind.IPV4)
        if allow_ipv6:
            return ParsedTarget(ip.compressed, TargetKind.IPV6)
        raise InvalidTargetError("IPv6 addresses are not supported in this version.")

    # Something that looks like a broken IPv4 (all digits and dots) should not
    # silently be treated as a hostname.
    if re.fullmatch(r"[\d.]+", candidate):
        raise InvalidTargetError(f"'{candidate}' is not a valid IPv4 address.")

    host = candidate.rstrip(".").lower()
    if not host or len(host) > MAX_HOSTNAME_LENGTH:
        raise InvalidTargetError(f"'{candidate}' is not a valid hostname.")
    labels = host.split(".")
    if not all(_LABEL_RE.match(label) for label in labels):
        raise InvalidTargetError(f"'{candidate}' is not a valid hostname.")
    return ParsedTarget(host, TargetKind.HOSTNAME)


def is_valid_target(text: str) -> bool:
    try:
        parse_target(text)
    except InvalidTargetError:
        return False
    return True
