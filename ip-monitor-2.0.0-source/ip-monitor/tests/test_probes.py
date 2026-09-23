"""Probe backends are tested with the network mocked out.  No ICMP is sent."""

import socket
import sys

import pytest

from ip_monitor.models import ProbeStatus
from ip_monitor.probes import base, icmp_api, ping_exe, select_probe, self_test
from ip_monitor.probes.base import ProbePermissionError, ProbeUnavailableError
from ip_monitor.probes.ping3_probe import PING3_AVAILABLE, Ping3Probe
from tests.conftest import FakeProbe, ok

# --- ping3 -----------------------------------------------------------------
pytestmark_ping3 = pytest.mark.skipif(not PING3_AVAILABLE, reason="ping3 not installed")


@pytestmark_ping3
@pytest.mark.parametrize(
    "raiser,status",
    [
        ("Timeout", ProbeStatus.TIMEOUT),
        ("HostUnknown", ProbeStatus.DNS_FAILURE),
        ("DestinationHostUnreachable", ProbeStatus.UNREACHABLE),
        ("DestinationUnreachable", ProbeStatus.UNREACHABLE),
        ("TimeToLiveExpired", ProbeStatus.UNREACHABLE),
        ("PingError", ProbeStatus.NETWORK_ERROR),
    ],
)
def test_ping3_exception_mapping(monkeypatch, raiser, status):
    import ping3
    from ping3 import errors

    exc_cls = getattr(errors, raiser)

    def fake_ping(*_a, **_k):
        try:
            raise exc_cls()
        except TypeError:
            raise exc_cls("x") from None

    monkeypatch.setattr(ping3, "ping", fake_ping)
    result = Ping3Probe().probe("10.0.0.1", 1.0)
    assert result.status is status and result.resolved_ip == "10.0.0.1"


@pytestmark_ping3
def test_ping3_success_and_units(monkeypatch):
    import ping3

    monkeypatch.setattr(ping3, "ping", lambda *_a, **_k: 0.0123)
    result = Ping3Probe().probe("10.0.0.1", 1.0)
    assert result.ok and abs(result.rtt_ms - 12.3) < 1e-6
    assert ping3.EXCEPTIONS is True


@pytestmark_ping3
def test_ping3_legacy_return_values(monkeypatch):
    import ping3

    monkeypatch.setattr(ping3, "ping", lambda *_a, **_k: None)
    assert Ping3Probe().probe("10.0.0.1", 1.0).status is ProbeStatus.TIMEOUT
    monkeypatch.setattr(ping3, "ping", lambda *_a, **_k: False)
    assert Ping3Probe().probe("10.0.0.1", 1.0).status is ProbeStatus.DNS_FAILURE


@pytestmark_ping3
def test_ping3_permission_error_propagates_as_probe_error(monkeypatch):
    import ping3

    def denied(*_a, **_k):
        raise PermissionError("raw socket")

    monkeypatch.setattr(ping3, "ping", denied)
    with pytest.raises(ProbePermissionError):
        Ping3Probe().probe("10.0.0.1", 1.0)


@pytestmark_ping3
def test_ping3_generic_oserror_is_network_error(monkeypatch):
    import ping3

    def boom(*_a, **_k):
        raise OSError("network is unreachable")

    monkeypatch.setattr(ping3, "ping", boom)
    assert Ping3Probe().probe("10.0.0.1", 1.0).status is ProbeStatus.NETWORK_ERROR


# --- IcmpSendEcho status classification (pure Python, all platforms) -------
@pytest.mark.parametrize(
    "code,status",
    [
        (icmp_api.IP_REQ_TIMED_OUT, ProbeStatus.TIMEOUT),
        (icmp_api.IP_DEST_HOST_UNREACHABLE, ProbeStatus.UNREACHABLE),
        (icmp_api.IP_DEST_NET_UNREACHABLE, ProbeStatus.UNREACHABLE),
        (icmp_api.IP_TTL_EXPIRED_TRANSIT, ProbeStatus.UNREACHABLE),
        (icmp_api.IP_GENERAL_FAILURE, ProbeStatus.NETWORK_ERROR),
        (12345, ProbeStatus.NETWORK_ERROR),
    ],
)
def test_icmp_api_classification(code, status):
    r = icmp_api.classify_ip_status(code, "10.0.0.1")
    assert r.status is status and r.resolved_ip == "10.0.0.1" and r.message


def test_icmp_api_access_denied_raises():
    with pytest.raises(ProbePermissionError):
        icmp_api.classify_ip_status(icmp_api.ERROR_ACCESS_DENIED, "10.0.0.1")


def test_ipaddr_layout_is_network_byte_order_in_memory():
    assert icmp_api.ipv4_to_ipaddr("1.2.3.4").to_bytes(4, "little") == bytes([1, 2, 3, 4])


@pytest.mark.skipif(sys.platform == "win32", reason="backend is available on Windows")
def test_icmp_api_unavailable_off_windows():
    with pytest.raises(ProbeUnavailableError):
        icmp_api.IcmpApiProbe()


# --- ping.exe parsing ------------------------------------------------------
WIN_OK = "Reply from 8.8.8.8: bytes=32 time=14ms TTL=117\n"
WIN_OK_ES = "Respuesta desde 8.8.8.8: bytes=32 tiempo=14ms TTL=117\n"
WIN_LT1 = "Reply from 10.0.0.1: bytes=32 time<1ms TTL=64\n"
WIN_TIMEOUT = "Request timed out.\n"
WIN_UNREACH = "Reply from 10.0.0.2: Destination host unreachable.\n"
WIN_TTL = "Reply from 10.1.1.1: TTL expired in transit.\n"
LINUX_OK = "64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.045 ms\n"


@pytest.mark.parametrize(
    "rc,out,status,rtt",
    [
        (0, WIN_OK, ProbeStatus.SUCCESS, 14.0),
        (0, WIN_OK_ES, ProbeStatus.SUCCESS, 14.0),
        (0, WIN_LT1, ProbeStatus.SUCCESS, 0.0),
        (1, WIN_TIMEOUT, ProbeStatus.TIMEOUT, None),
        (0, WIN_UNREACH, ProbeStatus.UNREACHABLE, None),  # ping.exe returns 0 here!
        (0, WIN_TTL, ProbeStatus.UNREACHABLE, None),
        (0, LINUX_OK, ProbeStatus.SUCCESS, 0.045),
        (1, "", ProbeStatus.TIMEOUT, None),
    ],
)
def test_ping_exe_parse(rc, out, status, rtt):
    r = ping_exe.parse_ping_output(rc, out, "10.0.0.1")
    assert r.status is status
    assert r.rtt_ms == rtt


def test_ping_exe_command_has_no_shell_and_validated_ip():
    cmd = ping_exe.build_command("C:/Windows/System32/ping.exe", "10.0.0.1", 1.5)
    assert isinstance(cmd, list) and cmd[-1] == "10.0.0.1"
    if sys.platform == "win32":
        assert cmd[1:6] == ["-n", "1", "-w", "1500", "-4"]
    else:
        assert cmd[1:5] == ["-c", "1", "-W", "2"]


def test_ping_exe_missing_binary(monkeypatch):
    monkeypatch.setattr(ping_exe.shutil, "which", lambda _name: None)
    with pytest.raises(ProbeUnavailableError):
        ping_exe.PingExeProbe()


def test_ping_exe_probe_runs_subprocess(monkeypatch, tmp_path):
    fake = tmp_path / "ping"
    fake.write_text("", encoding="utf-8")

    class Proc:
        returncode = 0
        stdout = WIN_OK
        stderr = ""

    calls = {}

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        calls["kw"] = kw
        return Proc()

    monkeypatch.setattr(ping_exe.subprocess, "run", fake_run)
    probe = ping_exe.PingExeProbe(ping_path=str(fake))
    r = probe.probe("8.8.8.8", 1.0)
    assert r.ok and r.rtt_ms == 14.0
    assert "shell" not in calls["kw"] and calls["kw"]["timeout"] == 6.0


# --- resolution helper -----------------------------------------------------
def test_resolve_ipv4_uses_getaddrinfo(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    )
    assert base.resolve_ipv4("example.com") == "93.184.216.34"


def test_resolve_ipv4_empty_result(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(socket.gaierror):
        base.resolve_ipv4("example.com")


# --- backend selection -----------------------------------------------------
def test_self_test_accepts_network_results_and_rejects_probe_errors():
    assert self_test(FakeProbe([ok()])) is True
    bad = FakeProbe([ok()])
    bad.raise_next = ProbePermissionError("no")
    assert self_test(bad) is False


def test_select_probe_falls_back_in_order(monkeypatch):
    from ip_monitor import probes

    class Broken:
        name = "broken"

        def __init__(self):
            raise ProbeUnavailableError("nope")

    good = FakeProbe([ok()])
    monkeypatch.setitem(probes.BACKENDS, "broken", Broken)
    monkeypatch.setitem(probes.BACKENDS, "good", lambda: good)
    assert select_probe("auto", order=["broken", "good"]) is good
    assert select_probe("good", order=["broken"]) is good  # preferred first, even if not in order
    with pytest.raises(ProbeUnavailableError):
        select_probe("auto", order=["broken", "unknown-name"])
