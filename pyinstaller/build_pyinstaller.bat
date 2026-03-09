@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 build_pyinstaller.py %*
) else (
    python build_pyinstaller.py %*
)

set EXIT_CODE=%errorlevel%
if not %EXIT_CODE%==0 (
    echo PyInstaller build failed.
    exit /b %EXIT_CODE%
)

echo PyInstaller build complete.
exit /b 0

