@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
title Doubao Purge - Self Check (v3)

echo ============================================================
echo   Doubao Purge  -  self check (read-only, changes nothing)
echo ============================================================
echo.

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY (
  echo [x] python not found
  pause & exit /b 1
)

echo [1] package files
for %%f in (install.py inject_preference.py src\preference-instruction.txt src\contract.md) do (
  if exist "%%f" (echo   [ok] %%f) else (echo   [x]  %%f missing)
)

echo.
echo [2] preference text length (limit 10000)
%PY% -c "p=r'src\preference-instruction.txt'; t=open(p,encoding='utf-8').read(); print('   chars =', len(t)); print('   [ok] fits' if len(t)<=10000 else '   [x] too long, trim it')"

echo.
echo [3] Doubao client
%PY% -c "import inject_preference as ip; print('   exe =', ip.find_exe(None))" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-Process Doubao -ErrorAction SilentlyContinue; if($p){'   running = yes (pid ' + ($p | ForEach-Object {$_.Id})[0] + ')'} else {'   running = no (start Doubao in Work Task mode)'}; $c=Get-NetTCPConnection -State Listen -LocalPort 9222 -ErrorAction SilentlyContinue; if($c){'   cdp 9222 = open'}else{'   cdp 9222 = closed (normal when not injecting)'}"

echo.
echo [4] how to judge (do this manually once)
echo   1. Doubao - Settings - Work mode - Personalization: preference is not empty
echo   2. Open a Work Task session, send: "who are you"
echo      pass = answers as the work contract, no "I am Doubao" identity talk
echo   3. Send: write a Python CSV null-counter script
echo      pass = first block is code, no disclaimer
echo.
pause
