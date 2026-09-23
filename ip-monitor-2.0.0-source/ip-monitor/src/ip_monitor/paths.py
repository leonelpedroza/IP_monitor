"""Location of writable user data.

The executable directory is never assumed to be writable.  By default all
user data goes to ``%LOCALAPPDATA%\\IPMonitor`` on Windows (``~/.local/share/
IPMonitor`` elsewhere).  A deliberate *portable mode* is enabled by placing an
empty file named ``portable.txt`` next to the executable; data then lives in
``<exe dir>\\data`` - but only if that directory is actually writable.

Layout::

    <data root>/
        config/settings.json
        logs/ip_monitor.log           application log (rotating)
        logs/ping_log_<timestamp>.csv per-session probe log
        targets/                      default folder for saved target lists
        exports/                      default folder for statistics exports
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from ip_monitor.version import APP_ID

log = logging.getLogger(__name__)

PORTABLE_MARKER = "portable.txt"


def application_dir() -> Path:
    """Directory containing the executable (frozen) or the project root (source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def default_data_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_ID
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_ID


@dataclass(frozen=True)
class AppPaths:
    root: Path
    portable: bool

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def targets_dir(self) -> Path:
        return self.root / "targets"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def app_log_file(self) -> Path:
        return self.logs_dir / "ip_monitor.log"

    def ensure(self) -> None:
        for d in (self.config_dir, self.logs_dir, self.targets_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


def resolve_paths(override: str | os.PathLike[str] | None = None) -> AppPaths:
    """Decide where user data lives.

    Order of precedence: explicit ``override`` (``--data-dir`` / tests),
    portable mode marker next to the executable, then the per-user default.
    """
    if override is not None:
        paths = AppPaths(Path(override), portable=False)
        paths.ensure()
        return paths

    app_dir = application_dir()
    if (app_dir / PORTABLE_MARKER).exists():
        candidate = app_dir / "data"
        if _is_writable_dir(candidate):
            paths = AppPaths(candidate, portable=True)
            paths.ensure()
            return paths
        log.warning("Portable marker found but %s is not writable; using per-user folder", candidate)

    paths = AppPaths(default_data_root(), portable=False)
    paths.ensure()
    return paths
