@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Olivia agent...
echo Open http://127.0.0.1:8765 in your browser.
echo Press Ctrl+C to stop.
python server.py
pause
