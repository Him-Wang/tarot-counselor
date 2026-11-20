@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  start "" /B py -3 server.py
) else (
  start "" /B pythonw.exe server.py
)
exit /b 0
