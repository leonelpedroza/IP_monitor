# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for IP Monitor.

    pyinstaller packaging/IPMonitor.spec --noconfirm --clean

Set IPMONITOR_ONEFILE=1 in the environment to build a single-file executable
instead of the default (recommended) one-folder build.
"""

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH is injected by PyInstaller
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / "packaging"))

from ip_monitor.version import APP_ID  # noqa: E402
import make_version_info  # noqa: E402

ONEFILE = os.environ.get("IPMONITOR_ONEFILE", "0") == "1"

version_file = ROOT / "build" / "version_info.txt"
version_file.parent.mkdir(parents=True, exist_ok=True)
version_file.write_text(make_version_info.render(), encoding="utf-8")

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(ROOT / "assets" / "icon.png"), ".")],
    hiddenimports=[
        "ping3",
        "ping3.errors",
        "matplotlib.backends.backend_tkagg",
    ],
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["TkAgg"]}},
    runtime_hooks=[],
    excludes=[
        # Not used by IP Monitor; excluding them keeps the distribution small.
        "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "gi",
        "IPython", "jupyter", "notebook",
        "scipy", "pandas", "sympy",
        "tkinter.test", "unittest", "test", "pydoc_data", "lib2to3",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

common = dict(
    name=APP_ID,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-compressed binaries trigger more AV false positives
    console=False,  # windowed application (no console)
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "icon.ico"),
    version=str(version_file),
    manifest=str(ROOT / "packaging" / "IPMonitor.manifest"),
    uac_admin=False,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_ID)
