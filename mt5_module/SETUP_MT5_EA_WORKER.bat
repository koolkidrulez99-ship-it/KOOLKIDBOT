@echo off
setlocal
cd /d "%~dp0"
title KOOLKID MT5 EA Worker Setup

where py >nul 2>&1
if %errorlevel%==0 (set "PY_CMD=py -3") else (set "PY_CMD=python")
%PY_CMD% -m venv "mt5_ea_worker\.venv"
if errorlevel 1 goto :fail
"mt5_ea_worker\.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"mt5_ea_worker\.venv\Scripts\python.exe" -m pip install -r "mt5_ea_worker\requirements.txt"
if errorlevel 1 goto :fail
echo EA worker setup complete.
exit /b 0

:fail
echo EA worker setup failed.
pause
exit /b 1
