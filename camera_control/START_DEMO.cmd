@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv-camera\Scripts\python.exe" (
  echo Run setup_windows.ps1 first. See START_HERE_WIN10_JA.md.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8000 in your browser after startup.
echo Stop with Ctrl+C in this window.
".venv-camera\Scripts\python.exe" -m camera_control.app --mode demo
pause
