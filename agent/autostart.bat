@echo off
chcp 65001 >nul
cd /d "C:\Users\wbhh\Documents\deepseek-harness\default-workspace\tarot-counselor\agent"
start "" /B "C:\Users\wbhh\AppData\Local\Programs\Python\Python39\pythonw.exe" server.py
exit /b 0
