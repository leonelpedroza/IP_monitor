# Double-click launcher for running IP Monitor from source on Windows (no console window).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ip_monitor.app import main  # noqa: E402

raise SystemExit(main())
