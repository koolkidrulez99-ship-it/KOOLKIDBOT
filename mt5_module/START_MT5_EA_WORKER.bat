@echo off
setlocal
cd /d "%~dp0"
title KOOLKID Local MT5 EA Worker

if not exist "mt5_ea_worker\.venv\Scripts\python.exe" (
  echo MT5 EA worker is not set up yet. Running isolated setup...
  call SETUP_MT5_EA_WORKER.bat
  if errorlevel 1 exit /b 1
)

echo KOOLKID MT5 EA Worker: http://127.0.0.1:8001
echo Keep this window open while running EAs.
cd /d "%~dp0mt5_ea_worker"
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
  echo.
  echo EA worker stopped with an error.
  pause
)
