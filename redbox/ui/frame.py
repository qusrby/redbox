"""윈도우 기본 제목 표시줄 없이 그리는 창.
일반 창 그대로 두고(작업 표시줄 최소화, 화면 가장자리 붙이기가 그대로 동작) 테두리 계산과 '어디를 잡았는지' 판정만 바꾼다:
창 머리를 잡으면 이동, 가장자리를 잡으면 크기 조절을 윈도우가 맡는다."""
import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen
from PyQt6.QtWidgets import QAbstractButton

from .style import C

WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084
HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 10, 11, 12, 13, 14, 15, 16, 17
EDGE = 6


def refresh(hwnd):
    """SWP_FRAMECHANGED: 창 속성은 그대로, 테두리 크기만 다시 계산하게 한다."""
    try:
        ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    except Exception:
        pass


def square_corners(hwnd):
    """윈도우 11 이 창 모서리를 둥글게 깎지 않게 한다(각진 모서리)."""
    try:
        pref = ctypes.c_int(1)   # DWMWCP_DONOTROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


BORDER = 1     # 창 둘레 회색 선(어두운 배경 위에서도 창 경계가 보이게). 최대화하면 없앤다


def border_margin(win):
    return 0 if win.isMaximized() else BORDER


def draw_border(win):
    """창 둘레 선. 바깥 레이아웃을 BORDER 만큼 안으로 들여 두면 그 자리에 보인다."""
    if win.isMaximized():
        return
    p = QPainter(win)
    p.setPen(QPen(QColor(C["border2"]), 1))
    p.drawRect(0, 0, win.width() - 1, win.height() - 1)
    p.end()


def handle(msg_ptr, win):
    """처리했으면 돌려줄 값, 아니면 None."""
    msg = wintypes.MSG.from_address(msg_ptr)
    if msg.message == WM_NCCALCSIZE and msg.wParam:
        u = ctypes.windll.user32
        if u.IsZoomed(msg.hWnd):     # 최대화하면 화면 밖으로 나가는 테두리 두께만큼 안쪽으로
            dpi = u.GetDpiForWindow(msg.hWnd)
            pad = u.GetSystemMetricsForDpi(92, dpi)
            fx, fy = u.GetSystemMetricsForDpi(32, dpi) + pad, u.GetSystemMetricsForDpi(33, dpi) + pad
            rc = wintypes.RECT.from_address(msg.lParam)
            rc.left += fx
            rc.top += fy
            rc.right -= fx
            rc.bottom -= fy
        return 0
    if msg.message == WM_NCHITTEST:
        return hit_test(win)
    return None


def hit_test(win):
    pos = win.mapFromGlobal(QCursor.pos())
    x, y, w, h = pos.x(), pos.y(), win.width(), win.height()
    if not win.isMaximized():
        left, right, top, bottom = x < EDGE, x >= w - EDGE, y < EDGE, y >= h - EDGE
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
    check = getattr(win, "is_drag_area", None)
    if check and check(pos) and not isinstance(win.childAt(pos), QAbstractButton):
        return HTCAPTION
    return HTCLIENT


class WinButton(QAbstractButton):
    """최소화, 최대화(복원), 닫기. 직접 그린 선 아이콘."""

    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.restore = False
        self.setFixedSize(46, 36)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def set_restore(self, on):
        if on != self.restore:
            self.restore = on
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        hover = self.underMouse()
        if hover:
            p.fillRect(self.rect(), QColor("#e5484d" if self.kind == "close" else C["surface2"]))
        p.setPen(QPen(QColor("#ffffff" if hover and self.kind == "close" else C["text2"]), 1))
        cx, cy = self.width() / 2, self.height() / 2
        s = 5
        if self.kind == "min":
            p.drawLine(int(cx - s), int(cy), int(cx + s), int(cy))
        elif self.kind == "max":
            if self.restore:
                p.drawRect(QRectF(cx - s, cy - s + 2, 2 * s - 2, 2 * s - 2))
                p.drawLine(int(cx - s + 2), int(cy - s), int(cx + s), int(cy - s))
                p.drawLine(int(cx + s), int(cy - s), int(cx + s), int(cy + s - 2))
            else:
                p.drawRect(QRectF(cx - s, cy - s, 2 * s, 2 * s))
        else:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.drawLine(int(cx - s), int(cy - s), int(cx + s), int(cy + s))
            p.drawLine(int(cx - s), int(cy + s), int(cx + s), int(cy - s))
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)
