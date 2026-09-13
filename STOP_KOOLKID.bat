@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0koolkid_launcher.ps1" -Action Stop
if errorlevel 1 pause
endlocal
