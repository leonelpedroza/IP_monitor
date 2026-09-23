"""Application settings with tolerant loading and atomic saving."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MIN_INTERVAL_S = 1
MAX_INTERVAL_S = 60
DEFAULT_INTERVAL_S = 2
MIN_TIMEOUT_S = 0.2
MAX_TIMEOUT_S = 10.0
DEFAULT_TIMEOUT_S = 1.0
PROBE_BACKENDS = ("auto", "icmp_api", "ping3", "ping_exe")


@dataclass
class Settings:
    """Persistent user settings.  Every field has a safe default."""

    ping_interval: int = DEFAULT_INTERVAL_S
    probe_timeout: float = DEFAULT_TIMEOUT_S
    logging_enabled: bool = True
    show_pie_charts: bool = False
    probe_backend: str = "auto"
    window_geometry: str = ""
    last_targets_file: str = ""

    def validated(self) -> Settings:
        """Return a copy with every value clamped to its legal range."""
        s = Settings(**asdict(self))
        try:
            s.ping_interval = int(s.ping_interval)
        except (TypeError, ValueError):
            s.ping_interval = DEFAULT_INTERVAL_S
        s.ping_interval = max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, s.ping_interval))
        try:
            s.probe_timeout = float(s.probe_timeout)
        except (TypeError, ValueError):
            s.probe_timeout = DEFAULT_TIMEOUT_S
        s.probe_timeout = max(MIN_TIMEOUT_S, min(MAX_TIMEOUT_S, s.probe_timeout))
        s.logging_enabled = bool(s.logging_enabled)
        s.show_pie_charts = bool(s.show_pie_charts)
        if s.probe_backend not in PROBE_BACKENDS:
            s.probe_backend = "auto"
        s.window_geometry = str(s.window_geometry or "")
        s.last_targets_file = str(s.last_targets_file or "")
        return s

    @classmethod
    def from_dict(cls, data: Any) -> Settings:
        """Build settings from a JSON object, ignoring unknown or bad keys."""
        s = cls()
        if not isinstance(data, dict):
            return s
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in known:
                setattr(s, key, value)
        return s.validated()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.validated())


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file + ``os.replace``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def load_settings(path: Path) -> Settings:
    """Load settings; a missing or corrupt file yields defaults.

    A corrupt file is renamed to ``settings.json.corrupt-<timestamp>`` so the
    user can inspect it and the application still starts.
    """
    if not path.exists():
        return Settings()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        log.error("Settings file %s is unreadable or corrupt: %s", path, exc)
        try:
            backup = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
            path.replace(backup)
            log.warning("Corrupt settings moved to %s", backup)
        except OSError as move_exc:
            log.warning("Could not move corrupt settings file: %s", move_exc)
        return Settings()
    return Settings.from_dict(data)


def save_settings(path: Path, settings: Settings) -> None:
    """Persist settings atomically.  Raises OSError on failure."""
    atomic_write_text(path, json.dumps(settings.to_dict(), indent=2))
