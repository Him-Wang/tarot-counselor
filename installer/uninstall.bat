@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Olivia 奥莉薇娅 - 一键卸载
echo ============================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
echo.
echo 窗口将在 5 秒后关闭……
timeout /t 5 >nul
exit /b 0
