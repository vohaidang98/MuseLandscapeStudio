"""Small Windows resource sampler and hysteresis-based admission controller.

Only NEW work is gated. An admitted Muse request is never cancelled here.
"""
import asyncio
import ctypes
from ctypes import wintypes
import math
import os
import time


class WindowsLoad:
    def __init__(self):
        self.previous = None

    def sample(self):
        if os.name != 'nt':
            return None
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        idle, system, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        kernel.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3
        kernel.GetSystemTimes.restype = wintypes.BOOL
        if not kernel.GetSystemTimes(ctypes.byref(idle), ctypes.byref(system), ctypes.byref(user)):
            raise OSError(ctypes.get_last_error(), 'GetSystemTimes failed')
        def value(t):
            return (t.dwHighDateTime << 32) | t.dwLowDateTime
        current = (value(idle), value(system) + value(user))
        cpu = None
        if self.previous:
            elapsed = current[1] - self.previous[1]
            if elapsed > 0:
                cpu = max(0., min(100., 100 * (1 - (current[0] - self.previous[0]) / elapsed)))
        self.previous = current

        class Memory(ctypes.Structure):
            _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [
                (name, ctypes.c_ulonglong) for name in
                ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]
        memory = Memory()
        memory.length = ctypes.sizeof(memory)
        kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(Memory)]
        kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise OSError(ctypes.get_last_error(), 'GlobalMemoryStatusEx failed')
        return {'cpu': cpu, 'ram': float(memory.load), 'free_gb': memory.available / 1024**3}


class AdaptiveGovernor:
    def __init__(self, ceiling=6, enabled=True, sampler=None):
        self.sampler = sampler or WindowsLoad()
        self.task = None
        self.configure(ceiling, enabled)

    def configure(self, ceiling, enabled=True):
        self.ceiling = max(1, int(ceiling))
        self.enabled = bool(enabled)
        self.target = min(2, self.ceiling) if self.enabled else self.ceiling
        self.cpu = self.ram = self.free_gb = None
        self.sampled_at = None
        self.last_change = -math.inf
        self.high_samples = self.low_samples = self.recovery_samples = 0
        self.paused = False
        self.reason = 'Đang đo tải máy; bắt đầu ít luồng.' if enabled else 'Điều phối thủ công theo chế độ đã chọn.'

    def observe(self, sample, now=None):
        now = time.monotonic() if now is None else now
        if not sample or any(sample.get(key) is not None and not math.isfinite(sample[key]) for key in ('cpu', 'ram', 'free_gb')):
            self.sampled_at = None
            self.reason = 'Chưa đo được tải máy; giới hạn luồng ở mức thấp.'
            return
        self.cpu, self.ram, self.free_gb = (sample.get(key) for key in ('cpu', 'ram', 'free_gb'))
        if self.ram is None or self.free_gb is None:
            self.sampled_at = None
            return
        self.sampled_at = now
        if not self.enabled:
            self.target = self.ceiling
            return
        critical = self.ram >= 96 or self.free_gb < .5
        if critical:
            self.paused = True
            self.target = 0
            self.recovery_samples = self.low_samples = 0
            self.last_change = now
            self.reason = 'RAM gần đầy: tạm ngừng gửi việc mới, chờ tác vụ đang chạy giải phóng bộ nhớ.'
            return
        if self.paused:
            recovered = self.ram < 90 and self.free_gb >= .9 and self.cpu is not None and self.cpu < 85
            self.recovery_samples = self.recovery_samples + 1 if recovered else 0
            if self.recovery_samples >= 3:
                self.paused = False
                self.target = 1
                self.last_change = now
                self.low_samples = 0
                self.reason = 'Máy đã nhẹ hơn; tiếp tục từ một luồng.'
            return
        high = self.ram >= 90 or self.free_gb < 1 or (self.cpu is not None and self.cpu >= 90)
        low = self.cpu is not None and self.cpu < 70 and self.ram < 84 and self.free_gb >= 1.2
        self.high_samples = self.high_samples + 1 if high else 0
        self.low_samples = self.low_samples + 1 if low else 0
        if high and (self.ram >= 90 or self.free_gb < 1 or self.high_samples >= 2) and now - self.last_change >= 15:
            self.target = max(1, self.target // 2)
            self.last_change = now
            self.low_samples = 0
            self.reason = 'CPU/RAM cao: giảm luồng mới; giữ nguyên tác vụ đã gửi.'
        elif self.low_samples >= 6 and now - self.last_change >= 30:
            self.target = min(self.ceiling, self.target + 1)
            self.last_change = now
            self.low_samples = 0
            self.reason = 'Tải máy ổn định: tăng dần luồng trong giới hạn đã chọn.'
        elif not high and self.target >= self.ceiling:
            self.reason = 'Đang chạy trong giới hạn hiệu năng đã chọn.'

    def limit(self, now=None):
        if not self.enabled:
            return self.ceiling
        now = time.monotonic() if now is None else now
        if self.sampled_at is None or now - self.sampled_at > 20:
            # A missing/stale sensor must not silently leave a permanent pause
            # or release all queued requests at once.
            return min(2, self.ceiling)
        return min(self.ceiling, self.target)

    def snapshot(self, active=0):
        stale = self.sampled_at is None or time.monotonic() - self.sampled_at > 20
        return {'enabled': self.enabled, 'target_jobs': self.limit(), 'ceiling': self.ceiling,
                'active_jobs': active, 'paused': self.enabled and self.limit() == 0,
                'cpu_percent': None if stale or self.cpu is None else round(self.cpu, 1),
                'ram_percent': None if stale or self.ram is None else round(self.ram, 1),
                'free_gb': None if stale or self.free_gb is None else round(self.free_gb, 2),
                'reason': 'Chưa đo được tải máy; giới hạn luồng ở mức thấp.' if stale and self.enabled else self.reason,
                'sample_seconds': 5}

    def start(self):
        if self.task and not self.task.done():
            return
        async def run():
            while True:
                try:
                    sample = await asyncio.to_thread(self.sampler.sample)
                    self.observe(sample)
                except (OSError, ValueError, TypeError):
                    self.observe(None)
                await asyncio.sleep(5)
        self.task = asyncio.create_task(run())

    async def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
