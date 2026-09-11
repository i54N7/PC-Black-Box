@echo off
setlocal EnableExtensions
title PC Black Box V7.1 Builder

echo.
echo ==================================================
echo   PC BLACK BOX V7.1
echo   Elevated Hardware Bridge Task Support
echo   Existing versions will NOT be deleted
echo ==================================================
echo.

cd /d "%~dp0"

if not exist "pc_black_box_v7_1.py" (
    echo [ERROR] pc_black_box_v7_1.py not found.
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

if not exist "Setup_Hardware_Bridge_Admin.bat" (
    echo [ERROR] Setup_Hardware_Bridge_Admin.bat not found.
    pause
    exit /b 4
)

if not exist "Setup_Hardware_Bridge_Admin.ps1" (
    echo [ERROR] Setup_Hardware_Bridge_Admin.ps1 not found.
    pause
    exit /b 5
)

echo [CHECK] Testing Python source...
python -m py_compile "pc_black_box_v7_1.py"
if errorlevel 1 (
    echo [ERROR] Python syntax check failed.
    pause
    exit /b 6
)

echo [BUILD] Building V7.1...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "PC_Black_Box" ^
  --icon "%~dp0PC_Black_Box_NEW.ico" ^
  --add-data "%~dp0PC_Black_Box_NEW.ico;." ^
  --distpath "%~dp0dist_v7_1" ^
  --workpath "%~dp0build_v7_1" ^
  --specpath "%~dp0spec_v7_1" ^
  "%~dp0pc_black_box_v7_1.py"

if errorlevel 1 (
    echo [ERROR] EXE build failed.
    pause
    exit /b 7
)

if not exist "PC_Black_Box_V7_1_Test" mkdir "PC_Black_Box_V7_1_Test"

copy /y "dist_v7_1\PC_Black_Box.exe" "PC_Black_Box_V7_1_Test\PC_Black_Box.exe" >nul
xcopy /e /i /y "HardwareBridgeRuntime" "PC_Black_Box_V7_1_Test\HardwareBridgeRuntime" >nul
copy /y "PC_Black_Box_NEW.ico" "PC_Black_Box_V7_1_Test\PC_Black_Box_NEW.ico" >nul
copy /y "Setup_Hardware_Bridge_Admin.bat" "PC_Black_Box_V7_1_Test\Setup_Hardware_Bridge_Admin.bat" >nul
copy /y "Setup_Hardware_Bridge_Admin.ps1" "PC_Black_Box_V7_1_Test\Setup_Hardware_Bridge_Admin.ps1" >nul
if exist "requirements.txt" copy /y "requirements.txt" "PC_Black_Box_V7_1_Test\requirements.txt" >nul

echo.
echo ==================================================
echo [SUCCESS] PC BLACK BOX V7.1 test build created:
echo   %~dp0PC_Black_Box_V7_1_Test\PC_Black_Box.exe
echo.
echo IMPORTANT:
echo   Run Setup_Hardware_Bridge_Admin.bat ONCE from
echo   inside PC_Black_Box_V7_1_Test before testing.
echo.
echo Existing V7.0 files were NOT deleted.
echo ==================================================
echo.
pause
