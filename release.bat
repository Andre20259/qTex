@echo off
rem Make a release:  release.bat 1.2.0   (or double-click and type the version)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0release.ps1" %*
echo.
pause
