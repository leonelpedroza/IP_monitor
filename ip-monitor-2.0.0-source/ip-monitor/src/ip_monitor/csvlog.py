"""Thread-safe per-session CSV probe log.

Many worker threads call :meth:`ProbeCsvLogger.log`; a single lock serialises
writes so rows can never interleave.  The file is opened once and flushed after
every row so the log is useful even if the process is killed.
"""

from __future__ import annotations

import contextlib
import csv
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import IO

from ip_monitor.models import ProbeResult

log = logging.getLogger(__name__)

CSV_HEADER = ["Timestamp", "Target", "Resolved IP", "Status", "Response Time (ms)"]


def format_rtt_for_csv(rtt_ms: float | None) -> str:
    return "" if rtt_ms is None else f"{rtt_ms:.2f}"


class ProbeCsvLogger:
    """Append-only CSV writer shared by all monitoring workers."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self._enabled = enabled
        self._lock = threading.Lock()
        self._file: IO[str] | None = None
        self._writer: csv.writer | None = None  # type: ignore[valid-type]
        self._failed = False
        self.error: str | None = None

    @classmethod
    def session_path(cls, logs_dir: Path, now: float | None = None) -> Path:
        stamp = datetime.fromtimestamp(now or time.time()).strftime("%Y-%m-%d_%H-%M-%S")
        return logs_dir / f"ping_log_{stamp}.csv"

    # -- state ---------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._enabled and not self._failed

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def failed(self) -> bool:
        return self._failed

    # -- I/O -----------------------------------------------------------------
    def _open(self) -> None:
        """Open the file lazily (called with the lock held)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        self._file = open(self.path, "a", encoding="utf-8", newline="")  # noqa: SIM115 - kept open for the session
        self._writer = csv.writer(self._file)
        if new_file:
            self._writer.writerow(CSV_HEADER)
            self._file.flush()

    def log(self, target_address: str, result: ProbeResult) -> None:
        """Write one row.  Never raises; a persistent failure disables logging."""
        if not self.enabled:
            return
        row = [
            datetime.fromtimestamp(result.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            target_address,
            result.resolved_ip or "",
            result.status.value,
            format_rtt_for_csv(result.rtt_ms),
        ]
        with self._lock:
            try:
                if self._file is None:
                    self._open()
                assert self._writer is not None and self._file is not None
                self._writer.writerow(row)
                self._file.flush()
            except OSError as exc:
                self._failed = True
                self.error = str(exc)
                log.error("Probe CSV log disabled - cannot write %s: %s", self.path, exc)
                self._close_locked()

    def _close_locked(self) -> None:
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.close()
        self._file = None
        self._writer = None

    def close(self) -> None:
        with self._lock:
            self._close_locked()
