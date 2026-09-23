"""MonitorService / TargetWorker with an injected probe - no real ICMP."""

import contextlib
import queue
import socket
import threading
import time

import pytest

from ip_monitor import monitor as mon
from ip_monitor.models import ProbeStatus
from ip_monitor.monitor import MonitorService, TargetWorker
from ip_monitor.probes.base import ProbePermissionError, ProbeUnavailableError
from ip_monitor.validation import TargetKind
from tests.conftest import FakeProbe, ok, timeout


def _drain(q: queue.Queue, timeout_s: float = 2.0, want: int = 1) -> list:
    events = []
    end = time.monotonic() + timeout_s
    while len(events) < want and time.monotonic() < end:
        with contextlib.suppress(queue.Empty):
            events.append(q.get(timeout=0.05))
    return events


def test_success_and_timeout_events_flow_through_queue():
    svc = MonitorService(FakeProbe([ok(7.0), timeout()]), interval_s=0.05)
    svc.add_target("t1", "10.0.0.1", TargetKind.IPV4)
    events = _drain(svc.events, want=2)
    assert [e.result.status for e in events] == [ProbeStatus.SUCCESS, ProbeStatus.TIMEOUT]
    assert events[0].result.rtt_ms == 7.0 and events[0].target_id == "t1"
    assert svc.shutdown(2.0)


def test_dns_failure_is_reported_without_probing(monkeypatch):
    def fail(_host):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(mon, "resolve_ipv4", fail)
    probe = FakeProbe()
    svc = MonitorService(probe, interval_s=0.05)
    svc.add_target("t1", "nope.invalid", TargetKind.HOSTNAME)
    ev = _drain(svc.events)[0]
    assert ev.result.status is ProbeStatus.DNS_FAILURE and "known" in ev.result.message
    assert probe.calls == []
    svc.shutdown()


def test_hostname_is_resolved_then_probed_and_cached(monkeypatch):
    calls = []

    def resolve(host):
        calls.append(host)
        return "93.184.216.34"

    monkeypatch.setattr(mon, "resolve_ipv4", resolve)
    probe = FakeProbe([ok()])
    svc = MonitorService(probe, interval_s=0.02)
    svc.add_target("t1", "example.com", TargetKind.HOSTNAME)
    _drain(svc.events, want=3)
    svc.shutdown()
    assert calls == ["example.com"]  # resolved once, cached while successful
    assert probe.calls and all(ip == "93.184.216.34" for ip, _ in probe.calls)


def test_hostname_is_re_resolved_after_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(mon, "resolve_ipv4", lambda h: (calls.append(h), "10.9.9.9")[1])
    probe = FakeProbe([timeout(), timeout(), timeout()])
    svc = MonitorService(probe, interval_s=0.02)
    svc.add_target("t1", "flaky.example", TargetKind.HOSTNAME)
    _drain(svc.events, want=3)
    svc.shutdown()
    assert len(calls) >= 2


@pytest.mark.parametrize(
    "exc,status",
    [
        (ProbePermissionError("denied"), ProbeStatus.PERMISSION_ERROR),
        (ProbeUnavailableError("gone"), ProbeStatus.ICMP_UNAVAILABLE),
        (OSError("boom"), ProbeStatus.NETWORK_ERROR),
        (RuntimeError("bug"), ProbeStatus.NETWORK_ERROR),
    ],
)
def test_probe_errors_are_classified_and_worker_survives(exc, status):
    probe = FakeProbe([ok()])
    probe.raise_next = exc
    svc = MonitorService(probe, interval_s=0.02)
    svc.add_target("t1", "10.0.0.1", TargetKind.IPV4)
    events = _drain(svc.events, want=2)
    assert events[0].result.status is status
    assert events[1].result.status is ProbeStatus.SUCCESS  # worker kept going
    svc.shutdown()


def test_removed_target_produces_no_more_events():
    probe = FakeProbe([ok()], delay_s=0.2)  # probe in flight while we remove
    svc = MonitorService(probe, interval_s=0.02)
    svc.add_target("t1", "10.0.0.1", TargetKind.IPV4)
    time.sleep(0.05)  # worker is now inside the 200 ms probe
    svc.remove_target("t1")
    time.sleep(0.4)
    assert svc.events.empty()
    assert svc.worker_count() == 0
    assert svc.shutdown()


def test_pause_and_resume():
    svc = MonitorService(FakeProbe([ok()]), interval_s=0.02)
    svc.add_target("t1", "10.0.0.1", TargetKind.IPV4, paused=True)
    time.sleep(0.15)
    assert svc.events.empty() and svc.is_paused("t1")
    svc.resume("t1")
    assert _drain(svc.events)
    svc.pause("t1")
    time.sleep(0.6)  # PAUSE_POLL_S + interval
    _drain(svc.events, timeout_s=0.1, want=100)
    time.sleep(0.2)
    assert svc.events.empty()
    svc.shutdown()


def test_pause_all_resume_all():
    svc = MonitorService(FakeProbe([ok()]), interval_s=0.02)
    for i in range(3):
        svc.add_target(f"t{i}", f"10.0.0.{i}", TargetKind.IPV4)
    svc.pause_all()
    assert all(svc.is_paused(f"t{i}") for i in range(3))
    svc.resume_all()
    assert not any(svc.is_paused(f"t{i}") for i in range(3))
    svc.shutdown()


def test_shutdown_stops_all_threads_including_paused_and_retired():
    svc = MonitorService(FakeProbe([ok()]), interval_s=5.0)  # long interval: must wake on stop
    svc.add_target("a", "10.0.0.1", TargetKind.IPV4)
    svc.add_target("b", "10.0.0.2", TargetKind.IPV4, paused=True)
    svc.add_target("c", "10.0.0.3", TargetKind.IPV4)
    svc.remove_target("c")
    before = threading.active_count()
    t0 = time.monotonic()
    assert svc.shutdown(3.0)
    assert time.monotonic() - t0 < 2.0  # did not wait for the 5 s interval
    assert svc.live_thread_count() == 0
    assert threading.active_count() <= before
    with pytest.raises(RuntimeError):
        svc.add_target("d", "10.0.0.4", TargetKind.IPV4)


def test_duplicate_target_id_rejected():
    svc = MonitorService(FakeProbe(), interval_s=0.5)
    svc.add_target("a", "10.0.0.1", TargetKind.IPV4)
    with pytest.raises(ValueError):
        svc.add_target("a", "10.0.0.1", TargetKind.IPV4)
    svc.shutdown()


def test_interval_and_timeout_changes_reach_worker():
    probe = FakeProbe([ok()])
    svc = MonitorService(probe, interval_s=0.5, timeout_s=1.0)
    svc.add_target("a", "10.0.0.1", TargetKind.IPV4)
    _drain(svc.events)
    svc.set_timeout(0.3)
    svc.set_interval(0.02)
    _drain(svc.events, want=4)
    svc.shutdown()
    assert probe.calls[-1][1] == 0.3
    assert svc.interval_s == 0.02


def test_csv_logger_receives_every_event(tmp_path):
    from ip_monitor.csvlog import ProbeCsvLogger

    csv_logger = ProbeCsvLogger(tmp_path / "log.csv")
    svc = MonitorService(FakeProbe([ok()]), csv_logger=csv_logger, interval_s=0.02)
    svc.add_target("a", "10.0.0.1", TargetKind.IPV4)
    events = _drain(svc.events, want=3)
    svc.shutdown()
    lines = (tmp_path / "log.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) - 1 >= len(events)


def test_worker_probe_once_direct():
    w = TargetWorker("x", "10.0.0.1", TargetKind.IPV4, FakeProbe([ok(3.0)]), lambda e: None, lambda: 1.0, lambda: 1.0)
    r = w.probe_once()
    assert r.ok and r.rtt_ms == 3.0 and r.resolved_ip == "10.0.0.1"
