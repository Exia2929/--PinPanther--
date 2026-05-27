# -*- coding: utf-8 -*-
"""
PinPanther 🐾 —— 多螢幕「程式視窗自動定位」工具
=================================================

用途：
    你是多螢幕使用者，希望「每次開啟某個程式時，它的視窗自動跑到指定的螢幕上」，
    而且每個程式可以分別設定要用「視窗 / 最大化 / 全螢幕(無邊框)」開啟。

特色：
    * 純 Python 標準函式庫（tkinter + ctypes），不需要 pip 安裝任何套件。
    * 圖形化介面：新增 / 編輯 / 刪除規則、即時監控、日誌顯示。
    * 監控背景執行，偵測到新視窗就自動套用規則。

執行環境： Windows 10 / 11、Python 3.8+
注意：若目標程式是以「系統管理員」身分執行，本程式也需以系統管理員身分執行才能搬移它的視窗。
"""

import os
import json
import time
import queue
import threading
import subprocess
import shutil
import webbrowser
import ctypes
from ctypes import wintypes

import tkinter as tk
from tkinter import ttk, messagebox

from ahk_generator import generate_ahk_script
import i18n
from i18n import t


# ===========================================================================
#  Windows API（ctypes）封裝
# ===========================================================================

# --- 讓程式具備 Per-Monitor DPI 感知，多螢幕不同縮放時座標才正確 -------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

RECT = wintypes.RECT
HMONITOR = wintypes.HANDLE

# --- 常數 ------------------------------------------------------------------
GWL_STYLE = -16
GWL_EXSTYLE = -20
GW_OWNER = 4

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
HWND_TOP = 0

SW_SHOWNORMAL = 1
SW_MAXIMIZE = 3
SW_SHOW = 5
SW_RESTORE = 9

MONITORINFOF_PRIMARY = 1
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


# --- 結構 ------------------------------------------------------------------
class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


# --- 回呼型別 --------------------------------------------------------------
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
)

# --- 函式原型（明確宣告 argtypes，避免 64 位元 handle 被截斷） ----------------
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL

user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL

user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC, ctypes.POINTER(RECT), MonitorEnumProc, wintypes.LPARAM
]
user32.EnumDisplayMonitors.restype = wintypes.BOOL

user32.GetMonitorInfoW.argtypes = [HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL

# 64 位元要用 ...Ptr 版本才能正確讀寫視窗樣式
if ctypes.sizeof(ctypes.c_void_p) == 8:
    _GetWindowLong = user32.GetWindowLongPtrW
    _SetWindowLong = user32.SetWindowLongPtrW
else:
    _GetWindowLong = user32.GetWindowLongW
    _SetWindowLong = user32.SetWindowLongW
_GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
_GetWindowLong.restype = ctypes.c_longlong
_SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
_SetWindowLong.restype = ctypes.c_longlong

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long  # HRESULT


# --- 系統列(tray) 相關 API（純 ctypes，無外部相依） -------------------------
shell32 = ctypes.windll.shell32

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", WPARAM),
        ("lParam", LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, ctypes.c_void_p,
]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def _make_int_resource(i):
    return ctypes.cast(ctypes.c_void_p(i & 0xFFFF), wintypes.LPCWSTR)


# tray 常數
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_TRAY_CALLBACK = 0x0400 + 20
NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
IDI_APPLICATION = 32512
IDC_ARROW = 32512
MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100
TRAY_ID_SHOW = 1
TRAY_ID_WATCH = 2
TRAY_ID_QUIT = 3


# --- 輔助函式 --------------------------------------------------------------
def get_window_text(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_window_pid(hwnd):
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def get_exe_name(pid):
    """以 PID 取得執行檔名（小寫，例如 'notepad.exe'）。"""
    if not pid:
        return ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(2048)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def is_cloaked(hwnd):
    """UWP / 商店 App 常有被 DWM 隱藏(cloaked)的幽靈視窗，要排除。"""
    val = ctypes.c_int(0)
    res = dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val)
    )
    return res == 0 and val.value != 0


def is_real_window(hwnd):
    """判斷是否為「真正的應用程式主視窗」。"""
    if not user32.IsWindowVisible(hwnd):
        return False
    if user32.GetWindow(hwnd, GW_OWNER):          # 有 owner 的多半是對話框
        return False
    ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW:                      # 工具視窗
        return False
    if is_cloaked(hwnd):
        return False
    r = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    if (r.right - r.left) <= 0 or (r.bottom - r.top) <= 0:
        return False
    return True


def enum_real_windows():
    """回傳目前所有「真正的應用程式視窗」的 hwnd 清單。"""
    out = []

    def cb(hwnd, _lparam):
        if is_real_window(hwnd):
            out.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def get_monitors():
    """回傳螢幕清單（依左→右、上→下排序），每筆含 monitor/work 矩形與是否主螢幕。"""
    mons = []

    def cb(hMonitor, _hdc, _lprc, _lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
            m, w = mi.rcMonitor, mi.rcWork
            mons.append({
                "monitor": (m.left, m.top, m.right, m.bottom),
                "work": (w.left, w.top, w.right, w.bottom),
                "primary": bool(mi.dwFlags & MONITORINFOF_PRIMARY),
                "device": mi.szDevice,
            })
        return True

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(cb), 0)
    mons.sort(key=lambda x: (x["monitor"][0], x["monitor"][1]))
    return mons


def monitor_label(idx, mon):
    mw = mon["monitor"][2] - mon["monitor"][0]
    mh = mon["monitor"][3] - mon["monitor"][1]
    tag = t("primary_tag") if mon["primary"] else ""
    return t("monitor_label", idx=idx, w=mw, h=mh,
             x=mon["monitor"][0], y=mon["monitor"][1], tag=tag)


# ===========================================================================
#  套用規則：把視窗搬到指定螢幕並設定狀態
# ===========================================================================
def apply_rule(hwnd, rule, monitors, log=lambda *_: None):
    idx = int(rule.get("monitor_index", 0))
    if idx < 0 or idx >= len(monitors):
        prim = next((i for i, m in enumerate(monitors) if m["primary"]), 0)
        log(t("log_monitor_missing", idx=idx, prim=prim))
        idx = prim
    if not monitors:
        return
    mon = monitors[idx]
    mrect = mon["monitor"]
    wrect = mon["work"]
    mode = rule.get("mode", "maximized")

    try:
        # 先還原，避免「在錯誤螢幕上已最大化」造成搬移失敗
        user32.ShowWindow(hwnd, SW_RESTORE)

        if mode == "maximized":
            # 先把視窗移到目標螢幕，再最大化（最大化會貼齊它所在的那個螢幕）
            x, y = wrect[0], wrect[1]
            w = (wrect[2] - wrect[0]) // 2
            h = (wrect[3] - wrect[1]) // 2
            user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h,
                                SWP_NOZORDER | SWP_NOACTIVATE)
            user32.ShowWindow(hwnd, SW_MAXIMIZE)

        elif mode == "fullscreen":
            # 無邊框全螢幕：移除標題列/邊框，覆蓋整個螢幕矩形
            style = _GetWindowLong(hwnd, GWL_STYLE)
            style &= ~WS_OVERLAPPEDWINDOW
            _SetWindowLong(hwnd, GWL_STYLE, style)
            x, y = mrect[0], mrect[1]
            w = mrect[2] - mrect[0]
            h = mrect[3] - mrect[1]
            user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h,
                                SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_SHOWWINDOW)

        else:  # windowed
            cw = int(rule.get("win_w") or 0)
            ch = int(rule.get("win_h") or 0)
            if cw > 0 and ch > 0:
                # 使用記住的自訂大小；位置相對於目標螢幕工作區左上角
                w, h = cw, ch
                x = wrect[0] + int(rule.get("win_x") or 0)
                y = wrect[1] + int(rule.get("win_y") or 0)
            else:
                # 未設定 → 在工作區置中，大小為工作區的 70%
                ww = wrect[2] - wrect[0]
                wh = wrect[3] - wrect[1]
                w = int(ww * 0.7)
                h = int(wh * 0.7)
                x = wrect[0] + (ww - w) // 2
                y = wrect[1] + (wh - h) // 2
            user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h,
                                SWP_NOZORDER | SWP_NOACTIVATE)
    except Exception as e:
        log(t("log_apply_failed", e=e))


def norm_exe(name):
    name = (name or "").lower().strip()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def match_rule(rules, exe, title):
    """找出第一條符合的（已啟用的）規則。"""
    exe_n = norm_exe(exe)
    title_l = (title or "").lower()
    for r in rules:
        if not r.get("enabled", True):
            continue
        if not r.get("exe"):
            continue
        if norm_exe(r["exe"]) != exe_n:
            continue
        tc = (r.get("title_contains") or "").strip().lower()
        if tc and tc not in title_l:
            continue
        return r
    return None


# ===========================================================================
#  背景監控執行緒
# ===========================================================================
class Watcher(threading.Thread):
    def __init__(self, get_rules, log, interval=1.0, self_pid=None):
        super().__init__(daemon=True)
        self.get_rules = get_rules
        self.log = log
        self.interval = max(0.3, float(interval))
        self.self_pid = self_pid or os.getpid()
        self._stop = threading.Event()
        self.seen = set()
        self.pending = {}  # hwnd -> [rule, 剩餘重套次數]

    def stop(self):
        self._stop.set()

    def run(self):
        # 啟動時先把「現有視窗」記為已看過，只處理之後新開的視窗
        for h in enum_real_windows():
            self.seen.add(h)
        self.log(t("log_watch_started"))
        while not self._stop.is_set():
            try:
                monitors = get_monitors()
                current = enum_real_windows()
                curset = set(current)
                for hwnd in current:
                    if hwnd in self.seen:
                        continue
                    self.seen.add(hwnd)
                    self._handle_new(hwnd, monitors)
                self._process_pending(monitors)
                # 清掉已關閉的視窗
                self.seen &= (curset | set(self.pending.keys()))
            except Exception as e:
                self.log(t("log_watch_loop_err", e=e))
            self._stop.wait(self.interval)
        self.log(t("log_watch_stopped"))

    def _handle_new(self, hwnd, monitors):
        pid = get_window_pid(hwnd)
        if pid == self.self_pid:
            return
        exe = get_exe_name(pid)
        title = get_window_text(hwnd)
        rule = match_rule(self.get_rules(), exe, title)
        if not rule:
            return
        apply_rule(hwnd, rule, monitors, self.log)
        mon_txt = (monitor_label(rule["monitor_index"], monitors[rule["monitor_index"]])
                   if rule["monitor_index"] < len(monitors) else t("monitor_unknown"))
        self.log(t("log_applied_window", exe=exe, monitor=mon_txt,
                   mode=i18n.mode_label(rule["mode"]), title=title[:30]))
        # 最大化 / 全螢幕：有些程式會在開啟後自己調整位置，故再補套幾次
        if rule.get("mode") in ("maximized", "fullscreen"):
            self.pending[hwnd] = [rule, 2]

    def _process_pending(self, monitors):
        done = []
        for hwnd, info in list(self.pending.items()):
            rule, remaining = info
            if not user32.IsWindow(hwnd):
                done.append(hwnd)
                continue
            apply_rule(hwnd, rule, monitors)
            remaining -= 1
            if remaining <= 0:
                done.append(hwnd)
            else:
                self.pending[hwnd][1] = remaining
        for h in done:
            self.pending.pop(h, None)


# ===========================================================================
#  系統列(tray) 圖示
# ===========================================================================
class TrayIcon(threading.Thread):
    """純 ctypes 實作的系統列圖示，於自己的執行緒維護 Win32 訊息迴圈。

    使用者點擊圖示或選單時，會呼叫 dispatch(cmd)，cmd 為下列字串之一：
    "show" / "toggle_watch" / "quit"。dispatch 應只是把指令丟進佇列，
    真正的動作交由 GUI 主執行緒處理（tkinter 非執行緒安全）。
    """

    def __init__(self, tooltip, dispatch):
        super().__init__(daemon=True)
        self.tooltip = (tooltip or "MonitorPin")[:127]
        self.dispatch = dispatch
        self.hwnd = None
        self.nid = None
        self._wndproc = None
        self._class_name = f"MonitorPinTray_{os.getpid()}"
        self.ready = threading.Event()
        self.ok = False

    def run(self):
        try:
            self._create_window()
            self._add_icon()
            self.ok = True
        except Exception:
            self.ok = False
            self.ready.set()
            return
        self.ready.set()
        msg = MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        try:
            self._remove_icon()
        except Exception:
            pass

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    # ---- 內部 ----
    def _create_window(self):
        self._wndproc = WNDPROC(self._wnd_proc)
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = self._class_name
        wc.hIcon = user32.LoadIconW(None, _make_int_resource(IDI_APPLICATION))
        wc.hCursor = user32.LoadCursorW(None, _make_int_resource(IDC_ARROW))
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(
            0, self._class_name, "MonitorPin", 0, 0, 0, 0, 0,
            None, None, hinst, None)
        if not self.hwnd:
            raise OSError("CreateWindowExW failed")

    def _add_icon(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY_CALLBACK
        nid.hIcon = user32.LoadIconW(None, _make_int_resource(IDI_APPLICATION))
        nid.szTip = self.tooltip
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            raise OSError("Shell_NotifyIcon ADD failed")
        self.nid = nid

    def _remove_icon(self):
        if self.nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.nid = None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY_CALLBACK:
            ev = lparam & 0xFFFF
            if ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.dispatch("show")
            elif ev == WM_RBUTTONUP:
                self._show_menu(hwnd)
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_menu(self, hwnd):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, TRAY_ID_SHOW, t("tray_show"))
        user32.AppendMenuW(menu, MF_STRING, TRAY_ID_WATCH, t("tray_toggle_watch"))
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, TRAY_ID_QUIT, t("tray_quit"))
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            pt.x, pt.y, 0, hwnd, None)
        user32.PostMessageW(hwnd, 0, 0, 0)
        user32.DestroyMenu(menu)
        if cmd == TRAY_ID_SHOW:
            self.dispatch("show")
        elif cmd == TRAY_ID_WATCH:
            self.dispatch("toggle_watch")
        elif cmd == TRAY_ID_QUIT:
            self.dispatch("quit")


# ===========================================================================
#  設定檔
# ===========================================================================
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "monitor_pin_rules.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, list):
            d = {"rules": d}
        lang = d.get("lang", "zh")
        return {
            "rules": d.get("rules", []),
            "auto_start": bool(d.get("auto_start", False)),
            "interval": float(d.get("interval", 1.0)),
            "tray_close": bool(d.get("tray_close", True)),
            "tray_min": bool(d.get("tray_min", True)),
            "lang": lang if lang in i18n.LANGS else "zh",
        }
    except Exception:
        return {"rules": [], "auto_start": False, "interval": 1.0,
                "tray_close": True, "tray_min": True, "lang": "zh"}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showerror(t("err_save_title"), t("err_save_body", e=e))


# ===========================================================================
#  AutoHotkey 開機腳本：產生與部署
# ===========================================================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
AHK_SCRIPT_PATH = os.path.join(PROJECT_DIR, "PinPanther.ahk")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
STARTUP_SHORTCUT = os.path.join(STARTUP_DIR, "PinPanther.lnk")

_CREATE_NO_WINDOW = 0x08000000

_AHK_CANDIDATES = [
    r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe",
    r"C:\Program Files\AutoHotkey\v2\AutoHotkey32.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 r"Programs\AutoHotkey\v2\AutoHotkey64.exe"),
    r"C:\Program Files\AutoHotkey\AutoHotkey64.exe",
    r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
]


def find_ahk_exe():
    """找出 AutoHotkey v2 執行檔路徑，找不到回傳 None。"""
    for p in _AHK_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\AutoHotkey") as k:
                    inst = winreg.QueryValueEx(k, "InstallDir")[0]
                for sub in (r"v2\AutoHotkey64.exe", r"v2\AutoHotkey32.exe",
                            "AutoHotkey64.exe", "AutoHotkey.exe"):
                    cand = os.path.join(inst, sub)
                    if os.path.isfile(cand):
                        return cand
            except OSError:
                continue
    except Exception:
        pass
    return None


def write_ahk_script(rules):
    """用目前規則產生腳本並寫到專案資料夾（UTF-8 with BOM，AHK 才能正確讀中文）。"""
    text = generate_ahk_script(rules, lang=i18n.get_lang())
    with open(AHK_SCRIPT_PATH, "w", encoding="utf-8-sig") as f:
        f.write(text)
    return AHK_SCRIPT_PATH


def _ps_quote(s):
    """包成 PowerShell 單引號字串（內部單引號要加倍）。"""
    return "'" + str(s).replace("'", "''") + "'"


def create_startup_shortcut(ahk_exe):
    """在 shell:startup 建立指向『AHK 執行檔 + 本腳本』的捷徑（覆蓋既有）。"""
    os.makedirs(STARTUP_DIR, exist_ok=True)
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut({lnk});"
        "$s.TargetPath={tgt};"
        "$s.Arguments={args};"
        "$s.WorkingDirectory={wd};"
        "$s.IconLocation={icon};"
        "$s.Description='PinPanther 多螢幕視窗自動定位';"
        "$s.Save()"
    ).format(
        lnk=_ps_quote(STARTUP_SHORTCUT),
        tgt=_ps_quote(ahk_exe),
        args=_ps_quote('"%s"' % AHK_SCRIPT_PATH),
        wd=_ps_quote(PROJECT_DIR),
        icon=_ps_quote(ahk_exe + ",0"),
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        check=True, creationflags=_CREATE_NO_WINDOW, capture_output=True,
    )


def remove_startup_shortcut():
    """從開機啟動移除捷徑（腳本檔本身保留）。"""
    if os.path.isfile(STARTUP_SHORTCUT):
        os.remove(STARTUP_SHORTCUT)


def is_deployed():
    return os.path.isfile(STARTUP_SHORTCUT)


def run_script_once(ahk_exe):
    """用最新規則立刻啟動腳本（測試用；常駐於系統列，可右鍵結束）。"""
    return subprocess.Popen([ahk_exe, AHK_SCRIPT_PATH], cwd=PROJECT_DIR)


# ===========================================================================
#  規則編輯對話框
# ===========================================================================
class RuleDialog(tk.Toplevel):
    def __init__(self, master, monitors, rule=None):
        super().__init__(master)
        self.title(t("dlg_edit_title") if rule else t("dlg_add_title"))
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        self.monitors = monitors

        rule = rule or {}
        pad = {"padx": 10, "pady": 6}

        # 執行檔名稱 + 從目前視窗挑選
        ttk.Label(self, text=t("lbl_exe")).grid(
            row=0, column=0, sticky="w", **pad)
        self.exe_var = tk.StringVar(value=rule.get("exe", ""))
        exe_box = ttk.Combobox(self, textvariable=self.exe_var, width=34,
                               values=self._running_exes())
        exe_box.grid(row=0, column=1, sticky="we", **pad)

        # 視窗標題包含（選填）
        ttk.Label(self, text=t("lbl_title_contains")).grid(
            row=1, column=0, sticky="w", **pad)
        self.title_var = tk.StringVar(value=rule.get("title_contains", ""))
        ttk.Entry(self, textvariable=self.title_var, width=36).grid(
            row=1, column=1, sticky="we", **pad)

        # 目標螢幕
        ttk.Label(self, text=t("lbl_which_monitor")).grid(
            row=2, column=0, sticky="w", **pad)
        self.mon_labels = [monitor_label(i, m) for i, m in enumerate(monitors)]
        self.mon_var = tk.StringVar()
        mon_box = ttk.Combobox(self, textvariable=self.mon_var, width=34,
                               values=self.mon_labels, state="readonly")
        cur_idx = int(rule.get("monitor_index", 0))
        if 0 <= cur_idx < len(self.mon_labels):
            mon_box.current(cur_idx)
        elif self.mon_labels:
            mon_box.current(0)
        mon_box.grid(row=2, column=1, sticky="we", **pad)
        self.mon_box = mon_box

        # 開啟模式
        ttk.Label(self, text=t("lbl_mode")).grid(row=3, column=0, sticky="nw", **pad)
        self.mode_var = tk.StringVar(value=rule.get("mode", "maximized"))
        mode_frame = ttk.Frame(self)
        mode_frame.grid(row=3, column=1, sticky="w", **pad)
        for key in ("windowed", "maximized", "fullscreen"):
            ttk.Radiobutton(mode_frame, text=i18n.mode_label(key), value=key,
                            variable=self.mode_var).pack(anchor="w")

        # 視窗模式自訂大小 / 位置（僅「視窗」模式有效，留空＝自動置中 70%）
        sz = ttk.LabelFrame(self, text=t("frm_custom_size"))
        sz.grid(row=4, column=0, columnspan=2, sticky="we", padx=10, pady=6)
        self.win_w_var = tk.StringVar(value=self._fmt(rule.get("win_w")))
        self.win_h_var = tk.StringVar(value=self._fmt(rule.get("win_h")))
        self.win_x_var = tk.StringVar(value=self._fmt(rule.get("win_x")))
        self.win_y_var = tk.StringVar(value=self._fmt(rule.get("win_y")))
        ttk.Label(sz, text=t("lbl_w")).grid(row=0, column=0, padx=4, pady=4)
        ttk.Entry(sz, textvariable=self.win_w_var, width=7).grid(row=0, column=1, padx=4)
        ttk.Label(sz, text=t("lbl_h")).grid(row=0, column=2, padx=4)
        ttk.Entry(sz, textvariable=self.win_h_var, width=7).grid(row=0, column=3, padx=4)
        ttk.Label(sz, text=t("lbl_rel_x")).grid(row=0, column=4, padx=4)
        ttk.Entry(sz, textvariable=self.win_x_var, width=7).grid(row=0, column=5, padx=4)
        ttk.Label(sz, text=t("lbl_rel_y")).grid(row=0, column=6, padx=4)
        ttk.Entry(sz, textvariable=self.win_y_var, width=7).grid(row=0, column=7, padx=4)
        ttk.Label(sz, text=t("hint_rel"),
                  foreground="#666").grid(row=1, column=0, columnspan=8, sticky="w", padx=4)

        # 啟用
        self.enabled_var = tk.BooleanVar(value=rule.get("enabled", True))
        ttk.Checkbutton(self, text=t("chk_enable_rule"), variable=self.enabled_var).grid(
            row=5, column=1, sticky="w", **pad)

        # 按鈕
        btns = ttk.Frame(self)
        btns.grid(row=6, column=0, columnspan=2, pady=(4, 10))
        ttk.Button(btns, text=t("btn_ok"), command=self._ok).pack(side="left", padx=6)
        ttk.Button(btns, text=t("btn_cancel"), command=self.destroy).pack(side="left", padx=6)

        self.columnconfigure(1, weight=1)
        exe_box.focus_set()
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self._center(master)

    def _running_exes(self):
        exes = set()
        for hwnd in enum_real_windows():
            n = get_exe_name(get_window_pid(hwnd))
            if n:
                exes.add(n)
        return sorted(exes)

    def _center(self, master):
        self.update_idletasks()
        try:
            mx = master.winfo_rootx() + master.winfo_width() // 2
            my = master.winfo_rooty() + master.winfo_height() // 2
            x = mx - self.winfo_width() // 2
            y = my - self.winfo_height() // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

    @staticmethod
    def _fmt(v):
        try:
            iv = int(v)
            return str(iv) if iv else ""
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def _int(s):
        try:
            return int(float(s))
        except (TypeError, ValueError):
            return 0

    def _ok(self):
        exe = self.exe_var.get().strip()
        if not exe:
            messagebox.showwarning(t("warn_missing_title"), t("warn_missing_exe"), parent=self)
            return
        mon_idx = self.mon_box.current()
        if mon_idx < 0:
            mon_idx = 0
        self.result = {
            "exe": exe,
            "title_contains": self.title_var.get().strip(),
            "monitor_index": mon_idx,
            "mode": self.mode_var.get(),
            "enabled": self.enabled_var.get(),
            "win_w": self._int(self.win_w_var.get()),
            "win_h": self._int(self.win_h_var.get()),
            "win_x": self._int(self.win_x_var.get()),
            "win_y": self._int(self.win_y_var.get()),
        }
        self.destroy()


# ===========================================================================
#  主視窗
# ===========================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.cfg = load_config()
        i18n.set_lang(self.cfg.get("lang", "zh"))
        self.title(t("app_title"))
        self.geometry("800x700")
        self.minsize(740, 620)

        self.rules = self.cfg["rules"]
        self.monitors = get_monitors()
        self.log_q = queue.Queue()
        self.cmd_q = queue.Queue()
        self.watcher = None

        self.tray_close_var = tk.BooleanVar(value=self.cfg.get("tray_close", True))
        self.tray_min_var = tk.BooleanVar(value=self.cfg.get("tray_min", True))

        self._build_ui()
        self._refresh_monitor_label()
        self._refresh_tree()

        # 建立系統列圖示（失敗則停用相關功能）
        self.tray = None
        try:
            self.tray = TrayIcon(t("tray_tooltip"), self.cmd_q.put)
            self.tray.start()
            self.tray.ready.wait(2.0)
            if not self.tray.ok:
                self.tray = None
        except Exception:
            self.tray = None
        if self.tray is None:
            self.log(t("log_tray_failed"))
            self.tray_close_var.set(False)
            self.tray_min_var.set(False)

        self._refresh_ahk_status()
        self.after(250, self._drain_log)
        self.bind("<Unmap>", self._on_unmap)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # ── 螢幕資訊列 ─────────────────────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        self.mon_label = ttk.Label(top, text="", foreground="#225")
        self.mon_label.pack(side="left")
        # 語言切換（中文 / English）
        self.lang_box = ttk.Combobox(
            top, width=8, state="readonly",
            values=[i18n.LANG_DISPLAY[c] for c in i18n.LANGS])
        self.lang_box.set(i18n.LANG_DISPLAY[i18n.get_lang()])
        self.lang_box.bind("<<ComboboxSelected>>", self._on_lang_change)
        self.lang_box.pack(side="right", padx=(0, 0))
        ttk.Label(top, text="🌐").pack(side="right", padx=(0, 4))
        ttk.Button(top, text=t("btn_rescan"), command=self._rescan_monitors)\
            .pack(side="right", padx=(0, 12))

        # ── 步驟 ① 設定規則 ───────────────────────────────────────
        step1 = ttk.LabelFrame(self, text=t("step1_title"))
        step1.pack(fill="both", expand=True, **pad)

        tree_wrap = ttk.Frame(step1)
        tree_wrap.pack(fill="both", expand=True, padx=6, pady=(6, 2))
        cols = ("enabled", "exe", "title", "monitor", "mode")
        self.tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", height=6)
        headers = {
            "enabled": (t("col_enabled"), 50),
            "exe": (t("col_exe"), 180),
            "title": (t("col_title"), 150),
            "monitor": (t("col_monitor"), 70),
            "mode": (t("col_mode"), 140),
        }
        for c, (txt, w) in headers.items():
            self.tree.heading(c, text=txt)
            anchor = "center" if c in ("enabled", "monitor") else "w"
            self.tree.column(c, width=w, anchor=anchor)
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", lambda e: self._edit_rule())

        r1 = ttk.Frame(step1)
        r1.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(r1, text=t("btn_add"), command=self._add_rule).pack(side="left", padx=3)
        ttk.Button(r1, text=t("btn_edit"), command=self._edit_rule).pack(side="left", padx=3)
        ttk.Button(r1, text=t("btn_delete"), command=self._del_rule).pack(side="left", padx=3)
        ttk.Button(r1, text=t("btn_toggle"), command=self._toggle_rule).pack(side="left", padx=3)
        ttk.Button(r1, text=t("btn_capture_layout"),
                   command=self._capture_layout).pack(side="left", padx=(12, 3))
        ttk.Button(r1, text=t("btn_capture_size"),
                   command=self._capture_size).pack(side="right", padx=3)

        # ── 步驟 ② 測試規則（不影響開機） ─────────────────────────
        step2 = ttk.LabelFrame(self, text=t("step2_title"))
        step2.pack(fill="x", **pad)
        r2 = ttk.Frame(step2)
        r2.pack(fill="x", padx=6, pady=6)
        ttk.Button(r2, text=t("btn_apply_now"),
                   command=self._apply_now).pack(side="left", padx=3)
        ttk.Separator(r2, orient="vertical").pack(side="left", fill="y", padx=10)
        self.watch_btn = ttk.Button(r2, text=t("btn_start_watch"), command=self._toggle_watch)
        self.watch_btn.pack(side="left", padx=3)
        self.status_label = ttk.Label(r2, text=t("status_idle"), foreground="#a00")
        self.status_label.pack(side="left", padx=8)
        ttk.Label(r2, text=t("lbl_interval")).pack(side="left", padx=(12, 2))
        self.interval_var = tk.StringVar(value=str(self.cfg.get("interval", 1.0)))
        ttk.Spinbox(r2, from_=0.3, to=5.0, increment=0.1, width=5,
                    textvariable=self.interval_var).pack(side="left")

        # ── 步驟 ③ 部署到開機 ─────────────────────────────────────
        step3 = ttk.LabelFrame(self, text=t("step3_title"))
        step3.pack(fill="x", **pad)
        self.ahk_status = ttk.Label(step3, text="", foreground="#225", justify="left")
        self.ahk_status.pack(anchor="w", padx=6, pady=(6, 4))
        r3a = ttk.Frame(step3)
        r3a.pack(fill="x", padx=6, pady=(0, 2))
        self.install_btn = ttk.Button(r3a, text=t("btn_install_ahk"),
                                      command=self._install_ahk)
        self.install_btn.pack(side="left", padx=3)
        ttk.Button(r3a, text=t("btn_deploy"),
                   command=self._deploy_ahk).pack(side="left", padx=3)
        r3b = ttk.Frame(step3)
        r3b.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(r3b, text=t("btn_run_once"),
                   command=self._run_ahk_once).pack(side="left", padx=3)
        ttk.Button(r3b, text=t("btn_undeploy"),
                   command=self._undeploy_ahk).pack(side="left", padx=3)
        ttk.Button(r3b, text=t("btn_open_folder"),
                   command=self._open_script_folder).pack(side="left", padx=3)

        # ── 日誌 ───────────────────────────────────────────────────
        logf = ttk.LabelFrame(self, text=t("log_frame"))
        logf.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(logf, height=6, state="disabled", wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log_text.yview)
        lsb.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=lsb.set)

        # ── 視窗選項（系統列）──────────────────────────────────────
        tray = ttk.Frame(self)
        tray.pack(fill="x", **pad)
        ttk.Button(tray, text=t("btn_hide_tray"),
                   command=self._hide_to_tray).pack(side="left", padx=4)
        ttk.Checkbutton(tray, text=t("chk_tray_close"),
                        variable=self.tray_close_var,
                        command=self._save).pack(side="left", padx=12)
        ttk.Checkbutton(tray, text=t("chk_tray_min"),
                        variable=self.tray_min_var,
                        command=self._save).pack(side="left", padx=4)

    # ---------- 語言切換 ----------
    def _on_lang_change(self, _event=None):
        sel = self.lang_box.get()
        lang = next((c for c, name in i18n.LANG_DISPLAY.items() if name == sel),
                    i18n.get_lang())
        if lang == i18n.get_lang():
            return
        i18n.set_lang(lang)
        self._save()                       # 把語言偏好寫入設定檔
        self._rebuild_ui()

    def _rebuild_ui(self):
        """切換語言後重建整個介面（狀態保留在 self.* 上，不受影響）。"""
        self.title(t("app_title"))
        try:
            log_content = self.log_text.get("1.0", "end-1c")
        except Exception:
            log_content = ""
        for w in self.winfo_children():
            w.destroy()
        self._build_ui()
        self._refresh_monitor_label()
        self._refresh_tree()
        self._refresh_ahk_status()
        self._refresh_watch_ui()
        if log_content:
            self.log_text.config(state="normal")
            self.log_text.insert("end", log_content + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")

    # ---------- 螢幕 ----------
    def _refresh_monitor_label(self):
        n = len(self.monitors)
        prim = next((i for i, m in enumerate(self.monitors) if m["primary"]), 0)
        self.mon_label.config(text=t("monitors_detected", n=n, prim=prim))

    def _rescan_monitors(self):
        self.monitors = get_monitors()
        self._refresh_monitor_label()
        self.log(t("log_rescanned", n=len(self.monitors)))

    # ---------- 規則 CRUD ----------
    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rules):
            mon_idx = r.get("monitor_index", 0)
            self.tree.insert("", "end", iid=str(i), values=(
                "✔" if r.get("enabled", True) else "✘",
                r.get("exe", ""),
                r.get("title_contains", ""),
                t("monitor_short", idx=mon_idx),
                i18n.mode_label(r.get("mode", "maximized")),
            ))

    def _selected_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(sel[0])

    def _add_rule(self):
        dlg = RuleDialog(self, self.monitors)
        self.wait_window(dlg)
        if dlg.result:
            self.rules.append(dlg.result)
            self._refresh_tree()
            self._save()

    def _edit_rule(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo(t("info_title"), t("select_rule_first"))
            return
        dlg = RuleDialog(self, self.monitors, self.rules[idx])
        self.wait_window(dlg)
        if dlg.result:
            self.rules[idx] = dlg.result
            self._refresh_tree()
            self._save()

    def _del_rule(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo(t("info_title"), t("select_rule_first"))
            return
        if messagebox.askyesno(t("confirm_title"),
                               t("confirm_delete", exe=self.rules[idx].get("exe"))):
            self.rules.pop(idx)
            self._refresh_tree()
            self._save()

    def _toggle_rule(self):
        idx = self._selected_index()
        if idx is None:
            return
        self.rules[idx]["enabled"] = not self.rules[idx].get("enabled", True)
        self._refresh_tree()
        self._save()

    def _apply_now(self):
        """把規則套用到目前已經開啟的視窗（手動排版用）。"""
        monitors = get_monitors()
        count = 0
        for hwnd in enum_real_windows():
            pid = get_window_pid(hwnd)
            if pid == os.getpid():
                continue
            exe = get_exe_name(pid)
            title = get_window_text(hwnd)
            rule = match_rule(self.rules, exe, title)
            if rule:
                apply_rule(hwnd, rule, monitors, self.log)
                count += 1
        self.log(t("log_applied_now", count=count))

    # ---------- 一鍵擷取目前布局 ----------
    @staticmethod
    def _window_monitor_index(hwnd, monitors):
        """以重疊面積最大的螢幕，判定視窗屬於哪個螢幕（回傳索引，無則 None）。"""
        r = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        best, best_area = None, 0
        for i, m in enumerate(monitors):
            mx0, my0, mx1, my1 = m["monitor"]
            iw = min(r.right, mx1) - max(r.left, mx0)
            ih = min(r.bottom, my1) - max(r.top, my0)
            if iw > 0 and ih > 0 and iw * ih > best_area:
                best_area, best = iw * ih, i
        return best

    @staticmethod
    def _detect_mode(hwnd, mon):
        """偵測視窗目前狀態，回傳 (mode, win_w, win_h, win_x, win_y)。"""
        if user32.IsZoomed(hwnd):
            return "maximized", 0, 0, 0, 0
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        mrect = mon["monitor"]
        covers_full = (r.left <= mrect[0] and r.top <= mrect[1]
                       and r.right >= mrect[2] and r.bottom >= mrect[3])
        style = _GetWindowLong(hwnd, GWL_STYLE)
        has_caption = bool(style & WS_CAPTION)
        if covers_full and not has_caption:
            return "fullscreen", 0, 0, 0, 0
        work = mon["work"]
        return ("windowed", r.right - r.left, r.bottom - r.top,
                r.left - work[0], r.top - work[1])

    def _capture_layout(self):
        """把每個螢幕上最上層的前景視窗，各擷取成一條規則。"""
        monitors = get_monitors()
        if not monitors:
            messagebox.showinfo(t("no_monitor_title"), t("no_monitor_body"), parent=self)
            return
        self_pid = os.getpid()
        assigned = {}  # monitor_index -> hwnd（enum_real_windows 為 Z 序由上而下）
        for hwnd in enum_real_windows():
            if get_window_pid(hwnd) == self_pid:
                continue
            mi = self._window_monitor_index(hwnd, monitors)
            if mi is None or mi in assigned:
                continue
            assigned[mi] = hwnd
            if len(assigned) == len(monitors):
                break
        if not assigned:
            messagebox.showinfo(t("no_window_title"), t("no_window_body"), parent=self)
            return

        candidates = []
        for mi in sorted(assigned):
            hwnd = assigned[mi]
            exe = get_exe_name(get_window_pid(hwnd))
            mode, w, h, x, y = self._detect_mode(hwnd, monitors[mi])
            candidates.append({
                "exe": exe, "title_contains": "", "monitor_index": mi,
                "mode": mode, "enabled": True,
                "win_w": w, "win_h": h, "win_x": x, "win_y": y,
                "_title": get_window_text(hwnd),
            })

        # 同一 exe 出現在多個螢幕時，填入標題以便區分（標題可能會變動）
        counts = {}
        for c in candidates:
            counts[norm_exe(c["exe"])] = counts.get(norm_exe(c["exe"]), 0) + 1
        for c in candidates:
            if counts[norm_exe(c["exe"])] > 1 and c["_title"]:
                c["title_contains"] = c["_title"]

        lines = []
        for c in candidates:
            ttl = t("capture_title_part", title=c["title_contains"][:24]) if c["title_contains"] else ""
            lines.append(t("capture_line", idx=c["monitor_index"], exe=c["exe"],
                           mode=i18n.mode_label(c["mode"]), ttl=ttl))
        for c in candidates:
            c.pop("_title", None)

        ans = messagebox.askyesnocancel(
            t("capture_dlg_title"),
            t("capture_dlg_body", lines="\n".join(lines)),
            parent=self)
        if ans is None:
            return
        if ans:
            self.rules.clear()
            self.rules.extend(candidates)
            mode_txt = t("capture_mode_replace")
        else:
            existing = {(norm_exe(r.get("exe", "")), r.get("monitor_index"),
                         (r.get("title_contains") or "").lower())
                        for r in self.rules}
            added = 0
            for c in candidates:
                key = (norm_exe(c["exe"]), c["monitor_index"],
                       (c["title_contains"] or "").lower())
                if key in existing:
                    continue
                self.rules.append(c)
                existing.add(key)
                added += 1
            mode_txt = t("capture_mode_add", added=added)

        self._refresh_tree()
        self._save()
        self.log(t("log_capture", count=len(candidates), mode=mode_txt))

    # ---------- AHK 開機腳本 ----------
    def _refresh_ahk_status(self):
        ahk = find_ahk_exe()
        if ahk:
            ahk_txt = t("ahk_installed", path=ahk)
            self.install_btn.config(text=t("btn_reinstall_ahk"))
        else:
            ahk_txt = t("ahk_not_found")
            self.install_btn.config(text=t("btn_install_ahk"))
        exists = t("script_generated") if os.path.isfile(AHK_SCRIPT_PATH) else t("script_not_generated")
        dep = t("deploy_yes") if is_deployed() else t("deploy_no")
        self.ahk_status.config(
            text=t("ahk_status_fmt", ahk=ahk_txt, script=exists, deploy=dep))

    def _install_ahk(self):
        if find_ahk_exe() and not messagebox.askyesno(
                t("installed_title"), t("installed_confirm")):
            return
        wg = shutil.which("winget")
        if not wg:
            if messagebox.askyesno(t("no_winget_title"), t("no_winget_body")):
                webbrowser.open("https://www.autohotkey.com/download/")
            return
        self.log(t("log_installing"))
        try:
            subprocess.Popen(
                [wg, "install", "-e", "--id", "AutoHotkey.AutoHotkey",
                 "--accept-source-agreements", "--accept-package-agreements"],
                creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            self.log(t("log_winget_failed", e=e))
            return
        threading.Thread(target=self._wait_for_ahk, daemon=True).start()

    def _wait_for_ahk(self):
        for _ in range(180):          # 最多等 3 分鐘
            if find_ahk_exe():
                self.log(t("log_ahk_detected"))
                break
            time.sleep(1)
        else:
            self.log(t("log_ahk_timeout"))
        self.cmd_q.put("refresh_ahk")

    def _deploy_ahk(self):
        ahk = find_ahk_exe()
        if not ahk:
            if messagebox.askyesno(t("ahk_missing_title"), t("ahk_missing_body")):
                self._install_ahk()
            return
        if not self.rules and not messagebox.askyesno(
                t("no_rules_title"), t("no_rules_body")):
            return
        try:
            self._save()
            write_ahk_script(self.rules)
            create_startup_shortcut(ahk)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode("utf-8", "ignore") or str(e)
            messagebox.showerror(t("deploy_failed_title"), t("deploy_shortcut_failed", err=err))
            return
        except Exception as e:
            messagebox.showerror(t("deploy_failed_title"), str(e))
            return
        self._refresh_ahk_status()
        self.log(t("log_deployed", name=os.path.basename(AHK_SCRIPT_PATH)))
        messagebox.showinfo(
            t("deploy_done_title"),
            t("deploy_done_body", script=AHK_SCRIPT_PATH, shortcut=STARTUP_SHORTCUT))

    def _undeploy_ahk(self):
        try:
            remove_startup_shortcut()
        except Exception as e:
            messagebox.showerror(t("undeploy_failed_title"), str(e))
            return
        self._refresh_ahk_status()
        self.log(t("log_undeployed"))

    def _run_ahk_once(self):
        ahk = find_ahk_exe()
        if not ahk:
            messagebox.showerror(t("run_ahk_not_found_title"), t("run_ahk_not_found_body"))
            return
        try:
            self._save()
            write_ahk_script(self.rules)
            run_script_once(ahk)
        except Exception as e:
            messagebox.showerror(t("run_failed_title"), str(e))
            return
        self._refresh_ahk_status()
        self.log(t("log_run_once"))

    def _open_script_folder(self):
        try:
            if os.path.isfile(AHK_SCRIPT_PATH):
                subprocess.Popen(["explorer", "/select,", AHK_SCRIPT_PATH])
            else:
                subprocess.Popen(["explorer", PROJECT_DIR])
        except Exception as e:
            self.log(t("log_open_folder_failed", e=e))

    # ---------- 監控 ----------
    def _refresh_watch_ui(self):
        """依目前監控狀態同步按鈕文字與狀態燈（重建介面後也用得到）。"""
        running = bool(self.watcher and self.watcher.is_alive())
        if running:
            self.watch_btn.config(text=t("btn_stop_watch"))
            self.status_label.config(text=t("status_watching"), foreground="#080")
        else:
            self.watch_btn.config(text=t("btn_start_watch"))
            self.status_label.config(text=t("status_idle"), foreground="#a00")

    def _toggle_watch(self):
        if self.watcher and self.watcher.is_alive():
            self.watcher.stop()
            self.watcher = None
            self._refresh_watch_ui()
        else:
            try:
                interval = float(self.interval_var.get())
            except ValueError:
                interval = 1.0
            self.watcher = Watcher(lambda: self.rules,
                                   self.log_q.put, interval=interval)
            self.watcher.start()
            self._refresh_watch_ui()
            self._save()

    # ---------- 日誌 ----------
    def log(self, msg):
        self.log_q.put(msg)

    def _drain_log(self):
        # 先處理系統列傳來的指令（在 GUI 主執行緒執行才安全）
        try:
            while True:
                self._handle_cmd(self.cmd_q.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                msg = self.log_q.get_nowait()
                ts = time.strftime("%H:%M:%S")
                self.log_text.config(state="normal")
                self.log_text.insert("end", f"[{ts}] {msg}\n")
                # 限制行數
                if int(self.log_text.index("end-1c").split(".")[0]) > 500:
                    self.log_text.delete("1.0", "100.0")
                self.log_text.see("end")
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        self.after(250, self._drain_log)

    # ---------- 系統列 / 視窗顯示 ----------
    def _handle_cmd(self, cmd):
        if cmd == "show":
            self._show_window()
        elif cmd == "toggle_watch":
            self._toggle_watch()
        elif cmd == "refresh_ahk":
            self._refresh_ahk_status()
        elif cmd == "quit":
            self._quit()

    def _show_window(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.attributes("-topmost", True)
        self.attributes("-topmost", False)
        self.focus_force()

    def _hide_to_tray(self):
        if self.tray:
            self.withdraw()
            self.log(t("log_hidden_tray"))
        else:
            self.iconify()

    def _on_unmap(self, event):
        # 視窗被最小化（iconic）時，若有啟用則改為縮到系統列
        if event.widget is self and self.tray and self.tray_min_var.get():
            if self.state() == "iconic":
                self.after(10, self.withdraw)

    def _capture_size(self):
        """找出符合所選規則的開啟視窗，把目前大小/位置存進規則（供「視窗」模式使用）。"""
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo(t("info_title"), t("select_rule_first"))
            return
        rule = self.rules[idx]
        monitors = get_monitors()
        m_idx = rule.get("monitor_index", 0)
        if not (0 <= m_idx < len(monitors)):
            m_idx = next((i for i, m in enumerate(monitors) if m["primary"]), 0)
        work = monitors[m_idx]["work"]
        target_exe = norm_exe(rule.get("exe", ""))
        tc = (rule.get("title_contains") or "").strip().lower()
        found = None
        for hwnd in enum_real_windows():
            pid = get_window_pid(hwnd)
            if pid == os.getpid():
                continue
            if norm_exe(get_exe_name(pid)) != target_exe:
                continue
            if tc and tc not in (get_window_text(hwnd) or "").lower():
                continue
            found = hwnd
            break
        if not found:
            messagebox.showinfo(t("capture_no_window_title"),
                                t("capture_no_window_body", exe=rule.get("exe")),
                                parent=self)
            return
        r = RECT()
        user32.GetWindowRect(found, ctypes.byref(r))
        rule["win_w"] = r.right - r.left
        rule["win_h"] = r.bottom - r.top
        rule["win_x"] = r.left - work[0]
        rule["win_y"] = r.top - work[1]
        self._refresh_tree()
        self._save()
        self.log(t("log_captured_size", exe=rule.get("exe"),
                   w=rule["win_w"], h=rule["win_h"], idx=m_idx,
                   x=rule["win_x"], y=rule["win_y"]))
        messagebox.showinfo(t("captured_title"),
                            t("captured_body", w=rule["win_w"], h=rule["win_h"],
                              x=rule["win_x"], y=rule["win_y"]),
                            parent=self)

    # ---------- 設定 ----------
    def _save(self):
        try:
            interval = float(self.interval_var.get())
        except (ValueError, AttributeError):
            interval = 1.0
        self.cfg = {
            "rules": self.rules,
            "auto_start": False,
            "interval": interval,
            "tray_close": self.tray_close_var.get(),
            "tray_min": self.tray_min_var.get(),
            "lang": i18n.get_lang(),
        }
        save_config(self.cfg)

    def _quit(self):
        if self.watcher and self.watcher.is_alive():
            self.watcher.stop()
        if self.tray:
            self.tray.stop()
        self._save()
        self.destroy()

    def _on_close(self):
        if self.tray and self.tray_close_var.get():
            self._hide_to_tray()
        else:
            self._quit()


if __name__ == "__main__":
    App().mainloop()
