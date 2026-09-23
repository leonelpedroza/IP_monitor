"""PyInstaller entry point (keeps the frozen bootstrap outside the package)."""

from ip_monitor.app import main

if __name__ == "__main__":
    raise SystemExit(main())
