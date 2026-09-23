"""Application (diagnostic) logging.

This is *not* the per-probe CSV log; see :mod:`ip_monitor.csvlog` for that.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"


def configure_logging(log_file: Path | None, level: int = logging.INFO) -> None:
    """Configure the root logger with a rotating file handler.

    The file handler is thread-safe (``logging`` serialises handler calls with a
    lock).  A stderr handler is added only when a console is attached, which is
    never the case for a ``.pyw`` or a windowed executable.
    """
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    formatter = logging.Formatter(LOG_FORMAT)

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as exc:  # pragma: no cover - depends on filesystem
            sys.stderr.write(f"Cannot open log file {log_file}: {exc}\n")

    if sys.stderr is not None and getattr(sys.stderr, "isatty", lambda: False)():
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    if not root.handlers:
        root.addHandler(logging.NullHandler())

    # Keep matplotlib's chatter out of the log.
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
