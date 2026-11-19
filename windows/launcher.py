"""Windows desktop host for the public FrameWeaver source snapshot."""
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
sys.argv[0] = str(Path(sys.argv[0]).resolve())
sys.path.insert(0, str(ROOT))
BIN = ROOT / ('bin' if getattr(sys, 'frozen', False) else 'windows/bin')
SMOKE = '--smoke-test' in sys.argv
UI_SMOKE = '--ui-smoke-test' in sys.argv
BROWSER_SMOKE = '--browser-smoke-test' in sys.argv
from agent.storage_paths import DATA
import tempfile
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'Temp').mkdir(exist_ok=True)
os.environ['TEMP'] = os.environ['TMP'] = str(DATA / 'Temp')
tempfile.tempdir = str(DATA / 'Temp')
os.environ['FLOW_AGENT_DIR'] = str(DATA)
os.environ['API_HOST'] = os.environ['WS_HOST'] = '127.0.0.1'
os.environ['API_PORT'] = '8100'
os.environ['WS_PORT'] = '9222'
os.environ['PATH'] = str(BIN) + os.pathsep + os.environ.get('PATH', '')
os.chdir(DATA)
log = open(DATA / 'desktop.log', 'a', encoding='utf-8', buffering=1)
sys.stdout = sys.stderr = log
logging.basicConfig(handlers=[RotatingFileHandler(DATA / 'app.log', maxBytes=5 * 1024 * 1024, backupCount=2, encoding='utf-8')], level=logging.INFO, force=True)

logging.getLogger('httpx').setLevel(logging.WARNING)


def browser_control():
    import tkinter as tk
    from tkinter import ttk
    import webbrowser
    panel = tk.Tk()
    panel.title('Muse Landscape Studio')
    panel.geometry('530x310')
    panel.resizable(False, False)
    frame = ttk.Frame(panel, padding=24)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Muse Landscape Studio đang chạy', font=('Segoe UI', 16)).pack(anchor='w', pady=(0, 12))
    ttk.Label(frame, text='Giao diện: http://127.0.0.1:8100\nGiữ cửa sổ này mở khi sử dụng trong trình duyệt.').pack(anchor='w', pady=(0, 16))
    for title, callback in [
        ('Mở giao diện', lambda: webbrowser.open('http://127.0.0.1:8100')),
        ('Thư mục kết quả Muse', lambda: os.startfile(str(DATA / '.flowkit' / 'muse-gateway'))),
        ('Thư mục dữ liệu và nhật ký', lambda: os.startfile(str(DATA))),
        ('Thoát ứng dụng', panel.destroy),
    ]:
        ttk.Button(frame, text=title, command=callback).pack(fill='x', pady=3)
    if BROWSER_SMOKE:
        panel.withdraw()
        def verify():
            (DATA / 'browser-ui-result.json').write_text(json.dumps({'tk': str(panel.tk.call('info', 'patchlevel')), 'buttons': 4, 'status': 'ok'}), encoding='utf-8')
            panel.destroy()
        panel.after(300, verify)
    else:
        panel.after(500, lambda: webbrowser.open('http://127.0.0.1:8100'))
    panel.mainloop()


class UpdateApi:
    """JS API: nut "Cap nhat" tren giao dien goi vao day (chay thread rieng, khong dong bang UI)."""
    def __init__(self):
        self._window = None
        self._lock = threading.Lock()

    def check_update(self):
        if not self._lock.acquire(blocking=False):
            return 'busy'
        try:
            import app_gate
            if app_gate.check_update(True):
                if self._window is not None:
                    self._window.destroy()
                return 'installing'
            return 'done'
        except Exception:
            logging.exception('Manual update failed')
            return 'error'
        finally:
            self._lock.release()


def main():
    import uvicorn
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from agent.muse_app import app
    static = ROOT / 'dashboard' / 'dist'
    app.mount('/assets', StaticFiles(directory=static / 'assets'), name='dashboard-assets')

    @app.get('/{path:path}', include_in_schema=False)
    async def dashboard(path: str):
        if path == 'api' or path.startswith(('api/', 'ws/')):
            raise HTTPException(404)
        candidate = (static / path).resolve()
        if candidate.is_relative_to(static.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static / 'index.html')

    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8100, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(300):
            if server.started:
                break
            if not thread.is_alive():
                raise RuntimeError('Không khởi động được máy chủ. Kiểm tra cổng 8100 trong desktop.log.')
            time.sleep(.1)
        else:
            raise RuntimeError('Quá thời gian khởi động máy chủ.')
        if SMOKE:
            report = {}
            for endpoint in ('/health', '/', '/api/muse/status', '/api/muse/scenes/options', '/api/muse/scenes/storage', '/api/muse/scenes'):
                req = urllib.request.Request('http://127.0.0.1:8100' + endpoint, headers={'X-Flowkit-Local-Auth': '1'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    body = response.read()
                    report[endpoint] = {'status': response.status, 'bytes': len(body)}
                    if endpoint == '/health':
                        report['health'] = json.loads(body)
            html = (static / 'index.html').read_text(encoding='utf-8')
            for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html):
                local_asset = static / asset.lstrip('/')
                if not local_asset.is_file():
                    raise RuntimeError('Missing dashboard asset: ' + asset)
                with urllib.request.urlopen('http://127.0.0.1:8100' + asset, timeout=10) as response:
                    if response.read() != local_asset.read_bytes():
                        raise RuntimeError('Dashboard asset mismatch: ' + asset)
                report[asset] = {'status': 200, 'bytes': local_asset.stat().st_size}
            for binary in ('ffmpeg', 'ffprobe'):
                result = subprocess.run([str(BIN / (binary + '.exe')), '-version'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
                report[binary] = result.stdout.splitlines()[0]
            (DATA / 'smoke-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            return
        if '--browser' in sys.argv or BROWSER_SMOKE:
            browser_control()
            return
        try:
            import webview
        except Exception:
            logging.exception('WebView unavailable; opening browser control')
            browser_control()
            return
        from webview.menu import Menu, MenuAction, MenuSeparator
        update_api = UpdateApi()
        window = webview.create_window('Muse Landscape Studio', 'http://127.0.0.1:8100', width=1400, height=900, min_size=(1000, 650), hidden=UI_SMOKE, js_api=update_api)
        update_api._window = window
        loaded = threading.Event()
        window.events.loaded += loaded.set
        menu = [Menu('Muse Landscape Studio', [
            MenuAction('Mở thư mục dữ liệu', lambda: os.startfile(str(DATA))),
            MenuAction('Mở thư mục dữ liệu Muse', lambda: os.startfile(str(DATA))),
            MenuAction('Mở nhật ký', lambda: os.startfile(str(DATA / 'app.log'))),
            MenuSeparator(),
            MenuAction('Tải lại giao diện', lambda: window.load_url('http://127.0.0.1:8100')),
            MenuAction('Thoát', window.destroy),
        ])]
        if UI_SMOKE:
            def verify_window():
                try:
                    for _ in range(60):
                        report = window.evaluate_js('({title: document.title, text: document.body.innerText, rootChildren: document.getElementById("root")?.childElementCount || 0})')
                        if report['rootChildren'] and len(report['text']) > 30:
                            (DATA / 'ui-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                            return
                        time.sleep(.5)
                    raise RuntimeError('React did not render')
                except Exception:
                    logging.exception('UI smoke test failed')
                finally:
                    window.destroy()
            window.events.loaded += verify_window
        def startup_timeout():
            if not loaded.is_set():
                window.destroy()
        watchdog = threading.Timer(15, startup_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            webview.start(gui='edgechromium', storage_path=str(DATA / 'webview'), menu=menu, icon=str(ROOT / ('app-icon.ico' if getattr(sys, 'frozen', False) else 'windows/assets/app-icon.ico')))
        except Exception:
            logging.exception('WebView initialization failed')
        finally:
            watchdog.cancel()
        if UI_SMOKE and not (DATA / 'ui-result.json').exists():
            raise RuntimeError('WebView2 smoke test failed')
        if not loaded.is_set():
            browser_control()
    finally:
        # Stop services before uvicorn waits for long-lived chat/video requests.
        import asyncio
        from agent.muse_app import shutdown_services
        loop = getattr(app.state, 'event_loop', None)
        if loop and thread.is_alive() and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(shutdown_services(app), loop).result(timeout=25)
            except Exception:
                logging.exception('Graceful Muse shutdown timed out')
        server.should_exit = True
        thread.join(timeout=5)
        from agent.services.muse_browser_cleanup import close_owned_chrome
        close_owned_chrome(DATA / '.flowkit' / 'muse-gateway')


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    # One instance per user; never attach to an unrelated service on this port.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    mutex = kernel.CreateMutexW(None, False, 'Local\\FrameWeaverWindowsPreview')
    if ctypes.get_last_error() == 183:
        logging.error('Another FrameWeaver instance owns the Windows mutex')
        if not SMOKE and not UI_SMOKE:
            ctypes.windll.user32.MessageBoxW(None, 'Muse Landscape Studio đang chạy. Hãy mở cửa sổ hiện có.', 'FrameWeaver', 64)
        sys.exit(1)
    if not (SMOKE or UI_SMOKE or BROWSER_SMOKE):
        # Bat buoc ma kich hoat; cap nhat tu thu muc LAN (chi ban da kich hoat).
        import app_gate
        if not app_gate.ensure_activated():
            sys.exit(0)
        if app_gate.check_update('--check-update' in sys.argv) or '--check-update' in sys.argv:
            sys.exit(0)
    try:
        main()
    except BaseException:
        import traceback
        traceback.print_exc(file=log)
        log.flush()
        logging.exception('Desktop startup failed')
        if not SMOKE and not UI_SMOKE:
            ctypes.windll.user32.MessageBoxW(None, 'Không mở được Muse Landscape Studio. Xem nhật ký tại:\n' + str(DATA / 'desktop.log'), 'FrameWeaver', 16)
        sys.exit(1)
    finally:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(mutex)
