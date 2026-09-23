"""Single authoritative location for the application version and identity.

Everything else (About dialog, pyproject.toml, PyInstaller version resource,
ZIP file name) reads the version from here.
"""

__version__ = "2.0.0"

APP_NAME = "IP Monitor"
APP_ID = "IPMonitor"  # used for folder names and the executable name
APP_AUTHOR = "Leonel Pedroza"
APP_DESCRIPTION = "Lightweight real-time ICMP reachability monitor for network engineers"


def version_tuple() -> tuple[int, int, int]:
    """Return the version as a tuple of integers (major, minor, patch)."""
    parts = __version__.split("-", 1)[0].split(".")
    return tuple(int(p) for p in parts[:3])  # type: ignore[return-value]
