"""Shared fixtures.

* ``fake_probe`` - a scripted probe so no ICMP packets are sent.
* ``tk_root``    - a real Tk root; the test is skipped when no display is
                   available (e.g. headless CI without Xvfb).
"""

from __future__ import annotations

import contextlib
import sys
import threading
import time
from collections import deque
from collections.abc import Iterable
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ip_monitor.models import ProbeResult, ProbeStatus  # noqa: E402  (path set above)


class FakeProbe:
    """Returns scripted results in order (last one repeats).  Thread-safe."""

    name = "fake"

    def __init__(self, script: Iterable[ProbeResult] | None = None, delay_s: float = 0.0) -> None:
        self._script = deque(script or [ProbeResult.success(12.5, "127.0.0.1")])
        self._last = self._script[-1]
        self.delay_s = delay_s
        self.calls: list[tuple[str, float]] = []
        self._lock = threading.Lock()
        self.raise_next: Exception | None = None

    def probe(self, ip: str, timeout_s: float) -> ProbeResult:
        with self._lock:
            self.calls.append((ip, timeout_s))
            exc = self.raise_next
            self.raise_next = None
            result = self._script.popleft() if len(self._script) > 1 else self._last
        if exc is not None:
            raise exc
        if self.delay_s:
            time.sleep(self.delay_s)
        return ProbeResult(result.status, result.rtt_ms, time.time(), ip, result.message)


@pytest.fixture
def fake_probe() -> FakeProbe:
    return FakeProbe()


def ok(rtt: float = 10.0) -> ProbeResult:
    return ProbeResult.success(rtt, "127.0.0.1")


def timeout() -> ProbeResult:
    return ProbeResult.failure(ProbeStatus.TIMEOUT, "Request timed out", "127.0.0.1")


@pytest.fixture
def tk_root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # no display
        pytest.skip(f"Tk display not available: {exc}")
    root.withdraw()
    errors: list[tuple] = []
    root.report_callback_exception = lambda *args: errors.append(args)  # type: ignore[assignment]
    root.callback_errors = errors  # type: ignore[attr-defined]
    yield root
    with contextlib.suppress(tk.TclError):
        root.destroy()


def pump(root, seconds: float) -> None:
    """Run the Tk event loop for ``seconds`` (processes after() callbacks)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)
