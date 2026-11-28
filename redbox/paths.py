"""앱 데이터 위치. 설정, 로그, 상태는 설치 폴더가 아니라 사용자 폴더(%APPDATA%\\Redbox)에 둔다.
개발 중에는 REDBOX_HOME 환경 변수로 다른 폴더를 쓸 수 있다."""
import ctypes
import os
import sys
import uuid
from ctypes import wintypes

from . import APP_ID


def resource(*parts):
    """앱에 들어 있는 파일(글꼴 등). exe 로 묶으면 묶음 폴더 안, 아니면 저장소 폴더 기준."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


# -- 다른 프로그램 켜기 ------------------------------------------------------------------------------
# 묶은 앱은 PATH 앞에 자기 폴더를, QT_PLUGIN_PATH 에 자기 Qt 플러그인 폴더를 넣고 돈다. 그대로 물려주면
# OBS 같은 다른 Qt 프로그램이 Redbox 의 DLL 과 Qt 플러그인을 끌어 쓰게 되고(버전이 달라 위험하고, 설치 프로그램이
# Redbox 파일을 쓰는 프로그램으로 보고 닫는다), 영상 재생기 같은 프로그램도 같은 영향을 받는다.
_CHILD_DROP = ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML_IMPORT_PATH")


def _app_dirs():
    if not getattr(sys, "frozen", False):
        return []
    return [os.path.normcase(os.path.abspath(d)) for d in {os.path.dirname(sys.executable), getattr(sys, "_MEIPASS", "")} if d]


def child_env(env=None):
    """다른 프로그램에 물려줄 환경 변수: Redbox 폴더를 뺀 PATH, Qt 와 묶음 관련 값 없이."""
    env = dict(os.environ if env is None else env)
    for k in list(env):
        if k.upper() in _CHILD_DROP or k.upper().startswith(("_MEI", "_PYI")):
            env.pop(k)
    dirs = _app_dirs()
    if dirs and "PATH" in env:
        keep = [x for x in env["PATH"].split(os.pathsep)
                if x and not any(os.path.normcase(os.path.abspath(x)).startswith(d) for d in dirs)]
        env["PATH"] = os.pathsep.join(keep)
    return env


def start_file(target):
    """파일, 폴더, 주소를 윈도우 기본 프로그램으로 연다(os.startfile). 깨끗한 환경 변수로 열리게 잠깐 바꿔 둔다."""
    saved = dict(os.environ)
    clean = child_env(saved)
    try:
        for k in set(saved) - set(clean):
            os.environ.pop(k, None)
        os.environ.update(clean)
        os.startfile(target)
    finally:
        for k in set(saved) - set(os.environ):
            os.environ[k] = saved[k]
        os.environ.update(saved)


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
