@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM  MediaNexus installer build script
REM  Steps: 1) PyInstaller -> onedir bundle   2) Inno Setup -> setup wizard
REM  Prereq: pip install -r requirements.txt  AND  Inno Setup 6 installed
REM  Output: dist\installer\MediaNexus-Setup.exe
REM  Run this file from the project ROOT directory.
REM ============================================================================

set "INNO_DIR=C:\Program Files (x86)\Inno Setup 6"
if not exist "%INNO_DIR%\ISCC.exe" set "INNO_DIR=C:\Program Files\Inno Setup 6"
if not exist "%INNO_DIR%\ISCC.exe" (
    echo [ERROR] Inno Setup compiler ISCC.exe not found.
    echo         Please install Inno Setup 6 first: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

echo [1/2] Running PyInstaller (first run may be slow, please wait)...
python -m PyInstaller MediaNexus.spec --clean --noconfirm
if not !errorlevel! == 0 (
    echo [FAIL] PyInstaller error. Please run first: pip install -r requirements.txt
    pause
    exit /b 1
)
if not exist "dist\MediaNexus\MediaNexus.exe" (
    echo [FAIL] dist\MediaNexus\MediaNexus.exe not generated. Check MediaNexus.spec
    pause
    exit /b 1
)
echo        Generated dist\MediaNexus\MediaNexus.exe

echo [2/2] Compiling installer with Inno Setup...
"%INNO_DIR%\ISCC.exe" "installer\MediaNexus-Setup.iss"
if !errorlevel! == 0 (
    echo.
    echo [OK] Installer generated: dist\installer\MediaNexus-Setup.exe
    echo      Users can pick install location and toggle desktop/quick-launch icons.
) else (
    echo.
    echo [FAIL] Inno Setup compile error. Check installer\MediaNexus-Setup.iss
)
echo.
pause
