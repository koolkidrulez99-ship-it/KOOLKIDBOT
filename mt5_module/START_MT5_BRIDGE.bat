@echo off
setlocal
cd /d "%~dp0"
title KOOLKID Local MT5 Bridge

if not exist "mt5_bridge\.venv\Scripts\python.exe" (
  echo MT5 bridge is not set up yet.
  echo Running one-time setup now...
  call SETUP_MT5_BRIDGE.bat
  if errorlevel 1 exit /b 1
)

rem Self-heal missing Python packages (for example python-dotenv after an interrupted setup).
"mt5_bridge\.venv\Scripts\python.exe" -c "import fastapi, uvicorn, dotenv, multipart" >nul 2>&1
if errorlevel 1 (
  echo One or more bridge packages are missing. Repairing the bridge environment...
  "mt5_bridge\.venv\Scripts\python.exe" -m pip install -r "mt5_bridge\requirements.txt"
  if errorlevel 1 (
    echo.
    echo Bridge dependency repair failed. Check your internet connection and run SETUP_MT5_BRIDGE.bat again.
    pause
    exit /b 1
  )
)

echo ==============================================
echo   KOOLKID LOCAL MT5 BRIDGE
echo ==============================================
echo Local endpoint: http://127.0.0.1:8000
echo API docs:       http://127.0.0.1:8000/docs
echo.
echo LIVE-money trading is LOCKED unless you explicitly enable it in mt5_bridge\.env.
echo Keep this window open while using the real MT5 bridge.
echo.

cd /d "%~dp0mt5_bridge"
".venv\Scripts\python.exe" main.py

if errorlevel 1 (
  echo.
  echo Bridge stopped with an error.
  pause
)
