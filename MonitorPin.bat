@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM 用 pythonw 啟動（無主控台視窗）；找不到就退回 python
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "monitor_pin.py"
) else (
    python "monitor_pin.py"
)
