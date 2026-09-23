"""Monitoring service: one worker thread per target, results through a queue.

Threading contract
------------------
* Workers never touch Tkinter.  They produce ``ProbeEvent`` objects and put
  them on ``MonitorService.events`` (a ``queue.Queue``).  The GUI drains the
  queue from the Tk main thread with a periodic ``after()`` poller.
* Every worker has its own ``stop`` and ``running`` events.  Pause/resume and
  stop are therefore race-free: the worker is either sleeping on an Event
  (wakes instantly) or inside a bounded probe call (returns within the timeout).
* A removed target can never produce a late update: the event sink checks that
  the target id is still registered *under the service lock* before enqueueing,
  and the GUI additionally ignores events for unknown ids.
"""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ip_monitor.csvlog import ProbeCsvLogger
from ip_monitor.models import ProbeResult, ProbeStatus
from ip_monitor.probes.base import (
    Probe,
    ProbePermissionError,
    ProbeUnavailableError,
    resolve_ipv4,
)
from ip_monitor.validation import TargetKind

log = logging.getLogger(__name__)

DNS_REFRESH_S = 300.0  # re-resolve hostnames at least this often
PAUSE_POLL_S = 0.5


@dataclass(frozen=True)
class ProbeEvent:
    target_id: str
    address: str
    result: ProbeResult


class TargetWorker(threading.Thread):
    """Probes one target in a loop until stopped."""

    def __init__(
        self,
        target_id: str,
        address: str,
        kind: TargetKind,
        probe: Probe,
        sink: Callable[[ProbeEvent], None],
        interval_s: Callable[[], float],
        timeout_s: Callable[[], float],
        paused: bool = False,
    ) -> None:
        super().__init__(name=f"probe-{address}", daemon=True)
        self.target_id = target_id
        self.address = address
        self.kind = kind
        self._probe = probe
        self._sink = sink
        self._interval_s = interval_s
        self._timeout_s = timeout_s
        self.stop_event = threading.Event()
        self.running = threading.Event()  # set = monitoring, clear = paused
        if not paused:
            self.running.set()
        self._resolved_ip: str | None = address if kind is TargetKind.IPV4 else None
        self._resolved_at = 0.0
        self._last_failed = False

    # -- control -------------------------------------------------------------
    def pause(self) -> None:
        self.running.clear()

    def resume(self) -> None:
        self.running.set()

    def stop(self) -> None:
        self.stop_event.set()
        self.running.set()  # wake a paused worker so it can exit

    # -- helpers -------------------------------------------------------------
    def _needs_resolution(self, now: float) -> bool:
        if self.kind is TargetKind.IPV4:
            return False
        if self._resolved_ip is None:
            return True
        return self._last_failed or (now - self._resolved_at) > DNS_REFRESH_S

    def _resolve(self) -> ProbeResult | None:
        """Resolve the hostname; return a failure result if resolution failed."""
        try:
            self._resolved_ip = resolve_ipv4(self.address)
            self._resolved_at = time.time()
            return None
        except socket.gaierror as exc:
            self._resolved_ip = None
            return ProbeResult.failure(ProbeStatus.DNS_FAILURE, exc.strerror or str(exc))
        except OSError as exc:
            self._resolved_ip = None
            return ProbeResult.failure(ProbeStatus.NETWORK_ERROR, str(exc))

    def probe_once(self) -> ProbeResult:
        """Perform one full cycle (resolution + probe) and return the result."""
        now = time.time()
        if self._needs_resolution(now):
            failure = self._resolve()
            if failure is not None:
                self._last_failed = True
                return failure
        ip = self._resolved_ip
        if ip is None:  # unreachable in practice, but keep the type checker honest
            return ProbeResult.failure(ProbeStatus.INVALID_ADDRESS, "no address")
        try:
            result = self._probe.probe(ip, self._timeout_s())
        except ProbePermissionError as exc:
            result = ProbeResult.failure(ProbeStatus.PERMISSION_ERROR, str(exc), ip)
        except ProbeUnavailableError as exc:
            result = ProbeResult.failure(ProbeStatus.ICMP_UNAVAILABLE, str(exc), ip)
        except OSError as exc:
            result = ProbeResult.failure(ProbeStatus.NETWORK_ERROR, str(exc), ip)
        except Exception as exc:  # programming error in a backend: log loudly, keep running
            log.exception("Unexpected error probing %s", self.address)
            result = ProbeResult.failure(ProbeStatus.NETWORK_ERROR, f"internal error: {exc}", ip)
        self._last_failed = not result.ok
        return result

    # -- thread body ---------------------------------------------------------
    def run(self) -> None:
        log.info("Worker started for %s", self.address)
        try:
            while not self.stop_event.is_set():
                if not self.running.wait(PAUSE_POLL_S):
                    continue  # paused
                if self.stop_event.is_set():
                    break
                started = time.monotonic()
                result = self.probe_once()
                if self.stop_event.is_set():
                    break
                self._sink(ProbeEvent(self.target_id, self.address, result))
                # Keep a steady cadence: subtract the time the probe itself took.
                remaining = max(0.05, self._interval_s() - (time.monotonic() - started))
                self.stop_event.wait(remaining)
        except Exception:  # never let a worker die silently
            log.exception("Worker for %s crashed", self.address)
        finally:
            log.info("Worker stopped for %s", self.address)


class MonitorService:
    """Owns all workers.  All public methods are safe to call from the GUI thread."""

    def __init__(
        self,
        probe: Probe,
        csv_logger: ProbeCsvLogger | None = None,
        interval_s: float = 2.0,
        timeout_s: float = 1.0,
    ) -> None:
        self._probe = probe
        self._csv = csv_logger
        self._interval_s = float(interval_s)
        self._timeout_s = float(timeout_s)
        self._lock = threading.Lock()
        self._workers: dict[str, TargetWorker] = {}
        self._retired: list[TargetWorker] = []
        self.events: queue.Queue[ProbeEvent] = queue.Queue()
        self._closed = False

    # -- configuration -------------------------------------------------------
    @property
    def probe(self) -> Probe:
        return self._probe

    @property
    def interval_s(self) -> float:
        return self._interval_s

    def set_interval(self, seconds: float) -> None:
        self._interval_s = float(seconds)

    @property
    def timeout_s(self) -> float:
        return self._timeout_s

    def set_timeout(self, seconds: float) -> None:
        self._timeout_s = float(seconds)

    # -- event sink (called from worker threads) -----------------------------
    def _sink(self, event: ProbeEvent) -> None:
        with self._lock:
            if self._closed or event.target_id not in self._workers:
                return  # target removed while the probe was in flight
        if self._csv is not None:
            self._csv.log(event.address, event.result)
        self.events.put(event)

    # -- target lifecycle ----------------------------------------------------
    def add_target(self, target_id: str, address: str, kind: TargetKind, paused: bool = False) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("MonitorService is closed")
            if target_id in self._workers:
                raise ValueError(f"target {target_id} already monitored")
            worker = TargetWorker(
                target_id,
                address,
                kind,
                self._probe,
                self._sink,
                lambda: self._interval_s,
                lambda: self._timeout_s,
                paused=paused,
            )
            self._workers[target_id] = worker
        worker.start()

    def remove_target(self, target_id: str) -> None:
        with self._lock:
            worker = self._workers.pop(target_id, None)
            if worker is None:
                return
            worker.stop()
            self._retired.append(worker)
        self._reap()

    def _reap(self) -> None:
        with self._lock:
            self._retired = [w for w in self._retired if w.is_alive()]

    def pause(self, target_id: str) -> None:
        with self._lock:
            w = self._workers.get(target_id)
        if w:
            w.pause()

    def resume(self, target_id: str) -> None:
        with self._lock:
            w = self._workers.get(target_id)
        if w:
            w.resume()

    def pause_all(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
        for w in workers:
            w.pause()

    def resume_all(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
        for w in workers:
            w.resume()

    def is_paused(self, target_id: str) -> bool:
        with self._lock:
            w = self._workers.get(target_id)
        return w is not None and not w.running.is_set()

    def target_ids(self) -> list[str]:
        with self._lock:
            return list(self._workers)

    def worker_count(self) -> int:
        with self._lock:
            return len(self._workers)

    def live_thread_count(self) -> int:
        with self._lock:
            return sum(1 for w in list(self._workers.values()) + self._retired if w.is_alive())

    # -- shutdown ------------------------------------------------------------
    def shutdown(self, timeout_s: float = 3.0) -> bool:
        """Stop every worker and wait up to ``timeout_s`` in total.
        Returns True if all threads terminated."""
        with self._lock:
            self._closed = True
            workers = list(self._workers.values()) + list(self._retired)
            self._workers.clear()
            self._retired.clear()
        for w in workers:
            w.stop()
        deadline = time.monotonic() + timeout_s
        all_done = True
        for w in workers:
            w.join(max(0.0, deadline - time.monotonic()))
            if w.is_alive():
                all_done = False
                log.warning("Worker %s did not stop within the shutdown timeout", w.name)
        if self._csv is not None:
            self._csv.close()
        return all_done
