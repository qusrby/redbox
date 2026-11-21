"""작업표시줄 단추에 녹화 표시(빨간 점) 겹치기. 윈도우 ITaskbarList3.SetOverlayIcon 을 ctypes 로 부른다."""
import ctypes
import sys
from ctypes import wintypes

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from .style import REC_DOT

_CLSID = "{56FDF344-FD6D-11d0-958A-006097C9A090}"     # TaskbarList
_IID = "{ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf}"       # ITaskbarList3
_HRINIT, _SET_OVERLAY = 3, 18                          # vtable 순서


class _GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]


def _guid(s):
    g = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
    return g


def _light_taskbar():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "SystemUsesLightTheme")[0])
    except OSError:
        return False


class Taskbar:
    def __init__(self):
        self._ptr = None
        self._icon = None
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.ole32.CoInitialize(None)
            p = ctypes.c_void_p()
            ctypes.oledll.ole32.CoCreateInstance(ctypes.byref(_guid(_CLSID)), None, 1,     # CLSCTX_INPROC_SERVER
                                                 ctypes.byref(_guid(_IID)), ctypes.byref(p))
            self._ptr = p
            self._call(_HRINIT, ctypes.HRESULT, [])
        except OSError:
            self._ptr = None

    def _call(self, index, restype, args, argtypes=()):
        vtbl = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])
        return fn(self._ptr, *args)

    def _rec_icon(self):
        """빨간 점. 로고 타일(빨강)과 섞이지 않게 작업표시줄 바탕색 테를 두른다(트레이 아이콘의 파낸 둘레와 같은 모양)."""
        if self._icon is None:
            n = max(16, ctypes.windll.user32.GetSystemMetrics(49))   # SM_CXSMICON(배율 반영)
            img = QImage(n, n, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#eeeeee" if _light_taskbar() else "#1c1c1c"))
            p.drawEllipse(QRectF(0, 0, n, n))
            g = n * 0.16
            p.setBrush(QColor(REC_DOT))
            p.drawEllipse(QRectF(g, g, n - 2 * g, n - 2 * g))
            p.end()
            self._icon = int(img.toHICON())
        return self._icon

    def set_recording(self, hwnd, on, desc=""):
        """on 이면 빨간 점, 아니면 지운다. 성공하면 True."""
        if not self._ptr or not hwnd:
            return False
        try:
            hr = self._call(_SET_OVERLAY, ctypes.c_long,
                            [wintypes.HWND(hwnd), wintypes.HICON(self._rec_icon() if on else 0), desc if on else None],
                            (wintypes.HWND, wintypes.HICON, ctypes.c_wchar_p))
            return hr == 0
        except OSError:
            return False
