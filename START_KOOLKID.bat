@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0koolkid_launcher.ps1" -Action Start
if errorlevel 1 (
  echo.
  echo KOOLKID startup did not complete. Review the visible server windows above.
  pause
)
endlocal
