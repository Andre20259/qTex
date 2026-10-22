@echo off
rem Double-click to build QTeX (runs build.ps1 without changing your PowerShell policy).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
echo.
pause
