"""Windows ICMP Echo via the IP Helper API (``IcmpSendEcho``).

This is the same mechanism ``ping.exe`` uses.  It needs **no administrator
rights**, no raw socket and no child process, and it returns typed
``IP_STATUS`` codes (timeout, host unreachable, net unreachable, TTL expired)
so failures can be classified precisely.  Round-trip time resolution is
1 millisecond (identical to ``ping.exe``).

The status-code classification is pure Python and unit-tested on every
platform; the ``ctypes`` calls are only reachable on Windows.
"""

from __future__ import annotations

import ctypes
import socket
import struct
import sys

from ip_monitor.models import ProbeResult, ProbeStatus
from ip_monitor.probes.base import ProbePermissionError, ProbeUnavailableError

IP_SUCCESS = 0
IP_BUF_TOO_SMALL = 11001
IP_DEST_NET_UNREACHABLE = 11002
IP_DEST_HOST_UNREACHABLE = 11003
IP_DEST_PROT_UNREACHABLE = 11004
IP_DEST_PORT_UNREACHABLE = 11005
IP_NO_RESOURCES = 11006
IP_BAD_OPTION = 11007
IP_HW_ERROR = 11008
IP_PACKET_TOO_BIG = 11009
IP_REQ_TIMED_OUT = 11010
IP_BAD_REQ = 11011
IP_BAD_ROUTE = 11012
IP_TTL_EXPIRED_TRANSIT = 11013
IP_TTL_EXPIRED_REASSEM = 11014
IP_PARAM_PROBLEM = 11015
IP_SOURCE_QUENCH = 11016
IP_OPTION_TOO_BIG = 11017
IP_BAD_DESTINATION = 11018
IP_GENERAL_FAILURE = 11050

ERROR_ACCESS_DENIED = 5

_UNREACHABLE_CODES = {
    IP_DEST_NET_UNREACHABLE: "Destination net unreachable",
    IP_DEST_HOST_UNREACHABLE: "Destination host unreachable",
    IP_DEST_PROT_UNREACHABLE: "Destination protocol unreachable",
    IP_DEST_PORT_UNREACHABLE: "Destination port unreachable",
    IP_BAD_ROUTE: "Bad route",
    IP_TTL_EXPIRED_TRANSIT: "TTL expired in transit",
    IP_TTL_EXPIRED_REASSEM: "TTL expired during reassembly",
    IP_BAD_DESTINATION: "Bad destination",
}


def classify_ip_status(code: int, ip: str) -> ProbeResult:
    """Map an ``IP_STATUS`` / Win32 error code to a failed ``ProbeResult``."""
    if code == IP_REQ_TIMED_OUT:
        return ProbeResult.failure(ProbeStatus.TIMEOUT, "Request timed out", ip)
    if code in _UNREACHABLE_CODES:
        return ProbeResult.failure(ProbeStatus.UNREACHABLE, _UNREACHABLE_CODES[code], ip)
    if code == ERROR_ACCESS_DENIED:
        raise ProbePermissionError("IcmpSendEcho: access denied")
    return ProbeResult.failure(ProbeStatus.NETWORK_ERROR, f"IP_STATUS {code}", ip)


def ipv4_to_ipaddr(ip: str) -> int:
    """Convert dotted quad to the ``IPAddr`` ULONG layout (network byte order in memory)."""
    return struct.unpack("<L", socket.inet_aton(ip))[0]


if sys.platform == "win32":  # pragma: no cover - Windows only
    from ctypes import wintypes

    class IP_OPTION_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("Ttl", ctypes.c_ubyte),
            ("Tos", ctypes.c_ubyte),
            ("Flags", ctypes.c_ubyte),
            ("OptionsSize", ctypes.c_ubyte),
            ("OptionsData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    class ICMP_ECHO_REPLY(ctypes.Structure):
        _fields_ = [
            ("Address", ctypes.c_ulong),
            ("Status", ctypes.c_ulong),
            ("RoundTripTime", ctypes.c_ulong),
            ("DataSize", ctypes.c_ushort),
            ("Reserved", ctypes.c_ushort),
            ("Data", ctypes.c_void_p),
            ("Options", IP_OPTION_INFORMATION),
        ]

    _INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    def _load_iphlpapi() -> ctypes.WinDLL:
        dll = ctypes.WinDLL("iphlpapi", use_last_error=True)
        dll.IcmpCreateFile.restype = wintypes.HANDLE
        dll.IcmpCreateFile.argtypes = []
        dll.IcmpCloseHandle.restype = wintypes.BOOL
        dll.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
        dll.IcmpSendEcho.restype = wintypes.DWORD
        dll.IcmpSendEcho.argtypes = [
            wintypes.HANDLE,  # IcmpHandle
            ctypes.c_ulong,  # DestinationAddress (IPAddr)
            ctypes.c_void_p,  # RequestData
            wintypes.WORD,  # RequestSize
            ctypes.POINTER(IP_OPTION_INFORMATION),  # RequestOptions
            ctypes.c_void_p,  # ReplyBuffer
            wintypes.DWORD,  # ReplySize
            wintypes.DWORD,  # Timeout (ms)
        ]
        return dll

    class IcmpApiProbe:
        """``IcmpSendEcho`` probe.  One ICMP handle per call - handles are cheap and
        this keeps every worker thread fully independent."""

        name = "icmp_api"
        PAYLOAD = b"IPMonitor-echo-request-payload!!"  # 32 bytes, like ping.exe

        def __init__(self) -> None:
            try:
                self._dll = _load_iphlpapi()
            except OSError as exc:
                raise ProbeUnavailableError(f"iphlpapi not available: {exc}") from exc

        def probe(self, ip: str, timeout_s: float) -> ProbeResult:
            timeout_ms = max(1, int(round(timeout_s * 1000)))
            handle = self._dll.IcmpCreateFile()
            if handle in (None, 0, _INVALID_HANDLE_VALUE):
                err = ctypes.get_last_error()
                if err == ERROR_ACCESS_DENIED:
                    raise ProbePermissionError("IcmpCreateFile: access denied")
                raise ProbeUnavailableError(f"IcmpCreateFile failed (error {err})")
            try:
                data = ctypes.create_string_buffer(self.PAYLOAD, len(self.PAYLOAD))
                reply_size = ctypes.sizeof(ICMP_ECHO_REPLY) + len(self.PAYLOAD) + 8
                reply_buf = ctypes.create_string_buffer(reply_size)
                options = IP_OPTION_INFORMATION(Ttl=128, Tos=0, Flags=0, OptionsSize=0)
                count = self._dll.IcmpSendEcho(
                    handle,
                    ipv4_to_ipaddr(ip),
                    ctypes.cast(data, ctypes.c_void_p),
                    len(self.PAYLOAD),
                    ctypes.byref(options),
                    ctypes.cast(reply_buf, ctypes.c_void_p),
                    reply_size,
                    timeout_ms,
                )
                if count == 0:
                    return classify_ip_status(ctypes.get_last_error(), ip)
                reply = ICMP_ECHO_REPLY.from_buffer(reply_buf)
                if reply.Status == IP_SUCCESS:
                    return ProbeResult.success(float(reply.RoundTripTime), ip)
                return classify_ip_status(int(reply.Status), ip)
            finally:
                self._dll.IcmpCloseHandle(handle)

else:

    class IcmpApiProbe:  # type: ignore[no-redef]
        name = "icmp_api"

        def __init__(self) -> None:
            raise ProbeUnavailableError("The ICMP API backend is only available on Windows")

        def probe(self, ip: str, timeout_s: float) -> ProbeResult:  # pragma: no cover
            raise ProbeUnavailableError("The ICMP API backend is only available on Windows")
