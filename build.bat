@echo off
REM Convenience wrapper: runs build.ps1 with the same arguments.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
exit /b %ERRORLEVEL%
