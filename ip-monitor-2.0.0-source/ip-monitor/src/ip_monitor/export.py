"""Statistics export (CSV)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from ip_monitor.models import Target

EXPORT_HEADER = [
    "Target",
    "Resolved IP",
    "Status",
    "Sent",
    "Received",
    "Lost",
    "Packet Loss %",
    "Min RTT (ms)",
    "Max RTT (ms)",
    "Avg RTT (ms)",
    "Current RTT (ms)",
    "Last Successful Probe",
    "Export Time",
]


def _fmt(value: float | None, digits: int = 1) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def statistics_rows(targets: Iterable[Target], now: datetime | None = None) -> list[list[str]]:
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    rows: list[list[str]] = []
    for t in targets:
        s = t.stats
        last_ok = (
            datetime.fromtimestamp(s.last_success_time).strftime("%Y-%m-%d %H:%M:%S") if s.last_success_time else ""
        )
        status = "Paused" if t.paused else (s.last_status.label if s.last_status else "")
        rows.append(
            [
                t.address,
                s.resolved_ip or "",
                status,
                str(s.sent),
                str(s.received),
                str(s.lost),
                _fmt(s.packet_loss_pct),
                _fmt(s.min_rtt_ms),
                _fmt(s.max_rtt_ms),
                _fmt(s.avg_rtt_ms),
                _fmt(s.current_rtt_ms),
                last_ok,
                stamp,
            ]
        )
    return rows


def statistics_csv_text(targets: Iterable[Target]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(EXPORT_HEADER)
    writer.writerows(statistics_rows(targets))
    return buf.getvalue()


def export_statistics(path: Path, targets: Iterable[Target]) -> None:
    """Write the statistics CSV to ``path`` (UTF-8 with BOM so Excel opens it cleanly)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(statistics_csv_text(targets), encoding="utf-8-sig", newline="")


def default_export_name(now: datetime | None = None) -> str:
    return f"ip_stats_{(now or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}.csv"
