@echo off
setlocal
cd /d "%~dp0"
title KOOLKID MT5 Bridge Setup

echo.
echo ==============================================
echo   KOOLKID MT5 BRIDGE - WINDOWS SETUP
echo ==============================================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  where python >nul 2>&1
  if not %errorlevel%==0 (
    echo Python was not found.
    echo Install 64-bit Python for Windows, enable "Add Python to PATH", then run this file again.
    pause
    exit /b 1
  )
  set "PY_CMD=python"
)

echo Creating isolated Python environment...
%PY_CMD% -m venv "mt5_bridge\.venv"
if errorlevel 1 goto :fail

call "mt5_bridge\.venv\Scripts\activate.bat"
echo Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo Installing KOOLKID bridge dependencies...
python -m pip install -r "mt5_bridge\requirements.txt"
if errorlevel 1 goto :fail

echo.
echo ==============================================
echo   SETUP COMPLETE
echo ==============================================
echo Next:
echo  1. Install/open MetaTrader 5 and confirm it works.
echo  2. Start with a DEMO account.
echo  3. Run START_KOOLKID_WITH_MT5_BRIDGE.bat
echo.
pause
exit /b 0

:fail
echo.
echo Setup did not complete.
echo If MetaTrader5 failed to install, confirm you are using 64-bit Windows Python.
echo Copy the error above and send it to ChatGPT if you need help.
pause
exit /b 1
