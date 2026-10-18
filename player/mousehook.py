"""Left-button watcher for the video area (Windows only).

libVLC renders into its own child window, which swallows left clicks, so Qt
never sees a double-click on playing video. A low-level mouse hook reports
left-button presses; the player decides whether they landed on the video."""

import ctypes
import sys
from ctypes import wintypes

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class LeftClickHook:
    def __init__(self, on_press):
        """`on_press(x, y)` gets physical screen pixels for every left press."""
        self._on_press = on_press
        self._handle = None
        if sys.platform != "win32":
            return
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        proto = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        self._user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.CallNextHookEx.restype = ctypes.c_ssize_t
        self._user32.SetWindowsHookExW.argtypes = [ctypes.c_int, proto, wintypes.HINSTANCE, wintypes.DWORD]
        self._user32.SetWindowsHookExW.restype = ctypes.c_void_p
        self._user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        self._proc = proto(self._callback)  # keep a reference so it isn't collected
        self._handle = self._user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)

    def _callback(self, code, wparam, lparam):
        if code >= 0 and wparam == WM_LBUTTONDOWN:
            info = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            try:
                self._on_press(info.pt.x, info.pt.y)
            except Exception:  # never let an error escape into the hook chain
                pass
        return self._user32.CallNextHookEx(None, code, wparam, lparam)

    def close(self):
        if self._handle:
            self._user32.UnhookWindowsHookEx(self._handle)
            self._handle = None


def window_is_under(x: int, y: int, hwnd: int) -> bool:
    """True when the window at physical point (x, y) is `hwnd` or one of its children
    (libVLC's video window), i.e. not a menu or floating bar that happens to cover it."""
    if sys.platform != "win32":
        return True
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
    hit = user32.WindowFromPoint(wintypes.POINT(x, y))
    return bool(hit) and (hit == hwnd or bool(user32.IsChild(hwnd, hit)))
