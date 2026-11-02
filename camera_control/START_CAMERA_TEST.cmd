@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv-camera\Scripts\python.exe" (
  echo Run camera_control\scripts\setup_windows.ps1 first.
  echo See camera_control\PC_CAMERA_TEST_JA.md.
  pause
  exit /b 1
)
echo USB camera test. All control outputs are simulated on screen.
echo Open http://127.0.0.1:8000 in Chrome or Edge after startup.
echo Stop this window with Ctrl+C.
if exist "camera_control\camera-test.local.json" (
  echo Using saved camera_control\camera-test.local.json
  ".venv-camera\Scripts\python.exe" -m camera_control.camera_test --config "camera_control\camera-test.local.json"
) else (
  choice /c 0123 /n /m "Camera number [0,1,2,3] - try 0 first: "
  if errorlevel 4 (set CAMERA_DEVICE=3) else if errorlevel 3 (set CAMERA_DEVICE=2) else if errorlevel 2 (set CAMERA_DEVICE=1) else (set CAMERA_DEVICE=0)
  call :run_camera
)
pause
exit /b
:run_camera
".venv-camera\Scripts\python.exe" -m camera_control.camera_test --device %CAMERA_DEVICE%
exit /b
