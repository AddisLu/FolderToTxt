#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
foldertext.py  --  把一個資料夾打包成一整串文字，或把文字還原成資料夾。

用途：方便透過 codeshare / pastebin 這類「純文字」平台分享整個軟體專案。

相容 Python 3.8.10（未使用 3.9+ 語法）。單一檔案、零第三方套件。

範例：
    # 1) 打包資料夾 -> 文字檔
    python foldertext.py pack  ./my_project -o project.txt

    # 打包並直接印到畫面（可手動複製）
    python foldertext.py pack  ./my_project

    # 2) 還原文字 -> 資料夾
    python foldertext.py unpack project.txt -o ./restored

    # 從剪貼簿/stdin 讀入還原（例如貼上 codeshare 內容）
    pbpaste | python foldertext.py unpack -o ./restored

說明：
    - 文字檔（UTF-8 可解碼）會以原文保存，肉眼可讀。
    - 二進位檔（圖片、執行檔…）會自動以 base64 保存。
    - 內容用「長度前綴」記錄，因此檔案內含任何字元（含分隔線）都不會出錯。
    - 每個檔案附帶 sha256 摘要，還原時會自動驗證完整性。
"""

import argparse
import base64
import hashlib
import os
import sys

MAGIC = "FOLDERTEXT v1"
MARK_FILE = ">>> FILE "
MARK_DIR = ">>> DIR  "

# 預設忽略的檔名 / 資料夾名（可用 --no-default-ignore 關閉）
DEFAULT_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".egg-info",
}
DEFAULT_IGNORE_FILES = {".DS_Store", "Thumbs.db"}
DEFAULT_IGNORE_SUFFIX = (".pyc", ".pyo")


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _should_ignore_dir(name, use_default):
    if not use_default:
        return False
    return name in DEFAULT_IGNORE_DIRS


def _should_ignore_file(name, use_default):
    if not use_default:
        return False
    if name in DEFAULT_IGNORE_FILES:
        return True
    for suf in DEFAULT_IGNORE_SUFFIX:
        if name.endswith(suf):
            return True
    return False


def pack(root, use_default_ignore=True):
    """把 root 資料夾走訪一遍，回傳整串文字。"""
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise SystemExit("錯誤：'%s' 不是資料夾。" % root)

    base_name = os.path.basename(root.rstrip(os.sep)) or "root"
    out = []
    out.append(MAGIC)
    out.append("# root: %s" % base_name)
    out.append("")

    file_count = 0
    dir_count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # 就地過濾要忽略的子資料夾（影響 os.walk 後續走訪）
        dirnames[:] = sorted(
            d for d in dirnames if not _should_ignore_dir(d, use_default_ignore)
        )
        filenames = sorted(
            f for f in filenames if not _should_ignore_file(f, use_default_ignore)
        )

        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")

        # 記錄空資料夾，還原時才能重建
        if rel_dir and not filenames and not dirnames:
            out.append("%s%s" % (MARK_DIR, rel_dir))
            dir_count += 1

        for fn in filenames:
            abs_path = os.path.join(dirpath, fn)
            rel_path = fn if not rel_dir else "%s/%s" % (rel_dir, fn)

            # 跳過符號連結指向不存在的檔案等狀況
            try:
                with open(abs_path, "rb") as fh:
                    data = fh.read()
            except (OSError, IOError) as e:
                sys.stderr.write("略過（讀取失敗）：%s (%s)\n" % (rel_path, e))
                continue

            digest = _sha256_bytes(data)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None

            # 含 \r 的文字檔改用 base64：base64 payload 是純 ASCII 單行，
            # 不會被 codeplatform 的換行正規化更動，才能保證完整還原。
            if text is not None and "\r" not in text:
                enc = "text"
                payload = text
            else:
                enc = "b64"
                payload = base64.b64encode(data).decode("ascii")

            header = "%s%s | %s | %s | %d" % (
                MARK_FILE, rel_path, enc, digest, len(payload)
            )
            out.append(header)
            out.append(payload)
            file_count += 1

    sys.stderr.write("已打包 %d 個檔案、%d 個空資料夾。\n" % (file_count, dir_count))
    # 用 \n 串接；payload 已經是完整字串，長度前綴保證解析正確
    return "\n".join(out) + "\n"


def unpack(content, out_dir):
    """把整串文字還原成資料夾（寫到 out_dir 底下）。"""
    if MAGIC not in content:
        raise SystemExit("錯誤：找不到 '%s' 標頭，這不是有效的打包文字。" % MAGIC)

    # 正規化換行，避免 codeshare 平台把 \n 變成 \r\n 造成長度誤差
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    file_count = 0
    dir_count = 0
    pos = 0
    n = len(content)

    while True:
        i_file = content.find(MARK_FILE, pos)
        i_dir = content.find(MARK_DIR, pos)

        # 找出下一個標記（誰的位置比較前面）
        candidates = [x for x in (i_file, i_dir) if x != -1]
        if not candidates:
            break
        nxt = min(candidates)

        nl = content.find("\n", nxt)
        if nl == -1:
            nl = n
        header = content[nxt:nl]

        if header.startswith(MARK_DIR):
            rel = header[len(MARK_DIR):].strip()
            target = _safe_join(out_dir, rel)
            os.makedirs(target, exist_ok=True)
            dir_count += 1
            pos = nl + 1
            continue

        # MARK_FILE：格式 = ">>> FILE <path> | <enc> | <sha256> | <len>"
        meta = header[len(MARK_FILE):]
        try:
            rest, length_s = meta.rsplit(" | ", 1)
            rest, digest = rest.rsplit(" | ", 1)
            rel_path, enc = rest.rsplit(" | ", 1)
            length = int(length_s)
        except ValueError:
            raise SystemExit("錯誤：無法解析標頭：%s" % header)

        payload_start = nl + 1
        payload = content[payload_start:payload_start + length]

        if enc == "text":
            data = payload.encode("utf-8")
        elif enc == "b64":
            data = base64.b64decode(payload.encode("ascii"))
        else:
            raise SystemExit("錯誤：未知編碼 '%s'（檔案 %s）" % (enc, rel_path))

        actual = _sha256_bytes(data)
        if actual != digest:
            sys.stderr.write(
                "警告：%s 摘要不符（內容可能在傳輸中被更動）。\n" % rel_path
            )

        target = _safe_join(out_dir, rel_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(data)
        file_count += 1

        pos = payload_start + length

    sys.stderr.write("已還原 %d 個檔案、%d 個資料夾 -> %s\n"
                     % (file_count, dir_count, out_dir))


def _safe_join(base, rel):
    """安全地把相對路徑接到 base 底下，防止 ../ 逃出目標資料夾。"""
    rel = rel.replace("/", os.sep)
    target = os.path.normpath(os.path.join(base, rel))
    base_norm = os.path.normpath(base)
    if target != base_norm and not target.startswith(base_norm + os.sep):
        raise SystemExit("錯誤：不安全的路徑（試圖逃出目標資料夾）：%s" % rel)
    return target


def _read_input(path):
    if path in (None, "-"):
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write_output(text, path):
    if path in (None, "-"):
        sys.stdout.write(text)
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        sys.stderr.write("已寫出：%s\n" % os.path.abspath(path))


# ----------------------------------------------------------------------------
# GUI 模式（macOS）：全程用彈出視窗操作，剪貼簿自動化，完全不用打字。
# ----------------------------------------------------------------------------
import subprocess


def _osa(script):
    """執行一段 AppleScript，回傳 stdout（去除尾端換行）。使用者按取消 -> None。"""
    try:
        out = subprocess.check_output(
            ["osascript", "-e", script], stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").rstrip("\n")
    except subprocess.CalledProcessError:
        return None  # 使用者取消或發生錯誤


def _gui_choose_button(text, buttons, title="資料夾分享工具"):
    quoted = ", ".join('"%s"' % b for b in buttons)
    script = (
        'button returned of (display dialog "%s" '
        'with title "%s" buttons {%s} default button "%s")'
        % (text.replace('"', '\\"'), title, quoted, buttons[-1])
    )
    return _osa(script)


def _gui_choose_folder(prompt):
    return _osa('POSIX path of (choose folder with prompt "%s")' % prompt)


def _gui_choose_file(prompt):
    return _osa('POSIX path of (choose file with prompt "%s")' % prompt)


def _gui_info(text, title="資料夾分享工具"):
    _osa('display dialog "%s" with title "%s" buttons {"好"} default button "好"'
         % (text.replace('"', '\\"'), title))


def _clipboard_set(text):
    """把文字放進系統剪貼簿（跨平台）。"""
    if sys.platform == "darwin":
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
        return
    if sys.platform == "win32":
        # 用暫存檔 + PowerShell Set-Clipboard，可靠處理中文與大量文字，
        # 且離開程式後剪貼簿內容仍保留（tkinter 在 Windows 上會遺失）。
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        safe = tmp.replace("'", "''")
        cmd = ("Get-Content -LiteralPath '%s' -Raw -Encoding UTF8 "
               "| Set-Clipboard" % safe)
        try:
            subprocess.check_call(["powershell", "-NoProfile", "-Command", cmd])
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return
    # Linux / 其他：Wayland 的 wl-copy -> X11 的 xclip -> xsel
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"]):
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            if p.returncode == 0:
                return
        except OSError:
            continue
    raise RuntimeError(
        "找不到可用的剪貼簿工具（請安裝 wl-clipboard、xclip 或 xsel 其中之一）。")


def _clipboard_get():
    """讀取系統剪貼簿文字（跨平台）。"""
    if sys.platform == "darwin":
        return subprocess.check_output(["pbpaste"]).decode("utf-8")
    if sys.platform == "win32":
        out = subprocess.check_output([
            "powershell", "-NoProfile", "-Command",
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw",
        ])
        return out.decode("utf-8")
    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"]):
        try:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8")
        except (OSError, subprocess.CalledProcessError):
            continue
    return ""


def _open_in_file_manager(path):
    """在系統檔案總管/Finder 打開資料夾（跨平台）。"""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def run_gui():
    """依平台選擇 GUI：macOS 用原生對話框，其他平台用 tkinter。"""
    if sys.platform == "darwin":
        return _run_gui_macos()
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "找不到 tkinter，無法啟動圖形介面。\n"
            "請改用指令：\n"
            "  python foldertext.py pack <資料夾> -o out.txt\n"
            "  python foldertext.py unpack out.txt -o <還原位置>\n"
        )
        return 1
    return _run_gui_tk()


def _run_gui_macos():
    action = _gui_choose_button(
        "要做什麼？\n\n"
        "• 打包分享：選一個資料夾，打包成文字並自動複製到剪貼簿，\n"
        "  接著到 codeshare 貼上即可。\n\n"
        "• 還原資料夾：先在 codeshare 複製整段文字，本工具會自動讀取剪貼簿還原。",
        ["還原資料夾", "打包分享"],
    )
    if action is None:
        return 0  # 取消

    if action == "打包分享":
        folder = _gui_choose_folder("選擇要打包分享的資料夾")
        if not folder:
            return 0
        folder = folder.rstrip("/")
        text = pack(folder, use_default_ignore=True)
        _clipboard_set(text)
        # 順手在桌面留一份 .txt 備份
        desktop = os.path.expanduser("~/Desktop")
        name = os.path.basename(folder) or "folder"
        backup = os.path.join(desktop, "%s.分享.txt" % name)
        try:
            with open(backup, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            backup_note = "\n（另存了一份備份：桌面/%s）" % os.path.basename(backup)
        except OSError:
            backup_note = ""
        open_cs = _gui_choose_button(
            "✅ 打包完成！文字已複製到剪貼簿。\n\n"
            "共 %d 個字元。%s\n\n"
            "要現在打開 codeshare.io 貼上嗎？" % (len(text), backup_note),
            ["先不用", "打開 codeshare"],
        )
        if open_cs == "打開 codeshare":
            subprocess.Popen(["open", "https://codeshare.io/"])
        return 0

    if action == "還原資料夾":
        content = _clipboard_get()
        if MAGIC not in content:
            src = _gui_choose_button(
                "剪貼簿裡沒有偵測到打包文字。\n要改從文字檔還原嗎？",
                ["取消", "選文字檔"],
            )
            if src != "選文字檔":
                return 0
            path = _gui_choose_file("選擇打包好的文字檔")
            if not path:
                return 0
            content = _read_input(path)
        dest = _gui_choose_folder("選擇要「還原到哪個資料夾底下」")
        if not dest:
            return 0
        # 用打包時記錄的 root 名稱建立子資料夾，避免檔案散落
        root_name = "unpacked"
        for line in content.splitlines():
            if line.startswith("# root:"):
                root_name = line.split(":", 1)[1].strip() or root_name
                break
        out_dir = os.path.join(dest.rstrip("/"), root_name)
        unpack(content, out_dir)
        subprocess.Popen(["open", out_dir])  # 在 Finder 打開結果
        _gui_info("✅ 還原完成！已在 Finder 打開：\n%s" % out_dir)
        return 0

    return 0


def _run_gui_tk():
    """tkinter 版圖形介面（Windows / Linux 通用，Python 內建，無需安裝）。"""
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()  # 隱藏主視窗，只用它當對話框的母體與剪貼簿存取

    # ---- 主選單（兩顆大按鈕）----
    action = {"v": None}
    win = tk.Toplevel(root)
    win.title("資料夾分享工具")
    win.resizable(False, False)
    tk.Label(win, text="資料夾分享工具", font=("", 16, "bold")).pack(padx=24, pady=(18, 4))
    tk.Label(win, text="請選擇要進行的動作").pack(pady=(0, 8))

    def _choose(v):
        action["v"] = v
        win.destroy()

    tk.Button(win, text="📦  打包分享\n資料夾 → 文字（自動複製到剪貼簿）",
              width=40, height=3, command=lambda: _choose("pack")).pack(padx=24, pady=6)
    tk.Button(win, text="📂  還原資料夾\n剪貼簿或文字檔 → 資料夾",
              width=40, height=3, command=lambda: _choose("unpack")).pack(padx=24, pady=6)
    tk.Label(win, text="").pack(pady=2)
    win.protocol("WM_DELETE_WINDOW", lambda: _choose(None))
    win.update_idletasks()
    root.wait_window(win)

    act = action["v"]
    try:
        if act == "pack":
            folder = filedialog.askdirectory(title="選擇要打包分享的資料夾")
            if not folder:
                return 0
            folder = folder.rstrip("/\\")
            text = pack(folder, use_default_ignore=True)

            try:
                _clipboard_set(text)
                clip_ok = True
            except Exception:
                clip_ok = False

            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.isdir(desktop):
                desktop = os.path.expanduser("~")
            name = os.path.basename(folder) or "folder"
            backup = os.path.join(desktop, "%s.分享.txt" % name)
            try:
                with open(backup, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
                backup_note = "\n同時存了一份到：\n%s" % backup
            except OSError:
                backup = None
                backup_note = ""

            msg = (("✅ 打包完成，文字已複製到剪貼簿！\n"
                    if clip_ok else
                    "✅ 打包完成！（剪貼簿複製失敗，請開下方檔案手動複製）\n")
                   + "共 %d 個字元。%s\n\n要現在打開 codeshare.io 貼上嗎？"
                   % (len(text), backup_note))
            if messagebox.askyesno("完成", msg):
                import webbrowser
                webbrowser.open("https://codeshare.io/")
            elif backup and not clip_ok:
                _open_in_file_manager(os.path.dirname(backup))
            return 0

        if act == "unpack":
            try:
                content = _clipboard_get()  # 原生工具（含 Wayland wl-paste）
            except Exception:
                content = ""
            if MAGIC not in content:
                try:
                    content = root.clipboard_get()  # 後備：tkinter 剪貼簿
                except Exception:
                    pass
            if MAGIC not in content:
                if messagebox.askyesno(
                    "找不到內容",
                    "剪貼簿裡沒有偵測到打包文字。\n要改從文字檔還原嗎？",
                ):
                    path = filedialog.askopenfilename(
                        title="選擇打包好的文字檔",
                        filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")],
                    )
                    if not path:
                        return 0
                    content = _read_input(path)
                else:
                    return 0

            dest = filedialog.askdirectory(title="選擇要「還原到哪個資料夾底下」")
            if not dest:
                return 0

            root_name = "unpacked"
            for line in content.splitlines():
                if line.startswith("# root:"):
                    root_name = line.split(":", 1)[1].strip() or root_name
                    break
            out_dir = os.path.join(dest.rstrip("/\\"), root_name)
            unpack(content, out_dir)
            _open_in_file_manager(out_dir)
            messagebox.showinfo("完成", "✅ 還原完成！\n%s" % out_dir)
            return 0

        return 0
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="foldertext.py",
        description="把資料夾打包成一整串文字，或把文字還原成資料夾。",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_pack = sub.add_parser("pack", help="資料夾 -> 文字")
    p_pack.add_argument("folder", help="要打包的資料夾")
    p_pack.add_argument("-o", "--output", default="-",
                        help="輸出檔（預設印到畫面 stdout）")
    p_pack.add_argument("--no-default-ignore", action="store_true",
                        help="不要自動忽略 .git / __pycache__ / node_modules 等")

    p_unpack = sub.add_parser("unpack", help="文字 -> 資料夾")
    p_unpack.add_argument("input", nargs="?", default="-",
                          help="輸入文字檔（預設從 stdin 讀取）")
    p_unpack.add_argument("-o", "--output", default="./unpacked",
                          help="還原到哪個資料夾（預設 ./unpacked）")

    sub.add_parser("gui", help="圖形視窗模式（macOS，全程不用打字）")

    args = parser.parse_args(argv)

    # 沒給任何子指令時（例如在 Finder 雙擊啟動），預設進 GUI 模式
    if args.cmd is None:
        return run_gui()

    if args.cmd == "pack":
        text = pack(args.folder, use_default_ignore=not args.no_default_ignore)
        _write_output(text, args.output)
    elif args.cmd == "unpack":
        content = _read_input(args.input)
        unpack(content, args.output)
    elif args.cmd == "gui":
        return run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
