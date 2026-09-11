@echo off
setlocal EnableExtensions
title PC Black Box V7.1 - Hidden Hardware Bridge Setup

cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator permission for one-time setup...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

if not exist "%~dp0Setup_Hardware_Bridge_Admin_HIDDEN.ps1" (
    echo [ERROR] Setup_Hardware_Bridge_Admin_HIDDEN.ps1 not found.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup_Hardware_Bridge_Admin_HIDDEN.ps1"
