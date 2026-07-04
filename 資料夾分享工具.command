#!/bin/bash
# 雙擊我即可啟動「資料夾分享工具」的圖形視窗模式（不用打字）。
# 本檔案需與 foldertext.py 放在同一個資料夾。
cd "$(dirname "$0")" || exit 1

# 依序嘗試 python3 / python，找到可用的就啟動
if command -v python3 >/dev/null 2>&1; then
    python3 foldertext.py gui
elif command -v python >/dev/null 2>&1; then
    python foldertext.py gui
else
    osascript -e 'display dialog "找不到 Python，請先安裝 Python 3。" buttons {"好"} default button "好"'
fi
