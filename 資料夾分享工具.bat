@echo off
chcp 65001 >nul
rem 雙擊我即可啟動「資料夾分享工具」的圖形視窗（不用打字）。
rem 本檔案需與 foldertext.py 放在同一個資料夾。
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py foldertext.py gui
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    python foldertext.py gui
    goto :eof
)

echo 找不到 Python，請先到 https://www.python.org/ 安裝 Python 3，
echo 安裝時記得勾選「Add Python to PATH」。
pause
