@echo off
cd /d "%~dp0"
echo Open http://localhost:8000 in your browser after the server starts.
echo Keep this window open. Press Ctrl+C to stop.
py -3 -m http.server 8000 --bind 127.0.0.1
if errorlevel 1 (
  echo Could not start. Check Python installation or whether port 8000 is in use.
  pause
)
