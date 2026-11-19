"""Windows exit cleanup, strictly limited to Muse's own Chrome profiles."""
import ctypes
import json
import logging
import os
from pathlib import Path
import re
import subprocess

log = logging.getLogger(__name__)


def command_args(command):
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    count = ctypes.c_int()
    values = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not values:
        return []
    try:
        return [values[i] for i in range(count.value)]
    finally:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(values, ctypes.c_void_p))


def owns_browser(args, root):
    def flag(name):
        for i, arg in enumerate(args):
            if arg.startswith(name + '='):
                return arg.split('=', 1)[1]
            if arg == name and i + 1 < len(args):
                return args[i + 1]
        return None
    profile = flag('--user-data-dir')
    port = flag('--remote-debugging-port')
    if not profile or port not in {'19210', '19211'}:
        return False
    profile, root = Path(profile).resolve(), Path(root).resolve()
    return profile.parent == root and bool(re.fullmatch(r'chrome-profile|login-profile|login-[0-9a-f]{20}', profile.name))


def close_owned_chrome(root):
    if os.name != 'nt':
        return []
    flags = subprocess.CREATE_NO_WINDOW
    command = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, text=True, encoding='utf-8', timeout=10, creationflags=flags)
        if result.returncode or not result.stdout.strip():
            return []
        rows = json.loads(result.stdout.lstrip('\ufeff'))
        rows = rows if isinstance(rows, list) else [rows]
        stopped = []
        for row in rows:
            pid = int(row.get('ProcessId') or 0)
            args = command_args(row.get('CommandLine') or '')
            if pid <= 0 or not owns_browser(args, root):
                continue
            # Never kill by executable name. The matching browser parent owns
            # this isolated tree; ordinary Chrome profiles cannot pass above.
            kill = subprocess.run(['taskkill.exe', '/PID', str(pid), '/T', '/F'],
                                  capture_output=True, timeout=5, creationflags=flags)
            if not kill.returncode:
                stopped.append(pid)
        return stopped
    except (OSError, ValueError, subprocess.TimeoutExpired):
        log.exception('Could not finish scoped Muse browser cleanup')
        return []
