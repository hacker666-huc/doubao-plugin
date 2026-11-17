@echo off
cd /d "%~dp0"
echo ==========================================
echo  Doubao Purge - one-shot inject pack v2
echo ==========================================
where python >nul 2>nul
if errorlevel 1 (
  echo [ERR] python not found. Install Python 3.8+ first.
  pause
  exit /b 1
)
echo [1/2] install skill pack...
python install.py
if errorlevel 1 (
  echo [ERR] install.py failed
  pause
  exit /b 1
)
echo.
echo [2/2] inject preference + behavior probe (restarts Doubao)...
python inject_preference.py
echo.
echo Done. Switch Doubao to Work Task mode.
echo Verify: ask it to write a Python CSV null-counter script;
echo first block should be real code.
pause
