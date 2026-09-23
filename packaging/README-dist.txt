IP Monitor - portable Windows build
====================================

Run:      double-click IPMonitor.exe   (no installation, no Python needed)

First launch on a new PC: Windows SmartScreen may show "Windows protected your
PC" because the executable is not code-signed.  Click "More info" and then
"Run anyway".  Do not disable SmartScreen or Defender.

Your data (settings, logs, saved target lists, exports) is stored in:
    %LOCALAPPDATA%\IPMonitor\
Portable mode: create an empty file named "portable.txt" next to
IPMonitor.exe and the data folder "data\" will be used instead (only if
that folder is writable, e.g. a USB stick).

Documentation: see docs\ (USAGE.md, TROUBLESHOOTING.md).
