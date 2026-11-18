@echo off
cd /d "%~dp0"
echo ==========================================
echo  Doubao Purge - one-shot uninstall
echo ==========================================
where python >nul 2>nul
if errorlevel 1 (
  echo [ERR] python not found. Install Python 3.8+ first.
  pause
  exit /b 1
)
echo Will remove:
echo   1. skill pack files (manifest-recorded by install.py)
echo   2. work-task preference instruction (account-level, cleared via UI automation)
echo.
set /p ok=Continue? [y/N] 
if /i not "%ok%"=="y" (
  echo Cancelled.
  pause
  exit /b 0
)
echo.
echo [1/2] removing skill pack files...
python install.py --uninstall
echo.
echo [2/2] clearing work-task preference instruction...
python uninstall_preference.py
echo.
echo Done.
echo If step 2 failed, clear it manually:
echo   Settings - Work Mode Settings - Personalization - work task preference
pause
