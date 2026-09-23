"""Plain data models shared by the monitoring service and the GUI.

Nothing in this module imports Tkinter.  A ``Target`` and its ``TargetStats``
live independently of any widget, so destroying or recreating a Tk widget can
never corrupt monitoring state.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from ip_monitor.validation import TargetKind

RECENT_HISTORY = 10  # coloured circles in the row
EXTENDED_HISTORY = 60  # slices in the pie chart
HISTORY_SAMPLES = 10_800  # in-memory samples for the history graph (6 h @ 2 s)


class ProbeStatus(str, Enum):
    """Classification of a single probe attempt."""

    SUCCESS = "success"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"  # explicit ICMP Destination Unreachable / TTL expired
    DNS_FAILURE = "dns_failure"
    INVALID_ADDRESS = "invalid_address"
    NETWORK_ERROR = "network_error"
    PERMISSION_ERROR = "permission_error"
    ICMP_UNAVAILABLE = "icmp_unavailable"
    STOPPED = "stopped"

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]

    @property
    def is_failure(self) -> bool:
        """True for every status that counts as a lost probe."""
        return self not in (ProbeStatus.SUCCESS, ProbeStatus.STOPPED)


_STATUS_LABELS = {
    ProbeStatus.SUCCESS: "OK",
    ProbeStatus.TIMEOUT: "Timeout",
    ProbeStatus.UNREACHABLE: "Unreachable",
    ProbeStatus.DNS_FAILURE: "DNS failure",
    ProbeStatus.INVALID_ADDRESS: "Invalid address",
    ProbeStatus.NETWORK_ERROR: "Network error",
    ProbeStatus.PERMISSION_ERROR: "Permission denied",
    ProbeStatus.ICMP_UNAVAILABLE: "ICMP unavailable",
    ProbeStatus.STOPPED: "Stopped",
}


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of one probe.  Immutable and safe to pass between threads."""

    status: ProbeStatus
    rtt_ms: float | None = None
    timestamp: float = field(default_factory=time.time)
    resolved_ip: str | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ProbeStatus.SUCCESS

    @classmethod
    def success(cls, rtt_ms: float, resolved_ip: str | None = None) -> ProbeResult:
        return cls(ProbeStatus.SUCCESS, rtt_ms=rtt_ms, resolved_ip=resolved_ip)

    @classmethod
    def failure(cls, status: ProbeStatus, message: str = "", resolved_ip: str | None = None) -> ProbeResult:
        return cls(status, rtt_ms=None, resolved_ip=resolved_ip, message=message)


@dataclass
class TargetStats:
    """Statistics for one target.

    Definitions (documented for the export and the About dialog):

    * ``sent``      - probes attempted (every result except STOPPED)
    * ``received``  - probes that returned an echo reply (SUCCESS)
    * ``lost``      - ``sent - received``; includes timeouts, DNS failures and errors
    * ``packet_loss_pct`` - ``lost / sent * 100``
    * ``min/max/avg_rtt_ms`` - computed over *received* replies only.
      Failed probes never contribute to latency statistics; they are
      accounted for in packet loss instead.
    * ``current_rtt_ms`` - RTT of the most recent successful probe, or None
    * ``last_success_time`` - epoch seconds of the most recent SUCCESS
    """

    sent: int = 0
    received: int = 0
    min_rtt_ms: float | None = None
    max_rtt_ms: float | None = None
    sum_rtt_ms: float = 0.0
    current_rtt_ms: float | None = None
    last_success_time: float | None = None
    last_status: ProbeStatus | None = None
    last_message: str = ""
    resolved_ip: str | None = None
    recent: deque[bool | None] = field(default_factory=lambda: deque([None] * RECENT_HISTORY, maxlen=RECENT_HISTORY))
    extended: deque[bool] = field(default_factory=lambda: deque(maxlen=EXTENDED_HISTORY))
    history: deque[tuple[float, float | None]] = field(default_factory=lambda: deque(maxlen=HISTORY_SAMPLES))

    @property
    def lost(self) -> int:
        return self.sent - self.received

    @property
    def packet_loss_pct(self) -> float | None:
        if self.sent == 0:
            return None
        return self.lost / self.sent * 100.0

    @property
    def avg_rtt_ms(self) -> float | None:
        if self.received == 0:
            return None
        return self.sum_rtt_ms / self.received

    @property
    def extended_success_pct(self) -> float | None:
        """Success percentage over the last EXTENDED_HISTORY probes (pie chart)."""
        if not self.extended:
            return None
        return sum(1 for ok in self.extended if ok) / len(self.extended) * 100.0

    def record(self, result: ProbeResult) -> None:
        """Fold one probe result into the statistics."""
        self.last_status = result.status
        self.last_message = result.message
        if result.resolved_ip:
            self.resolved_ip = result.resolved_ip
        if result.status is ProbeStatus.STOPPED:
            return
        self.sent += 1
        if result.ok and result.rtt_ms is not None:
            rtt = float(result.rtt_ms)
            self.received += 1
            self.sum_rtt_ms += rtt
            self.min_rtt_ms = rtt if self.min_rtt_ms is None else min(self.min_rtt_ms, rtt)
            self.max_rtt_ms = rtt if self.max_rtt_ms is None else max(self.max_rtt_ms, rtt)
            self.current_rtt_ms = rtt
            self.last_success_time = result.timestamp
            self.recent.appendleft(True)
            self.extended.appendleft(True)
            self.history.append((result.timestamp, rtt))
        else:
            self.current_rtt_ms = None
            self.recent.appendleft(False)
            self.extended.appendleft(False)
            self.history.append((result.timestamp, None))

    def reset(self) -> None:
        """Clear all counters and histories (resolved IP is kept)."""
        resolved = self.resolved_ip
        self.__init__()  # type: ignore[misc]
        self.resolved_ip = resolved

    def previous_state(self) -> bool | None:
        """State of the probe before the most recent one, or None if unknown."""
        if len(self.recent) < 2:
            return None
        return self.recent[1]


class RowState(str, Enum):
    """Aggregated colour state of a target row (mirrors the original colours)."""

    UNKNOWN = "unknown"  # fewer than RECENT_HISTORY samples
    UP = "up"  # all recent probes succeeded
    DOWN = "down"  # all recent probes failed
    DEGRADED = "degraded"  # mixed
    PAUSED = "paused"


@dataclass
class Target:
    """A monitored endpoint.  Owned by the main thread."""

    address: str
    kind: TargetKind
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    sound_enabled: bool = False
    paused: bool = False
    stats: TargetStats = field(default_factory=TargetStats)

    def row_state(self) -> RowState:
        if self.paused:
            return RowState.PAUSED
        samples = [s for s in self.stats.recent if s is not None]
        if len(samples) < RECENT_HISTORY:
            return RowState.UNKNOWN
        if all(samples):
            return RowState.UP
        if not any(samples):
            return RowState.DOWN
        return RowState.DEGRADED
