"""게임 감지에 쓰는 윈도우 API 모음(읽기 전용: 프로세스, 창, 모듈, 파일 버전 정보)."""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
version = ctypes.WinDLL("version", use_last_error=True)

INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
TH32CS_SNAPPROCESS = 0x2
TH32CS_SNAPMODULE = 0x8
TH32CS_SNAPMODULE32 = 0x10
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_BAD_LENGTH = 24


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("GlblcntUsage", wintypes.DWORD), ("ProccntUsage", wintypes.DWORD),
                ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wintypes.DWORD),
                ("hModule", wintypes.HMODULE), ("szModule", ctypes.c_wchar * 256),
                ("szExePath", ctypes.c_wchar * 260)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.POINTER(wintypes.UINT)]

_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]


def set_dpi_aware():
    """창 크기를 실제 화면 픽셀로 받으려면 먼저 불러야 한다(배율 150%에서도 전체 화면 판정이 맞게)."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2
    except Exception:
        pass


def list_processes():
    """[(pid, exe 이름)]. psutil 보다 훨씬 싸다(2초마다 부르는 곳)."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return []
    out = []
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((e.th32ProcessID, e.szExeFile))
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return out


def exe_path(pid):
    """실행 파일 전체 경로. 권한이 없으면 빈 문자열."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def module_names(pid):
    """프로세스가 불러온 DLL 이름(소문자) 집합. 권한이 없으면(안티치트 등) None."""
    for _ in range(5):
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
        if snap and snap != INVALID_HANDLE_VALUE:
            break
        if ctypes.get_last_error() != ERROR_BAD_LENGTH:   # 모듈이 막 바뀌는 중이면 잠깐 뒤 다시
            return None
    else:
        return None
    names = set()
    try:
        m = MODULEENTRY32W()
        m.dwSize = ctypes.sizeof(m)
        ok = kernel32.Module32FirstW(snap, ctypes.byref(m))
        while ok:
            names.add(m.szModule.lower())
            ok = kernel32.Module32NextW(snap, ctypes.byref(m))
    finally:
        kernel32.CloseHandle(snap)
    return names


def _rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def window_pid(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def visible_windows():
    """{pid: [(hwnd, 너비, 높이)]} 보이는 최상위 창 전체."""
    out = {}

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            r = _rect(hwnd)
            w, h = r.right - r.left, r.bottom - r.top
            if w > 0 and h > 0:
                out.setdefault(window_pid(hwnd), []).append((hwnd, w, h))
        return True

    user32.EnumWindows(_EnumWindowsProc(cb), 0)
    return out


def foreground():
    """(hwnd, pid, 전체 화면 여부). 창이 모니터 전체를 덮으면(전체 화면, 테두리 없는 창) 전체 화면으로 본다."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, 0, False
    r = _rect(hwnd)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    mon = user32.MonitorFromWindow(hwnd, 2)   # MONITOR_DEFAULTTONEAREST
    if not mon or not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return hwnd, window_pid(hwnd), False
    m = mi.rcMonitor
    full = r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
    return hwnd, window_pid(hwnd), full


_GENERIC_PRODUCT = {"", "unrealengine", "unreal engine", "unity player", "unityplayer", "game", "launcher"}


def product_name(path):
    """실행 파일의 제품 이름(없으면 파일 설명). 엔진 기본값 같은 뜻 없는 이름이면 None."""
    try:
        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, buf):
            return None
        p = ctypes.c_void_p()
        n = wintypes.UINT()
        langs = []
        if version.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(p), ctypes.byref(n)) and n.value >= 4:
            arr = ctypes.cast(p, ctypes.POINTER(ctypes.c_uint16 * (n.value // 2))).contents
            langs = [(arr[i], arr[i + 1]) for i in range(0, len(arr) - 1, 2)]
        langs += [(0x0409, 0x04B0), (0x0409, 0x04E4), (0x0000, 0x04B0)]
        for key in ("ProductName", "FileDescription"):
            for lang, cp in langs:
                q = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\{key}"
                if version.VerQueryValueW(buf, q, ctypes.byref(p), ctypes.byref(n)) and n.value > 1:
                    text = ctypes.wstring_at(p.value, n.value).rstrip("\x00").strip()
                    if text.lower() not in _GENERIC_PRODUCT:
                        return text
    except OSError:
        pass
    return None


def fixed_drives():
    out = []
    mask = kernel32.GetLogicalDrives()
    for i in range(26):
        if mask & (1 << i):
            root = f"{chr(65 + i)}:\\"
            if kernel32.GetDriveTypeW(root) == 3:   # DRIVE_FIXED
                out.append(root)
    return out


def is_under(path_lower, dir_lower):
    d = dir_lower.rstrip("\\/") + os.sep
    return path_lower.startswith(d)
