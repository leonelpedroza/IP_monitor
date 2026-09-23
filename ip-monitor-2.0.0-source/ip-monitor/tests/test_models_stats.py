import time

from ip_monitor.models import EXTENDED_HISTORY, RECENT_HISTORY, ProbeResult, ProbeStatus, RowState, Target, TargetStats
from ip_monitor.validation import TargetKind
from tests.conftest import ok, timeout


def test_success_updates_latency_and_counts():
    s = TargetStats()
    for rtt in (10.0, 30.0, 20.0):
        s.record(ok(rtt))
    assert (s.sent, s.received, s.lost) == (3, 3, 0)
    assert s.min_rtt_ms == 10.0 and s.max_rtt_ms == 30.0 and s.avg_rtt_ms == 20.0
    assert s.current_rtt_ms == 20.0
    assert s.packet_loss_pct == 0.0
    assert s.last_success_time is not None


def test_failed_probes_do_not_pollute_latency():
    s = TargetStats()
    s.record(ok(10.0))
    s.record(timeout())
    s.record(ok(20.0))
    assert s.avg_rtt_ms == 15.0  # 30 / 2, not 30 / 3
    assert s.min_rtt_ms == 10.0 and s.max_rtt_ms == 20.0
    assert s.sent == 3 and s.received == 2 and s.lost == 1
    assert round(s.packet_loss_pct, 2) == 33.33
    assert s.current_rtt_ms == 20.0


def test_failure_clears_current_rtt():
    s = TargetStats()
    s.record(ok(10.0))
    s.record(timeout())
    assert s.current_rtt_ms is None
    assert s.last_status is ProbeStatus.TIMEOUT


def test_empty_stats_are_none_not_zero():
    s = TargetStats()
    assert s.avg_rtt_ms is None and s.min_rtt_ms is None and s.packet_loss_pct is None
    assert s.extended_success_pct is None


def test_histories_are_bounded():
    s = TargetStats()
    for _ in range(EXTENDED_HISTORY + 50):
        s.record(ok())
    assert len(s.recent) == RECENT_HISTORY
    assert len(s.extended) == EXTENDED_HISTORY
    assert s.extended_success_pct == 100.0


def test_recent_is_newest_first():
    s = TargetStats()
    s.record(timeout())
    s.record(ok())
    assert s.recent[0] is True and s.recent[1] is False
    assert s.previous_state() is False


def test_stopped_result_is_not_counted():
    s = TargetStats()
    s.record(ProbeResult.failure(ProbeStatus.STOPPED))
    assert s.sent == 0 and s.last_status is ProbeStatus.STOPPED


def test_reset_keeps_resolved_ip():
    s = TargetStats()
    s.record(ProbeResult.success(5.0, "10.1.1.1"))
    s.reset()
    assert s.sent == 0 and s.resolved_ip == "10.1.1.1"
    assert list(s.recent) == [None] * RECENT_HISTORY


def test_row_state_transitions():
    t = Target("10.0.0.1", TargetKind.IPV4)
    assert t.row_state() is RowState.UNKNOWN
    for _ in range(RECENT_HISTORY):
        t.stats.record(ok())
    assert t.row_state() is RowState.UP
    t.stats.record(timeout())
    assert t.row_state() is RowState.DEGRADED
    for _ in range(RECENT_HISTORY):
        t.stats.record(timeout())
    assert t.row_state() is RowState.DOWN
    t.paused = True
    assert t.row_state() is RowState.PAUSED


def test_history_samples_keep_timestamps():
    s = TargetStats()
    before = time.time()
    s.record(ok(3.0))
    ts, rtt = s.history[-1]
    assert before <= ts <= time.time() and rtt == 3.0
    s.record(timeout())
    assert s.history[-1][1] is None


def test_status_labels_and_failure_flag():
    assert ProbeStatus.DNS_FAILURE.label == "DNS failure"
    assert ProbeStatus.SUCCESS.is_failure is False
    assert ProbeStatus.TIMEOUT.is_failure is True
    assert ProbeStatus.STOPPED.is_failure is False
