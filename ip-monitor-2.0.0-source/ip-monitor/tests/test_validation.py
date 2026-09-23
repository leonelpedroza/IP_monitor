import pytest

from ip_monitor.validation import InvalidTargetError, TargetKind, is_valid_target, parse_target


@pytest.mark.parametrize(
    "text,expected",
    [
        ("10.0.0.1", "10.0.0.1"),
        (" 192.168.1.254 ", "192.168.1.254"),
        ("0.0.0.0", "0.0.0.0"),
        ("255.255.255.255", "255.255.255.255"),
    ],
)
def test_valid_ipv4(text, expected):
    parsed = parse_target(text)
    assert parsed.kind is TargetKind.IPV4
    assert parsed.address == expected


@pytest.mark.parametrize("text", ["256.1.1.1", "1.2.3", "1.2.3.4.5", "01.2.3.4", "1..2.3", "1.2.3.-1"])
def test_invalid_ipv4_is_not_treated_as_hostname(text):
    with pytest.raises(InvalidTargetError):
        parse_target(text)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("example.com", "example.com"),
        ("Router-1.Corp.Example.COM.", "router-1.corp.example.com"),
        ("localhost", "localhost"),
        ("sw1", "sw1"),
        ("a-b.c-d.e", "a-b.c-d.e"),
    ],
)
def test_valid_hostnames(text, expected):
    parsed = parse_target(text)
    assert parsed.kind is TargetKind.HOSTNAME
    assert parsed.address == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "-bad.example.com",
        "bad-.example.com",
        "under_score.example",
        "a" * 64 + ".com",
        "host name",
        "x." * 130,
        "exa mple.com",
    ],
)
def test_invalid_hostnames(text):
    with pytest.raises(InvalidTargetError):
        parse_target(text)


def test_urls_are_rejected_with_explanation():
    with pytest.raises(InvalidTargetError, match="not a URL"):
        parse_target("https://example.com")
    with pytest.raises(InvalidTargetError):
        parse_target("example.com/path")


def test_ipv6_rejected_by_default_but_recognised():
    with pytest.raises(InvalidTargetError, match="IPv6"):
        parse_target("2001:db8::1")
    parsed = parse_target("2001:db8::1", allow_ipv6=True)
    assert parsed.kind is TargetKind.IPV6
    assert parsed.address == "2001:db8::1"


def test_validation_never_does_dns(monkeypatch):
    import socket

    def boom(*a, **k):  # pragma: no cover - should never be called
        raise AssertionError("DNS lookup attempted during validation")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(socket, "gethostbyname", boom)
    assert is_valid_target("does-not-exist.example")
