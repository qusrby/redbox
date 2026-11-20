"""앱 데이터 위치. 설정, 로그, 상태는 설치 폴더가 아니라 사용자 폴더(%APPDATA%\\Redbox)에 둔다.
개발 중에는 REDBOX_HOME 환경 변수로 다른 폴더를 쓸 수 있다."""
import ctypes
import os
import uuid
from ctypes import wintypes

from . import APP_ID


def data_dir():
    base = os.environ.get("REDBOX_HOME")
    if not base:
        appdata = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        base = os.path.join(appdata, APP_ID)
    os.makedirs(base, exist_ok=True)
    return base


def log_dir():
    d = os.path.join(data_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def config_file():
    return os.path.join(data_dir(), "config.json")


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _known_folder(guid_text):
    """윈도우 알려진 폴더(동영상 등)의 실제 경로. 사용자가 위치를 옮겼어도 따라간다."""
    u = uuid.UUID(guid_text)
    g = _GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
    out = ctypes.c_wchar_p()
    try:
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
            return None
        return out.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


def videos_dir():
    return _known_folder("18989B1D-99B5-455B-841C-AB7C74E4DDFC") or os.path.join(os.path.expanduser("~"), "Videos")
