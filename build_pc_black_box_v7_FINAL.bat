@echo off
setlocal EnableExtensions
title PC Black Box V7.0 FINAL Builder

echo.
echo ==================================================
echo   PC BLACK BOX V7.0 - FINAL BUILD
echo   New dashboard + runtime icon + themes + ESP32
echo   Existing project files will NOT be deleted
echo ==================================================
echo.

cd /d "%~dp0"

if not exist "pc_black_box_v7_FINAL.py" (
    echo [ERROR] pc_black_box_v7_FINAL.py not found.
    pause
    exit /b 1
)

if not exist "PC_Black_Box_NEW.ico" (
    echo [ERROR] PC_Black_Box_NEW.ico not found.
    pause
    exit /b 2
)

if not exist "HardwareBridgeRuntime\HardwareBridge.exe" (
    echo [ERROR] HardwareBridgeRuntime\HardwareBridge.exe not found.
    pause
    exit /b 3
)

echo [CHECK] Testing Python source...
python -m py_compile "pc_black_box_v7_FINAL.py"
if errorlevel 1 (
    echo [ERROR] Python source check failed.
    pause
    exit /b 4
)

python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INSTALL] Installing PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller install failed.
        pause
        exit /b 5
    )
)

echo [BUILD] Building PC Black Box V7.0...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "PC_Black_Box" ^
  --icon "%~dp0PC_Black_Box_NEW.ico" ^
  --add-data "%~dp0PC_Black_Box_NEW.ico;." ^
  --distpath "%~dp0dist_v7_final" ^
  --workpath "%~dp0build_v7_final" ^
  --specpath "%~dp0spec_v7_final" ^
  "%~dp0pc_black_box_v7_FINAL.py"

if errorlevel 1 (
    echo.
    echo [ERROR] EXE build failed.
    pause
    exit /b 6
)

if not exist "PC_Black_Box_Final" mkdir "PC_Black_Box_Final"

copy /y "dist_v7_final\PC_Black_Box.exe" "PC_Black_Box_Final\PC_Black_Box.exe" >nul
if errorlevel 1 (
    echo [ERROR] Could not copy PC_Black_Box.exe.
    echo Close any running copy inside PC_Black_Box_Final and run this builder again.
    pause
    exit /b 7
)

xcopy /e /i /y "HardwareBridgeRuntime" "PC_Black_Box_Final\HardwareBridgeRuntime" >nul
if errorlevel 1 (
    echo [ERROR] Could not copy HardwareBridgeRuntime.
    pause
    exit /b 8
)

copy /y "PC_Black_Box_NEW.ico" "PC_Black_Box_Final\PC_Black_Box_NEW.ico" >nul
if exist "requirements.txt" copy /y "requirements.txt" "PC_Black_Box_Final\requirements.txt" >nul

echo.
echo ==================================================
echo [SUCCESS] PC BLACK BOX V7.0 FINAL created:
echo   %~dp0PC_Black_Box_Final\PC_Black_Box.exe
echo.
echo Existing old versions were NOT deleted.
echo ==================================================
echo.
pause
