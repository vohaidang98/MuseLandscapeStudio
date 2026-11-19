"""Cổng kích hoạt + cập nhật LAN cho bản Windows (Muse Landscape Studio).

- ensure_activated(): bắt buộc nhập đúng mã kích hoạt (chữ hiện dấu *) mới dùng được app.
- check_update(manual): đọc version.json trong thư mục cập nhật LAN, kiểm tra SHA-256, chạy bộ cài im lặng.
"""
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import app_licensing as licensing
import app_updater as updater

APP = 'MuseLandscapeStudio'
TITLE = 'Muse Landscape Studio'
APP_VERSION = '1.3.2'


def _root():
    root = tk.Tk()
    root.title(TITLE)
    root.geometry('1x1+-3000+-3000')
    root.attributes('-topmost', True)
    root.update()
    return root


def ensure_activated():
    """True nếu đã kích hoạt (sẵn có hoặc vừa nhập đúng mã); False nếu người dùng thoát."""
    if licensing.is_activated():
        return True
    root = _root()
    ok = False
    try:
        while True:
            code = simpledialog.askstring('Kích hoạt ' + TITLE, 'Nhập mã kích hoạt để sử dụng ' + TITLE + ':',
                                          show='*', parent=root)
            if code is None:
                break
            if licensing.activate(code):
                ok = True
                break
            messagebox.showwarning(TITLE, 'Mã không đúng. Hãy thử lại.', parent=root)
    finally:
        root.destroy()
    return ok


def check_update(manual):
    """Trả về True nếu đã chạy bộ cài (app phải thoát ngay để bộ cài thay file)."""
    if not licensing.is_activated():
        return False
    folder = updater.get_folder(APP)
    root = None
    try:
        if not folder:
            if not manual:
                return False
            root = _root()
            folder = filedialog.askdirectory(parent=root, title='Chọn thư mục cập nhật (trên mạng LAN)')
            if not folder:
                return False
            updater.set_folder(APP, folder)
        info = updater.check_latest(folder, APP_VERSION)
        if not info:
            if manual:
                root = root or _root()
                messagebox.showinfo(TITLE, f'Bạn đang dùng bản mới nhất ({APP_VERSION}).', parent=root)
            return False
        root = root or _root()
        notes = str(info.get('notes', '')).strip()[:600]
        if not messagebox.askyesno(TITLE, f'Có bản mới {info["version"]} (đang dùng {APP_VERSION}).\n\n{notes}\n\n'
                                          'Cập nhật ngay? Ứng dụng sẽ đóng để cài đặt.', parent=root):
            return False
        path = updater.download(info)
        updater.install(path)
        return True
    except Exception as exc:
        if manual:
            root = root or _root()
            messagebox.showerror(TITLE, f'Không cập nhật được:\n{exc}', parent=root)
            if messagebox.askyesno(TITLE, 'Chọn lại thư mục cập nhật?', parent=root):
                updater.set_folder(APP, '')
        return False
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
