@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM  MediaSync packaging script (onedir folder, no install wizard)
REM  Prereq: pip install -r requirements.txt
REM  Output: dist\MediaSync\  (folder with MediaSync.exe + DLLs + assets/docs)
REM  For the installer wizard (choose location / shortcuts), use:
REM      installer\build-installer.bat
REM  Run this file from the project ROOT directory.
REM ============================================================================

echo [1/1] Running PyInstaller (first run may be slow, please wait)...
python -m PyInstaller ProjectSync_Studio.spec --clean --noconfirm
if !errorlevel! == 0 (
    echo.
    echo [OK] Generated folder: dist\MediaSync\
    echo      Run dist\MediaSync\MediaSync.exe to launch.
    echo      For the installer wizard, run: installer\build-installer.bat
) else (
    echo.
    echo [FAIL] Packaging error. Please run first: pip install -r requirements.txt
)
echo.
pause
