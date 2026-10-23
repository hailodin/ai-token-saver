@echo off
REM Double-clickable Windows launcher - opens a console and runs the PowerShell installer/start script.
cd /d "%~dp0"
title Token Saver
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-windows.ps1"
if errorlevel 1 pause
