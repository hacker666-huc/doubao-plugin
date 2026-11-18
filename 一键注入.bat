@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
title Doubao Purge - One-shot Inject (v3)

echo ============================================================
echo   Doubao Purge  -  one-shot inject  v3
echo   installs skill pack + writes Work-Task preference + probes
echo ============================================================
echo   Dir: %CD%
echo.

if not exist "install.py" goto nofiles
if not exist "inject_preference.py" goto nofiles
if not exist "src\preference-instruction.txt" goto nofiles

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY goto nopython

echo [1/3] install skill pack into Doubao data dir...
%PY% install.py
if errorlevel 1 goto fail

echo.
echo [2/3] inject preference instruction (Doubao restarts once)...
%PY% inject_preference.py
if errorlevel 1 goto manual

echo.
echo [3/3] done.
echo   RESULT: PASS means injected AND behavior verified.
echo   Switch Doubao to "Work Task" mode and use it there.
echo.
echo If you see behavior=CHECK, just send a real task once:
echo   write a Python script that reads a CSV and prints per-column null counts
echo   first block should be code, no "sure / here is / for reference".
echo.
pause
exit /b 0

:manual
echo.
echo [i] auto-inject did not finish. Manual path (30 seconds):
echo     1. this script copied src\preference-instruction.txt to your clipboard
echo     2. Doubao - Settings - Work mode - Personalization - Work-task preference - Edit
echo     3. Ctrl+V, Save, then reopen a Work Task session
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Raw -Encoding UTF8 'src\preference-instruction.txt' | Set-Clipboard"
echo.
echo   (clipboard already set; if empty, open src\preference-instruction.txt and copy all)
pause
exit /b 2

:nopython
echo [x] Python 3.8+ not found.
echo     Install from https://www.python.org/downloads/  (check "Add python.exe to PATH")
pause
exit /b 1

:nofiles
echo [x] package incomplete: install.py / inject_preference.py / src\preference-instruction.txt
echo     Unzip the whole folder, do not run the bat from inside a zip preview.
pause
exit /b 1

:fail
echo.
echo [x] install.py failed. Re-run this bat; if it keeps failing:
echo     python install.py --dry-run    (shows what it would write)
pause
exit /b 1
