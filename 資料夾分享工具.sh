#!/usr/bin/env bash
# 「資料夾分享工具」Linux 啟動器（圖形視窗，不用打字）。
# 本檔案需與 foldertext.py 放在同一個資料夾。
#
# 使用方式（擇一）：
#   A. 檔案管理員裡：右鍵 -> 內容 -> 允許以程式執行，之後雙擊選「執行」。
#   B. 終端機：./資料夾分享工具.sh
#
# 提示：Linux 的剪貼簿自動化需要下列工具之一（多數桌面已內建）：
#   Wayland: wl-clipboard   X11: xclip 或 xsel
#   若沒安裝，程式仍會把結果存成桌面的 .txt 備份。

# 切換到腳本所在資料夾（支援被 symlink 呼叫）
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
cd "$DIR" || exit 1

if command -v python3 >/dev/null 2>&1; then
    exec python3 foldertext.py gui
elif command -v python >/dev/null 2>&1; then
    exec python foldertext.py gui
else
    MSG="找不到 Python，請先安裝 Python 3（例如：sudo apt install python3 python3-tk）。"
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --text="$MSG"
    else
        echo "$MSG"
    fi
    exit 1
fi
