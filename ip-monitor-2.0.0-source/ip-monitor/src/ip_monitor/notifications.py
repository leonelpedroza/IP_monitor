"""Sound notifications (Windows ``winsound``; silent no-op elsewhere).

Must only be called from the GUI thread - it is driven by the main-thread
event poller, never by monitoring workers.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

log = logging.getLogger(__name__)

try:  # pragma: no cover - platform specific
    import winsound  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    winsound = None  # type: ignore[assignment]

SOUND_AVAILABLE = winsound is not None and sys.platform == "win32"


def _beep_up() -> None:  # pragma: no cover - platform specific
    winsound.MessageBeep(winsound.MB_OK)  # type: ignore[union-attr, attr-defined]


def _beep_down() -> None:  # pragma: no cover - platform specific
    winsound.MessageBeep(winsound.MB_ICONHAND)  # type: ignore[union-attr, attr-defined]


class SoundNotifier:
    """Plays a sound when a target's state changes.  Injectable for tests."""

    def __init__(
        self,
        up: Callable[[], None] | None = None,
        down: Callable[[], None] | None = None,
    ) -> None:
        if up is None or down is None:
            if SOUND_AVAILABLE:
                up, down = _beep_up, _beep_down
            else:
                up = down = lambda: None
        self._up = up
        self._down = down

    def state_changed(self, now_up: bool) -> None:
        try:
            (self._up if now_up else self._down)()
        except Exception as exc:  # winsound errors are not fatal
            log.warning("Could not play notification sound: %s", exc)
