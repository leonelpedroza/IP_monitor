"""Generate the Windows VERSIONINFO resource for PyInstaller from version.py.

Usage:  python packaging/make_version_info.py build/version_info.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ip_monitor.version import APP_AUTHOR, APP_DESCRIPTION, APP_ID, APP_NAME, __version__, version_tuple  # noqa: E402

TEMPLATE = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vers},
    prodvers={vers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{author}'),
         StringStruct('FileDescription', '{description}'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', '{app_id}'),
         StringStruct('LegalCopyright', '{author}'),
         StringStruct('OriginalFilename', '{app_id}.exe'),
         StringStruct('ProductName', '{app_name}'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def render() -> str:
    major, minor, patch = version_tuple()
    return TEMPLATE.format(
        vers=(major, minor, patch, 0),
        version=__version__,
        author=APP_AUTHOR,
        description=APP_DESCRIPTION,
        app_id=APP_ID,
        app_name=APP_NAME,
    )


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "build" / "version_info.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    print(f"wrote {out} ({__version__})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
