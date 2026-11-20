@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Olivia 奥莉薇娅 - 一键安装（全自动）
echo ============================================
echo.
echo 正在安装，无需任何操作，请稍候……
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo [失败] 安装未完成，请查看上面的错误信息。
)
echo.
echo 窗口将在 5 秒后关闭……
timeout /t 5 >nul
exit /b 0
