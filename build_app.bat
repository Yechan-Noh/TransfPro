@echo off
REM Build TransfPro.exe for Windows
REM
REM Prerequisites:
REM   pip install pyinstaller
REM
REM Usage:
REM   cd transfpro
REM   build_app.bat

echo ================================================
echo   Building TransfPro for Windows
echo ================================================

REM Check pyinstaller
where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
)

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build
echo Running PyInstaller...
pyinstaller transfpro_win.spec --noconfirm

if exist "dist\TransfPro\TransfPro.exe" (
    echo.
    echo ================================================
    echo   Build successful!
    echo   Executable: dist\TransfPro\TransfPro.exe
    echo ================================================
    echo.
    echo To create an installer, install NSIS and run:
    echo   makensis installer.nsi
    echo.
) else (
    echo ERROR: Build failed. Check output above.
    exit /b 1
)
